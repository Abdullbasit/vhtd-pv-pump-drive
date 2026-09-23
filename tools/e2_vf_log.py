"""E2 - V/f baseline logger for the paper (runs against the 0826 V/f firmware,
whose telemetry map is the N_TEL=128 one in THIS folder's hs300_protocol.py).

The 0826 build has no capture ring, so the bus collapse is logged by polling a
contiguous telemetry block as fast as the link allows (~15-20 Hz at 115200):

    VDC IDC PDC ... STS MODE FAULT_FLAGS FREQ SET_FREQ MOD_IDX TEMP STOP_REASON

    python e2_vf_log.py COM11                    # log until Ctrl-C
    python e2_vf_log.py COM11 --start 38         # MANUAL mode, 38 Hz, START, then log
    python e2_vf_log.py COM11 --stop             # STOP the drive and exit

Everything goes to e2_vf_<date>.csv; a state change or a fault is also printed
with its timestamp so the trip instant is in the console too.
"""
import sys, time, csv, argparse, datetime
import hs300_protocol as P

T = P.TEL_BY_NAME
FIRST, LAST = T['VDC'], T['STOP_REASON']          # one contiguous block
NAMES = [r[1] for r in P.TELEMETRY if FIRST <= r[0] <= LAST]
EXTRA = ['ADC_B_RAW', 'ADC_B_OFS', 'XSPARE5', 'ISR_CNT']   # 125,126,127,122 = E2b diag: fmin(engaged), vmin, n, starts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port')
    ap.add_argument('--baud', type=int, default=9600)
    ap.add_argument('--start', type=float, metavar='HZ',
                    help='set MANUAL mode + FREQ_SP=HZ and START before logging')
    ap.add_argument('--mppt', action='store_true',
                    help='set MPPT mode (as fielded before 2026-08-30) and START before logging')
    ap.add_argument('--stop', action='store_true', help='STOP the drive and exit')
    ap.add_argument('--tag', default='', help='text put in the CSV name')
    a = ap.parse_args()

    L = P.Link(a.port, a.baud, 'rs485', retries=1); L.open()
    # a dropped frame must cost ~0.3 s, not 3 s: the trip is over in less
    L.read_telemetry = lambda addr, cnt: (lambda r: P.Link._floats(r[3]) if r and r[2] == cnt else None)(
        L._txn(L._frame(P.READ_TEL, addr, cnt), timeout=0.3))
    m = L.ping()
    if m is None:
        sys.exit('no reply on %s @ %d' % (a.port, a.baud))
    print('app magic %s  (0826 V/f map, N_TEL=%d)' % (hex(m), P.N_TEL))

    if a.stop:
        print('STOP ->', L.command('STOP')); L.close(); return 0

    if a.start is not None or a.mppt:
        if a.mppt:
            print('MODE MPPT ->', L.write_setting(P.SET_BY_NAME['MODE'], 1))
        else:
            print('MODE MANUAL ->', L.write_setting(P.SET_BY_NAME['MODE'], 0))
            print('FREQ_SP %.1f ->' % a.start, L.write_setting(P.SET_BY_NAME['FREQ_SP'], a.start))
        time.sleep(0.2)
        print('RESET_FAULT ->', L.command('RESET_FAULT')); time.sleep(0.3)
        print('START ->', L.command('START'))

    fn = 'e2_vf_%s%s.csv' % (datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
                             ('_' + a.tag) if a.tag else '')
    f = open(fn, 'w', newline=''); w = csv.writer(f)
    w.writerow(['t_s', 'clock'] + NAMES + EXTRA)
    print('logging to', fn, '- Ctrl-C to stop the LOG (the drive keeps running)')
    t0 = time.time(); last = None; extra = [''] * len(EXTRA); next_extra = 0; n = 0
    FAST_N = T['PDC'] - FIRST + 1                 # VDC IDC PDC every loop (~25 Hz at 9600)
    SLOW_A, SLOW_N = T['STS'], LAST - T['STS'] + 1   # STS..STOP_REASON 4x a second
    slow = [0.0] * SLOW_N; next_slow = 0
    try:
        while True:
            v = L.read_telemetry(FIRST, FAST_N)
            if v is None:
                continue
            t = time.time() - t0
            if t >= next_slow:
                sv = L.read_telemetry(SLOW_A, SLOW_N)
                if sv: slow = sv
                next_slow = t + 0.25
            if t >= next_extra:
                e = [L.read_telemetry(T[nm], 1) for nm in EXTRA]
                extra = [x[0] if x else '' for x in e]
                next_extra = t + 1.0
            full = list(v) + [0.0] * (SLOW_A - T['PDC'] - 1) + list(slow)
            w.writerow(['%.3f' % t, datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]]
                       + ['%.3f' % x for x in full] + extra)
            n += 1
            d = dict(zip(NAMES, full))
            key = (int(d['STS']), int(d['FAULT_FLAGS']), int(d['STOP_REASON']))
            if key != last or n % 100 == 0:
                print('%8.2fs  Vdc %6.1f  Idc %6.2f  P %6.0f W  f %5.2f  m %.3f  %s  flags %d  stop %d'
                      % (t, d['VDC'], d['IDC'], d['PDC'], d['FREQ'], d['MOD_IDX'],
                         P.STATE_NAMES[int(d['STS'])] if int(d['STS']) < len(P.STATE_NAMES) else d['STS'],
                         key[1], key[2]), flush=True)
                last = key
            if n % 200 == 0:
                f.flush()
    except KeyboardInterrupt:
        pass
    f.close(); L.close()
    print('%d samples, %.1f Hz -> %s' % (n, n / max(time.time() - t0, 1e-3), fn))
    return 0


if __name__ == '__main__':
    sys.exit(main())
