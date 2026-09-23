"""5.1 kW resistive step, droop armed but not reached (2026-09-10 10:57:53): four clean
panels from the 80 ms ring record - bus voltage, DC current, DC power, droop factor."""
import csv, os, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
rows = list(csv.DictReader(open(os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260910', 'ring', 'ring_105802.csv'))))
t = np.array([float(r['t_s']) for r in rows]); v = np.array([float(r['vDcInst']) for r in rows])
i = np.array([float(r['idc_units']) for r in rows]); k = np.array([float(r['iq_shed']) for r in rows])
edge = np.argmax(np.diff(v) < -15) + 1; t = t - t[edge]
m = (t >= -1.0) & (t <= 6.0)
fig, ax = plt.subplots(4, 1, figsize=(6.5, 6.4), sharex=True)
ax[0].plot(t[m], v[m], color='#1f4e79', lw=1.2); ax[0].set_ylabel('DC-link voltage (V)'); ax[0].set_ylim(380, 490)
ax[0].axhline(416, ls='--', color='#b0413e', lw=0.8); ax[0].text(5.95, 418, 'droop line HI = 0.80 V_oc (416 V)', ha='right', fontsize=7, color='#b0413e')
ax[1].plot(t[m], i[m], color='#2e7d32', lw=1.2); ax[1].set_ylabel('DC current (A)'); ax[1].set_ylim(25, 32)
ax[2].plot(t[m], v[m]*i[m]/1000, color='#6b5f4e', lw=1.2); ax[2].set_ylabel('DC power (kW)'); ax[2].set_ylim(11, 15)
ax[3].plot(t[m], k[m], color='#c62828', lw=1.4); ax[3].set_ylabel('droop factor k'); ax[3].set_ylim(0, 1.1); ax[3].set_yticks([0, 0.5, 1.0])
ax[3].text(5.95, 0.15, 'k = 1.0 throughout: the bus stayed above HI, the droop did not act', ha='right', fontsize=7, color='#c62828')
ax[3].set_xlabel('time from the bank closing (s)')
for a in ax: a.grid(alpha=0.3); a.axvline(0, color='#999', lw=0.7, ls=':')
ax[0].annotate('472 → 435 V in 160 ms', (0.16, 436), xytext=(1.6, 470), fontsize=7.5, arrowprops=dict(arrowstyle='->', lw=0.7))
ax[1].annotate('current stays at 30 A while the bus falls:\nconstant-power behaviour', (0.5, 30.0), xytext=(2.4, 25.5), fontsize=7.5, arrowprops=dict(arrowstyle='->', lw=0.7))
ax[1].annotate('tracker retreats after ~1 s', (1.7, 28.8), xytext=(3.0, 31.0), fontsize=7.5, arrowprops=dict(arrowstyle='->', lw=0.7))
fig.suptitle('5.1 kW resistive step on a 14.2 kW operating point, 2026-09-10 10:57:53 (80 ms record)', fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig07_step_5kW.png'), dpi=300); print('fig07 saved')
