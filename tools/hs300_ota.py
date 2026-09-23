#!/usr/bin/env python3
"""
hs300_ota.py - flash new application firmware into the HS300 drive over its
normal serial link. No ST-Link, no opening the cabinet.

  python hs300_ota.py COM11 app.bin --rs485          (field, RS485)
  python hs300_ota.py COM3  app.bin --ttl            (bench, TTL)
  python hs300_ota.py COM11 app.bin --rs485 --baud 9600

WHAT HAPPENS
  1. connects to the RUNNING app at its normal baud (scans if needed),
     checks the firmware magic, sends CMD_OTA_ENTER
  2. the drive stops the motor, ACKs, and reboots into the bootloader,
     which listens at 115200 on BOTH ports
  3. this reopens at 115200 and streams the image: BEGIN(len,crc32) ->
     CHUNKs in order -> END. The bootloader burns page-by-page and only
     marks the image bootable after the FLASH CRC verifies.
  4. the drive boots the new app; this reconnects at the old baud and
     confirms the new magic.

SAFETY
  - a cut cable / power loss mid-update cannot brick the drive: the
    bootloader's metadata is written only after verification, so on the next
    boot it simply waits for a retry. Run this again.
  - --enter-only just puts the drive in the bootloader (for manual testing);
    --no-enter skips step 1 if the drive is ALREADY in the bootloader.

THE .bin
  Keil: fromelf --bin --output app.bin project.axf   (or add it as a User
  command after build). The image must be LINKED AT 0x08001000 - see
  OTA_F334_MIGRATION.md. This tool refuses an image whose vector table
  does not point into the app region, so flashing an old 0x08000000 build
  by mistake is caught here, not on the drive.
"""
import sys, time, struct, zlib, argparse

sys.path.insert(0, ".")
import serial
try:
    import hs300_protocol as proto
except ImportError:
    proto = None

SYNC     = b"\xAA\x55"
FW_BEGIN, FW_CHUNK, FW_END = 0x10, 0x11, 0x12
FW_READ                    = 0x13          # bootloader >= Release/-Os 2026-09-13
FW_CHUNKC                  = 0x14          # chunk + crc32, bootloader 2026-09-13c
FW_ACK,   FW_NAK, FW_BAD   = 0x90, 0x91, 0x92
META_ADDR = 0x0800F800
META_MAGIC = None                          # learned from the page itself (m[3] == m0^m1^m2)
OTA_BAUD  = 115200
# ONE TRAILING PAD BYTE ON EVERY FRAME. Auto-direction USB-RS485 adapters drop
# their driver a few bit-times early on the LAST byte of a burst, so the drive
# receives that byte mangled. Measured 2026-09-13: every corrupt byte of a
# failed OTA sat at a 1 KB chunk end (offsets 0x3FF/0x7FF). With a pad byte
# the clipped byte is the pad, which the bootloader's SYNC search discards.
PAD       = b"\x00"
CHUNK     = 1024
APP_ADDR  = 0x08001000
APP_MAX   = 58 * 1024


def log(m):
    print("  " + m, flush=True)


def wait_reply(p, timeout):
    """The bootloader answers AA 55 <code> <code^FF>."""
    end = time.time() + timeout
    st = 0
    while time.time() < end:
        b = p.read(1)
        if not b:
            continue
        v = b[0]
        if st == 0:
            st = 1 if v == 0xAA else 0
        elif st == 1:
            st = 2 if v == 0x55 else (1 if v == 0xAA else 0)
        else:
            nxt = p.read(1)
            if nxt and nxt[0] == (v ^ 0xFF):
                return v
            st = 0
    return None


