#!/usr/bin/env python3
"""attack_pair.py - run the combined attack (string out + resistor bank) with
the shed ON and then OFF, N times, unattended, and put the drive back.

    python attack_pair.py runs/20260910 --pairs 2 [--hold 90] [--settle 300]
                          [--order on,off] [--f49 0.80 --f50 0.50]

One "shot": mark, R2 ON (string out) + R1 ON <hold> s (load), wait, R2 OFF.
After every shot: if the drive is in a FAULT state, RESET_FAULT + START through
the logger's cmd.txt and wait until it is back above 44 Hz; then settle.
Shed OFF means F49 0.30 / F50 0.20 (both lines under the 200 V UV trip); the
shed is ALWAYS restored to --f49/--f50 before the script ends, whatever
happened. Every step is stamped in marks.log; progress in pair.log.

Needs: solar_day.py running on the same outdir (its CSV is the eyes, its
cmd.txt the hands), the relay box reachable (relay_ctl.py).
"""
import sys, os, time, csv, argparse, subprocess, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outdir')
    ap.add_argument('--pairs', type=int, default=2)
    ap.add_argument('--hold', type=int, default=90)
    ap.add_argument('--settle', type=int, default=300)
    ap.add_argument('--order', default='on,off')
    ap.add_argument('--f49', default='0.80'); ap.add_argument('--f50', default='0.50')
    ap.add_argument('--start-pair', type=int, default=2, help='pair number for the marks')
    ap.add_argument('--freeze', type=float, default=0.0,
                    help='seconds after the edge to FREEZE the capture ring (set CAP_CTRL 4 through the logger). '
                         'Use on droop-ON shots with a fine --ring-div in solar_day, where no trip freezes it; 0 = off')
    a = ap.parse_args()
    outdir = os.path.join(HERE, a.outdir) if not os.path.isabs(a.outdir) else a.outdir
    day = os.path.basename(outdir.rstrip('/\\'))
    csvp = os.path.join(outdir, 'solar_day_%s.csv' % day)
    logp = os.path.join(outdir, 'pair.log')

    def log(m):
        line = '%s  %s' % (datetime.datetime.now().strftime('%H:%M:%S'), m)
        print(line, flush=True)
        with open(logp, 'a') as fh: fh.write(line + '\n')

    def relay(*args):
        r = subprocess.run([PY, os.path.join(HERE, 'relay_ctl.py')] + list(args), capture_output=True, text=True, timeout=40)
        out = (r.stdout.strip().splitlines() or [''])[-1]
        log('  relay %s -> %s' % (' '.join(args), out[14:90]))
        return r.returncode == 0

    def cmds(lines):
        """through the logger: returns the cmd.log echoes"""
        p = os.path.join(outdir, 'cmd.txt')
        with open(p, 'w') as fh: fh.write('\n'.join(lines) + '\n')
        t0 = time.time()
        while time.time() - t0 < 40 and os.path.exists(p): time.sleep(1)
        time.sleep(1)
        try: tail = open(os.path.join(outdir, 'cmd.log')).read().strip().splitlines()[-len(lines):]
        except Exception: tail = []
        for t in tail: log('  ' + t[10:110])
        return tail

    def last():
        try:
            rows = list(csv.DictReader(open(csvp)))
            return rows[-1] if rows else None
        except Exception:
            return None

    def state():
        r = last()
        if not r or not r['sts']: return ('?', 0.0, 0.0)
        return (r['sts'], float(r['hz'] or 0), float(r['VDC'] or 0))

    def wait_speed(limit=360):
        """'at speed' = closed loop and above the pump's cut-in with margin; the
        afternoon tracker sits at 38..41 Hz, so 44 was a 6 min wait for nothing"""
        t0 = time.time()
        while time.time() - t0 < limit:
            s, hz, v = state()
            if s == 'ON' and hz > 30.0: return True
            if s.startswith('FAULT') and time.time() - t0 > 20: return False
            time.sleep(4)
        return state()[0] == 'ON'

    def recover():
        s, hz, v = state()
        if s.startswith('FAULT'):
            log('drive in %s - RESET_FAULT + START' % s)
            cmds(['cmd RESET_FAULT']); time.sleep(4)
            cmds(['cmd START'])
        elif s == 'OFF':
            log('drive OFF - START')
            cmds(['cmd START'])
        ok = wait_speed()
        log('drive %s' % ('back at speed' if ok else 'NOT back at speed: %s %.1f Hz' % state()[:2]))
        return ok

    def shed(on):
        if on: cmds(['set BUS_SHED_HI %s' % a.f49, 'set BUS_SHED_LO %s' % a.f50])
        else:  cmds(['set BUS_SHED_HI 0.30', 'set BUS_SHED_LO 0.20'])

    def after_pull():
        """fire right AFTER a ring pull so the whole edge (and a trip, ~6-9 s in)
        lands inside a running 18 s window: on 09-11 two OC trips coincided with
        a pull and the ring could not freeze (cap_freeze needs RUNNING)."""
        ip = os.path.join(outdir, 'ring', 'index.csv')
        try: m0 = os.path.getmtime(ip)
        except Exception: return
        t0 = time.time()
        while time.time() - t0 < 40:
            try:
                if os.path.getmtime(ip) != m0: time.sleep(2.5); return
            except Exception: return
            time.sleep(0.3)

    def shot(tag, on):
        s, hz, v = state()
        log('%s: shed %s, drive %s %.1f Hz %.0f V' % (tag, 'ON' if on else 'OFF', s, hz, v))
        after_pull()
        relay('mark', '%s COMBINED string out + load, shed %s, %d s' % (tag, 'ON' if on else 'OFF', a.hold))
        relay('string', 'out')
        relay('load', 'on', str(a.hold))
        t0 = time.time(); tripped = None
        if a.freeze > 0:
            time.sleep(max(0.0, a.freeze - (time.time() - t0)))
            cmds(['set CAP_CTRL 4'])          # freeze the ring; solar_day dumps it on its next pull
            log('  ring frozen %.1f s after the edge' % (time.time() - t0))
        while time.time() - t0 < a.hold + 2:
            s, hz, v = state()
            if s.startswith('FAULT') and not tripped:
                tripped = s; log('  TRIP %s at +%.0f s (%s)' % (s, time.time() - t0, last()['stop_r']))
            time.sleep(3)
        relay('string', 'in')
        relay('load', 'off')
        s, hz, v = state()
        log('  end of shot: drive %s %.1f Hz %.0f V%s' % (s, hz, v, '' if not tripped else ' - TRIPPED ' + tripped))
        relay('mark', '%s result: %s' % (tag, 'TRIP ' + tripped if tripped else 'no trip, %s %.1f Hz' % (s, hz)))
        return tripped

    try:
        log('attack pairs start: %d pairs, hold %d s, settle %d s, order %s' % (a.pairs, a.hold, a.settle, a.order))
        if not recover(): log('drive not running - abort'); return 1
        order = [x.strip() == 'on' for x in a.order.split(',')]
        for n in range(a.pairs):
            pn = a.start_pair + n
            for on in order:
                if not recover(): log('drive not at speed before the shot - abort'); return 3
                shed(on); time.sleep(3)
                tag = '%s%d' % ('A' if on else 'B', pn)
                tripped = shot(tag, on)
                if on is False: shed(True)          # never leave the shed off after a B
                if tripped or state()[0] != 'ON':
                    time.sleep(10)
                    if not recover(): log('could not recover the drive - abort'); return 2
                log('  settling %d s' % a.settle)
                time.sleep(a.settle)
        log('attack pairs done')
        return 0
    finally:
        shed(True)
        relay('all', 'off')
        log('shed restored %s/%s, relays open' % (a.f49, a.f50))

if __name__ == '__main__':
    sys.exit(main())
