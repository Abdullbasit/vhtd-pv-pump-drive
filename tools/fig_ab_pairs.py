"""Two A/B figures from the 2026-09-10 80 ms ring records:
 fig_ab_B3_A6.png     : B3 droop off (overcurrent trip)  |  A6 droop on (ride-through), string out + 10.4 kW
 fig_steps_5_10kW.png : 5.1 kW step, droop armed not reached  |  10.4 kW step, droop engaged"""
import csv, os, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); R = os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260910', 'ring')
def ring(name):
    rows = list(csv.DictReader(open(os.path.join(R, name))))
    t = np.array([float(r['t_to_trip_s']) for r in rows]) if 't_to_trip_s' in rows[0] else None
    if t is None:
        t = np.array([float(r['t_s']) for r in rows]); v0 = np.array([float(r['vDcInst']) for r in rows]); e = np.argmax(np.diff(v0) < -15) + 1; t = t - t[e]
    v = np.array([float(r['vDcInst']) for r in rows]); i = np.array([float(r['idc_units']) for r in rows]); k = np.array([float(r['iq_shed']) for r in rows])
    return t, v, i, k
def panel(ax, name, title, span, trip=False):
    t, v, i, k = ring(name); m = (t >= span[0]) & (t <= span[1])
    ax[0].plot(t[m], v[m], color='#1f4e79', lw=1.1); ax[0].set_ylim(180, 500); ax[0].set_title(title, fontsize=8)
    for y, l in ((416, 'HI'), (260, 'LO'), (200, 'UV trip')): ax[0].axhline(y, ls='--', color='#b0413e', lw=0.6); ax[0].text(span[1], y + 4, l, fontsize=6, color='#b0413e', ha='right')
    ax[1].plot(t[m], i[m], color='#2e7d32', lw=1.1); ax[1].set_ylim(0, 35)
    ax[2].plot(t[m], k[m], color='#c62828', lw=1.2); ax[2].set_ylim(0, 1.1)
    for a in ax: a.grid(alpha=0.3); a.axvline(0, color='#999', ls=':', lw=0.8)
    if trip:
        for a in ax: a.axvspan(0, span[1], color='#c62828', alpha=0.06, lw=0)
def make(left, right, out, xlabel_l, xlabel_r):
    fig, ax = plt.subplots(3, 2, figsize=(7.2, 5.4), sharex='col')
    panel(ax[:, 0], *left); panel(ax[:, 1], *right)
    ax[0, 0].set_ylabel('DC-link voltage (V)'); ax[1, 0].set_ylabel('DC current (A)'); ax[2, 0].set_ylabel('droop factor k')
    ax[2, 0].set_xlabel(xlabel_l); ax[2, 1].set_xlabel(xlabel_r)
    fig.tight_layout(); fig.savefig(os.path.join(ROOT, 'paper_figs', out), dpi=300); print(out)
make(('trip_113205.csv', '(a) B3, droop off: string out + 10.4 kW, 11:32', (-1.5, 0.05), True),
     ('ring_114451.csv', '(b) A6, droop on: string out + 10.4 kW, 11:44', (-1.0, 6.0)),
     'fig_ab_B3_A6.png', 'time to the overcurrent trip (s)', 'time from the string opening (s)')
make(('ring_105802.csv', '(a) 5.1 kW resistive step, droop armed, not reached, 10:57', (-1.0, 6.0)),
     ('ring_111527.csv', '(b) 10.4 kW resistive step, droop engaged, 11:15', (-1.0, 6.0)),
     'fig_steps_5_10kW.png', 'time from the bank closing (s)', 'time from the bank closing (s)')