def upload(p, img, wait_s=0):
    crc = zlib.crc32(img) & 0xFFFFFFFF
    log("image %d bytes, crc32 %08X" % (len(img), crc))

    # BEGIN. The bootloader erases 29 pages BEFORE it ACKs (~1.5 s), so the
    # timeout here is generous.
    # With wait_s > 0 the BEGIN is repeated every 3 s until the bootloader
    # answers: for catching the ~8 s window after a power-cycle when the app
    # on the chip is dead and cannot be asked to enter the bootloader.
    t_end = time.time() + wait_s
    while True:
        p.reset_input_buffer()
        p.write(SYNC + bytes([FW_BEGIN]) + struct.pack("<II", len(img), crc) + PAD)
        r = wait_reply(p, 3.0 if wait_s > 0 else 8.0)
        if r == FW_ACK or wait_s <= 0 or time.time() > t_end:
            break
        log("  waiting for the bootloader (power-cycle the drive)... %ds left" % (t_end - time.time()))
    if r != FW_ACK:
        log("no ACK to BEGIN (%s) - is the drive in the bootloader?"
            % ("NAK" if r == FW_NAK else "silence"))
        return False
    log("erase done, streaming...")

    sent = 0
    t0 = time.time()
    legacy = False           # bootloaders before 2026-09-13 only know FW_CHUNK (no per-chunk CRC)
    while sent < len(img):
        n = min(CHUNK, len(img) - sent)
        data = img[sent:sent + n]
        def mk(legacy_):
            if legacy_:
                return SYNC + bytes([FW_CHUNK]) + struct.pack("<IH", sent, n) + data + PAD
            return (SYNC + bytes([FW_CHUNKC]) + struct.pack("<IH", sent, n)
                    + data + struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF) + PAD)
        ok = False
        for attempt in range(6):
            p.write(mk(legacy))
            r = wait_reply(p, 3.0)
            if r == FW_ACK:
                ok = True
                break
            if r is None and not legacy and sent == 0 and attempt == 0:
                # an old bootloader silently ignores the CRC'd chunk: fall back
                # to the plain chunk for this session (no per-chunk check)
                legacy = True
                log("no ACK to the CRC'd chunk - old bootloader, switching to plain FW_CHUNK")
                continue
            log("chunk @%d: %s (attempt %d)"
                % (sent, {FW_NAK: "NAK", FW_BAD: "crc mismatch, resending"}.get(r, "timeout"), attempt + 1))
            # The bootloader requires IN-ORDER chunks. A NAK means it gave up
            # on this session entirely - do not press on. FW_BAD just means
            # this chunk arrived damaged: send it again.
            if r == FW_NAK:
                return False
        if not ok:
            return False
        sent += n
        pct = sent * 100 // len(img)
        print("\r  %3d%%  %d/%d B  %.1f kB/s" %
              (pct, sent, len(img), sent / 1024.0 / max(time.time() - t0, 0.01)),
              end="", flush=True)
    print()

    p.write(SYNC + bytes([FW_END]) + PAD)
    r = wait_reply(p, 10.0)          # final page + flash CRC + metadata
    if r != FW_ACK:
        log("FINAL VERIFY FAILED on the drive - image NOT marked bootable.")
        log("Nothing is lost: the bootloader is still waiting. Run again.")
        return False
    log("verified and marked bootable")
    return True


def read_flash(p, addr, n, tries=3):
    """FW_READ: n bytes from flash address addr, CRC-checked. None on failure.
    Needs the 2026-09-13 bootloader; older ones ignore the command (silence)."""
    for _ in range(tries):
        p.reset_input_buffer()
        p.write(SYNC + bytes([FW_READ]) + struct.pack("<II", addr, n) + PAD)
        r = wait_reply(p, 3.0)
        if r != FW_ACK:
            if r is None:
                return None                     # not supported / not listening
            continue
        buf = bytearray()
        end = time.time() + 2.0 + n / 5000.0
        while len(buf) < n + 4 and time.time() < end:
            c = p.read(n + 4 - len(buf))
            if c:
                buf += c
        if len(buf) == n + 4:
            data = bytes(buf[:n])
            if (zlib.crc32(data) & 0xFFFFFFFF) == struct.unpack("<I", buf[n:])[0]:
                return data
        log("read @%08X: bad/short reply, retrying" % addr)
    return None


