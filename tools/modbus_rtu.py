#!/usr/bin/env python3
"""
modbus_rtu.py - Modbus RTU master for the TUF-2000 / TDS-100 ultrasonic
flowmeter, sharing an RS485 pair with the HS300 drive.

THE REGISTER MAP BELOW IS THE CONFIRMED ONE, taken from the Web Serial
dashboard that is already reading this meter. It is not a guess from a
datasheet, which matters: registers 3-4 are HEAT flow rate, not velocity, and
reading velocity from there gives a plausible-looking number that is wrong.

SHARING THE BUS
  Both devices are slaves and neither answers the other's frames. The meter
  reads 0xAA as a device address and discards HS300 traffic; the drive never
  finds its AA 55 sync pair in a Modbus frame. So no arbitration is needed
  beyond not transmitting at the same time, which the agent's single lock
  already guarantees.

  Set the METER to 115200 to match the drive. At 9600 a full HS300 telemetry
  read takes 441 ms - longer than the drive's own 404 ms publish interval - so
  you would never see fresh data.

ON THE METER
  M50 address 1 · M51 baud/parity/bits/stop · M52 MODBUS RTU
"""
import struct, time

def crc16(data):
    """Modbus CRC16: reflected 0xA001, init 0xFFFF, transmitted low byte first."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc


# ---------------------------------------------------------------- decoding
# 32-bit values are CDAB: the two 16-bit registers arrive with the HIGH word
# SECOND. Decoding as plain big-endian gives a number that looks almost right
# and is completely wrong.
def f32(regs, i, order="cdab"):
    hi, lo = (regs[i+1], regs[i]) if order == "cdab" else (regs[i], regs[i+1])
    return struct.unpack('>f', struct.pack('>HH', hi, lo))[0]

def i32(regs, i, order="cdab"):
    hi, lo = (regs[i+1], regs[i]) if order == "cdab" else (regs[i], regs[i+1])
    return struct.unpack('>i', struct.pack('>HH', hi, lo))[0]

def total(whole, frac):
    """The totalizer is a whole part in a LONG plus a fraction in a separate
    REAL4. A fraction outside [0,1) means that register did not decode - use
    the whole part alone rather than publishing nonsense."""
    if not (-1.0 < frac < 1.0) or frac != frac:      # NaN fails both
        frac = 0.0
    return whole + frac


class ModbusRTU:
    """Master. Takes an ALREADY-OPEN pyserial port and shares it."""

    def __init__(self, ser, unit=1, gap=0.02, timeout=0.6, retries=3,
                 order="cdab"):
        self.ser = ser
        self.unit = unit
        self.gap = gap
        self.timeout = timeout
        self.retries = retries
        self.order = order
        self.txn = self.retry = self.fail = self.crc_err = 0

    # Registers are given 1-BASED, exactly as the meter's manual numbers them.
    # Function 03 addresses from 0, so the -1 happens here and in one place.
    def read(self, first_register, count):
        addr = first_register - 1
        body = bytes([self.unit, 0x03]) + struct.pack('>HH', addr, count)
        c = crc16(body)
        req = body + bytes([c & 0xFF, c >> 8])
        want = 5 + 2 * count

        self.txn += 1
        for attempt in range(self.retries):
            time.sleep(self.gap)
            self.ser.reset_input_buffer()
            self.ser.write(req)
            self.ser.flush()

            buf = bytearray()
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                n = self.ser.in_waiting
                chunk = self.ser.read(n if n else 1)
                if chunk:
                    buf += chunk
                if len(buf) < want:
                    continue
                # Scan rather than assume position: HS300 traffic can precede
                # our reply on a shared bus.
                for j in range(len(buf) - want + 1):
                    if buf[j] != self.unit or buf[j+1] != 0x03:
                        continue
                    if buf[j+2] != 2 * count:
                        continue
                    fr = bytes(buf[j:j+want])
                    ck = crc16(fr[:-2])
                    if (ck & 0xFF) != fr[-2] or (ck >> 8) != fr[-1]:
                        self.crc_err += 1
                        continue
                    if attempt:
                        self.retry += attempt
                    return list(struct.unpack('>%dH' % count, fr[3:3+2*count]))
                # a Modbus exception reply is 5 bytes, function | 0x80
                for j in range(len(buf) - 4):
                    if buf[j] == self.unit and buf[j+1] == 0x83:
                        self.fail += 1
                        return None
        self.fail += 1
        return None

    def read_all(self):
        """Two transactions, matching the working dashboard.

            block 1, registers 1-12
              1-2   flow rate       REAL4  m3/h
              3-4   heat flow rate  REAL4          <- NOT velocity
              5-6   fluid velocity  REAL4  m/s
              7-8   sound velocity  REAL4  m/s
              9-10  positive total  LONG
              11-12 positive frac   REAL4

            block 2, registers 25-28
              25-26 net total       LONG
              27-28 net frac        REAL4

        Returns {name: (value, unit)}. A missing key means that read failed,
        which is more useful than a zero.
        """
        out = {}
        o = self.order

        g = self.read(1, 12)
        if g:
            out["flow_rate"] = (f32(g, 0, o),  "m3/h")
            out["velocity"]  = (f32(g, 4, o),  "m/s")
            out["sound_vel"] = (f32(g, 6, o),  "m/s")
            out["pos_total"] = (total(i32(g, 8, o), f32(g, 10, o)), "")

        g = self.read(25, 4)
        if g:
            out["net_total"] = (total(i32(g, 0, o), f32(g, 2, o)), "")

        return out

    @staticmethod
    def sound_vel_ok(v):
        """Water is ~1482 m/s at 20 C. A wildly different figure means the
        pipe parameters on the meter (M10/M11) are wrong, and every flow
        reading derived from them is wrong with it - so this is worth
        surfacing rather than leaving as a number nobody checks."""
        return 1350.0 <= v <= 1600.0
