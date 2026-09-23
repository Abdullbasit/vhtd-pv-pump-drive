"""E5 - yield under V/f with the flow meter, 2026-09-14.

solar_day.py cannot talk to the 0826 V/f build (its map is N_TEL=128), so this
is the V/f-side twin: every PERIOD s it reads the V/f telemetry block and the
Modbus flow meter on the same RS485 bus (unit --flow, registers 1..12 as in
solar_day.py), accumulates Wh and m3, and writes e5_vf_<date>.csv. The L/Wh
per block is computed afterwards against the FOC blocks solar_day logged.

    python e5_vf_day.py COM11 --mppt         # START in MPPT, then log
    python e5_vf_day.py COM11                # just log
"""
import sys, os, time, csv, argparse, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, '..', '..', 'hs300v2_foc_ota_001', 'PC_AGENT_PY'))
import hs300_protocol as P
import modbus_rtu
from solar_day import raw_read

T = P.TEL_BY_NAME
FIRST, LAST = T['VDC'], T['STOP_REASON']
NAMES = [r[1] for r in P.TELEMETRY if FIRST <= r[0] <= LAST]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port'); ap.add_argument('--baud', type=int, default=9600)
    ap.add_argument('--flow', type=int, default=1, help='flow meter Modbus unit (0 = none)')
    ap.add_argument('--period', type=float, default=3.0)
    ap.add_argument('--mppt', action='store_true'); ap.add_argument('--outdir', default='.')
    ap.add_argument('--tag', default='')
    a = ap.parse_args()
    L = P.Link(a.port, a.baud, 'rs485', retries=1); L.open()
    m = L.ping()
    if m is None: sys.exit('no reply from the drive')
    print('drive magic %s (V/f map)' % hex(m))
    if a.mppt:
        print('MODE MPPT ->', L.write_setting(P.SET_BY_NAME['MODE'], 1)); time.sleep(0.2)
        print('RESET_FAULT ->', L.command('RESET_FAULT')); time.sleep(0.3)
        print('START ->', L.command('START'))
    fn = os.path.join(a.outdir, 'e5_vf_%s%s.csv' % (datetime.datetime.now().strftime('%Y%m%d_%H%M%S'), ('_' + a.tag) if a.tag else ''))
    f = open(fn, 'w', newline=''); w = csv.writer(f)
    w.writerow(['iso', 't_s', 'VDC', 'IDC', 'P_W', 'hz', 'modidx', 'sts', 'Q_m3h', 'meter_m3', 'kWh', 'm3'])
    print('logging to', fn)
    t0 = time.time(); tprev = None; E_J = 0.0; V_m3 = 0.0; n = 0
    try:
        while True:
            tel = L.read_telemetry(FIRST, LAST - FIRST + 1)
            g = raw_read(L.ser, a.flow, 1, 12) if a.flow else None
            now = time.time()
            q = modbus_rtu.f32(g, 0, 'cdab') if g else None
            tot = modbus_rtu.total(modbus_rtu.i32(g, 8, 'cdab'), modbus_rtu.f32(g, 10, 'cdab')) if g and len(g) >= 12 else None
            if tel is None:
                time.sleep(0.5); continue
            d = dict(zip(NAMES, tel))
            if tprev is not None:
                dt = now - tprev
                E_J += d['PDC'] * dt
                if q is not None and q > 0: V_m3 += q * dt / 3600.0
            tprev = now
            row = [datetime.datetime.now().isoformat(timespec='seconds'), '%.1f' % (now - t0),
                   '%.1f' % d['VDC'], '%.2f' % d['IDC'], '%.0f' % d['PDC'], '%.2f' % d['FREQ'], '%.3f' % d['MOD_IDX'],
                   int(d['STS']), ('%.2f' % q) if q is not None else '', ('%.3f' % tot) if tot is not None else '',
                   '%.4f' % (E_J / 3.6e6), '%.4f' % V_m3]
            w.writerow(row); n += 1
            if n % 20 == 0: f.flush()
            print('  %s  %-6s %5.1f Hz  P %6.0f W  Vdc %5.0f  Q %6s  %.3f m3  %.3f kWh  %s L/Wh'
                  % (row[0][11:], P.STATE_NAMES[int(d['STS'])] if int(d['STS']) < len(P.STATE_NAMES) else d['STS'],
                     d['FREQ'], d['PDC'], d['VDC'], row[8] or '--', V_m3, E_J / 3.6e6,
                     ('%.2f' % (V_m3 * 1e6 / (E_J / 3.6) )) if E_J > 3.6e5 else '--'), flush=True)
            time.sleep(max(0.0, a.period - (time.time() - now)))
    except KeyboardInterrupt:
        pass
    f.close(); L.close(); print('done ->', fn)


if __name__ == '__main__':
    main()
