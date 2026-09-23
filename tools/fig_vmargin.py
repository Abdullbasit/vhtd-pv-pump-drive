"""Voltage margin through the combined disturbance, droop on (A6) and droop off (B3'),
2026-09-10, from the 3 s telemetry: voltage demand |v_s| against the limit, and i_q."""
import csv, os, datetime as dt, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
rows = list(csv.DictReader(open(os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260910', 'solar_day_20260910.csv'))))
def series(t0, t1):
    out = []
    for r in rows:
        c = r['iso'][11:19]
        if t0 <= c <= t1:
            ts = dt.datetime.strptime(r['iso'], '%Y-%m-%d %H:%M:%S')
            def f(k):
                try: return float(r[k])
                except Exception: return np.nan
            out.append((ts, f('v_dem'), f('vlim'), f('foc_iq'), f('VDC'), f('shed'), r['sts']))
    return out
cases = [('A6, droop on: string out + 10.4 kW, 11:44:40', '11:44:20', '11:45:30', dt.datetime(2026, 9, 10, 11, 44, 40)),
         ("B3′, droop off: string out + 7.9 kW, 12:25:32", '12:25:10', '12:26:20', dt.datetime(2026, 9, 10, 12, 25, 32))]
fig, ax = plt.subplots(2, 2, figsize=(7.2, 4.6), sharex='col')
for j, (title, t0, t1, edge) in enumerate(cases):
    s = series(t0, t1); t = [(x[0] - edge).total_seconds() for x in s]
    vd = [x[1] for x in s]; vl = [x[2] for x in s]; iq = [x[3] for x in s]; sts = [x[6] for x in s]
    a = ax[0, j]; a.plot(t, vl, 's-', ms=3, lw=1, color='#b0413e', label='voltage limit |v_s|_max (from the bus)')
    a.plot(t, vd, 'o-', ms=3, lw=1, color='#1f4e79', label='voltage demand |v_s|')
    a.set_ylim(100, 300); a.set_title(title, fontsize=8); a.grid(alpha=0.3); a.axvline(0, color='#999', ls=':', lw=0.8)
    b = ax[1, j]; b.plot(t, iq, 'o-', ms=3, lw=1, color='#2e7d32'); b.set_ylim(0, 50); b.grid(alpha=0.3); b.axvline(0, color='#999', ls=':', lw=0.8)
    b.set_xlabel('time from the edge (s)')
    for k, st in enumerate(sts):
        if st.startswith('FAULT'):
            for aa in (a, b): aa.axvspan(t[k] - 1.5, t[-1] + 1.5, color='#c62828', alpha=0.08, lw=0)
            a.text(t[k], 285, 'overcurrent trip', fontsize=7, color='#c62828', ha='center'); break
ax[0, 0].set_ylabel('stator voltage (V)'); ax[1, 0].set_ylabel('torque current i_q (A)')
ax[0, 1].legend(*ax[0, 0].get_legend_handles_labels(), fontsize=6.5, loc='lower left', frameon=True, framealpha=0.95, edgecolor='none')
ax[0, 1].annotate('demand exceeds the limit\nas the bus falls', (6, 273), xytext=(14, 160), fontsize=6.5, arrowprops=dict(arrowstyle='->', lw=0.7))
fig.suptitle('Stator-voltage margin through the combined disturbance, 2026-09-10 (3 s telemetry): droop on against droop off', fontsize=8.5)
fig.tight_layout(); fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig_vmargin.png'), dpi=300); print('fig_vmargin saved')