def backup(p, path):
    """Copy the app that is on the chip to `path`, exactly as the bootloader
    sees it: length and CRC from the metadata page when it is valid, the whole
    58 KB region otherwise. Returns True when the file is written and checked."""
    meta = read_flash(p, META_ADDR, 16)
    if meta is None:
        log("backup: bootloader did not answer FW_READ - it is too old for this")
        return False
    m = struct.unpack("<IIII", meta)
    if m[3] == (m[0] ^ m[1] ^ m[2]) and 0 < m[1] <= APP_MAX:
        n, want = m[1], m[2]
        log("backup: metadata says app is %d bytes, crc32 %08X" % (n, want))
    else:
        n, want = APP_MAX, None
        log("backup: no valid metadata (ST-Link flashed app?) - reading the full %d B region" % n)
    img = bytearray()
    t0 = time.time()
    while len(img) < n:
        k = min(CHUNK, n - len(img))
        d = read_flash(p, APP_ADDR + len(img), k)
        if d is None:
            log("backup: read failed at %d - aborting, nothing written" % len(img))
            return False
        img += d
        print("\r  %3d%%  %d/%d B  %.1f kB/s" %
              (len(img) * 100 // n, len(img), n, len(img) / 1024.0 / max(time.time() - t0, 0.01)),
              end="", flush=True)
    print()
    got = zlib.crc32(bytes(img)) & 0xFFFFFFFF
    if want is not None and got != want:
        log("backup: CRC MISMATCH (chip %08X, metadata %08X) - not written" % (got, want))
        return False
    if want is None:
        # trim the 0xFF tail of an ST-Link-flashed image
        end = len(img)
        while end > 8 and img[end - 1] == 0xFF:
            end -= 1
        img = img[:end]
        got = zlib.crc32(bytes(img)) & 0xFFFFFFFF
    with open(path, "wb") as fh:
        fh.write(bytes(img))
    log("backup: wrote %s  (%d B, crc32 %08X)" % (path, len(img), got))
    return True


def main():
    ap = argparse.ArgumentParser(description="HS300 F334 OTA uploader")
    ap.add_argument("port")
    ap.add_argument("image", nargs="?", help="app .bin linked at 0x08001000 (omit with --backup to only back up)")
    ap.add_argument("--backup", metavar="FILE",
                    help="first copy the app that is ON THE CHIP to FILE (FW_READ, "
                         "2026-09-13 bootloader or newer); then upload `image` if given")
    ap.add_argument("--baud", type=int, default=9600,
                    help="the RUNNING app's baud (for the enter step)")
    ap.add_argument("--rs485", action="store_true", default=True)
    ap.add_argument("--ttl", action="store_true")
    ap.add_argument("--no-enter", action="store_true",
                    help="drive is ALREADY in the bootloader")
    ap.add_argument("--wait", type=int, default=0, metavar="SECS",
                    help="keep sending BEGIN for SECS seconds until the bootloader "
                         "answers (use with --no-enter after a power-cycle)")
    ap.add_argument("--enter-only", action="store_true",
                    help="send CMD_OTA_ENTER and stop")
    a = ap.parse_args()

    if a.image is None and not a.backup:
        log("nothing to do: give an image to upload and/or --backup FILE")
        return 1
    img = None
    if a.image is not None:
        img = open(a.image, "rb").read()
        if len(img) > APP_MAX:
            log("image %d B exceeds the %d B app region" % (len(img), APP_MAX))
            return 1
        # Sanity: the vector table must point into the app region, or this is a
        # build still linked at 0x08000000 - which would run once and never again.
        sp, pc = struct.unpack_from("<II", img, 0)
        if not (0x20000000 <= sp <= 0x20003000) or not (APP_ADDR <= pc < APP_ADDR + APP_MAX):
            log("REFUSED: vector table SP=%08X PC=%08X - this image is not "
                "linked at 0x08001000. See OTA_F334_MIGRATION.md." % (sp, pc))
            return 1

    mode = "ttl" if a.ttl else "rs485"

    # ---- step 1: tell the running app to enter the bootloader -----------
    if not a.no_enter:
        if proto is None:
            log("hs300_protocol.py not found - use --no-enter with the drive "
                "already in the bootloader")
            return 1
        link = proto.Link(a.port, a.baud, mode)
        link.open()
        m = link.ping()
        if m is None:
            log("no reply from the app at %d - if the drive is already in "
                "the bootloader, use --no-enter" % a.baud)
            link.close()
            return 1
        log("app alive, magic %s - entering bootloader" % hex(m))
        link.command("OTA_ENTER")
        link.close()
        if a.enter_only:
            log("done (--enter-only). Bootloader listens ~8 s at 115200.")
            return 0
        time.sleep(0.8)               # reset + bootloader init

    # ---- step 2: stream at the bootloader's fixed 115200 ----------------
    p = serial.Serial()
    p.port, p.baudrate, p.timeout = a.port, OTA_BAUD, 0.05
    p.dtr = p.rts = False
    p.open()
    if a.backup:
        if not backup(p, a.backup):
            p.close()
            log("backup failed - NOT uploading. The bootloader boots the existing app after ~8 s of quiet.")
            return 1
        if img is None:
            p.close()
            log("done (backup only). The bootloader boots the existing app after ~8 s of quiet.")
            return 0
    ok = upload(p, img, a.wait)
    p.close()
    if not ok:
        return 1

    # ---- step 3: confirm the new app came up -----------------------------
    if proto is not None:
        time.sleep(1.5)
        link = proto.Link(a.port, a.baud, mode)
        link.open()
        for _ in range(10):
            m = link.ping()
            if m is not None:
                log("NEW app is up, magic %s" % hex(m))
                link.close()
                return 0
            time.sleep(0.5)
        link.close()
        log("uploaded OK but the app has not answered yet - give it a "
            "moment and check with test_link.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
