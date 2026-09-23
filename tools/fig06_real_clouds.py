"""Real clouds 2026-09-07: array power, DC-link voltage and the droop factor over the day.
k from the 80 ms ring windows (minimum per ~18 s window, drawn as a step); every dip is one cloud."""
import csv, os, datetime as dt, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as md
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
RUN = os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260907')
rows = list(csv.DictReader(open(os.path.join(RUN, 'solar_day_20260907.csv'))))
def col(n):
    out = []
    for r in rows:
        try: out.append(float(r[n]))
        except Exception: out.append(np.nan)
    return np.array(out)
tt = np.array([dt.datetime.strptime(r['iso'], '%Y-%m-%d %H:%M:%S') for r in rows])
V = col('VDC'); P = col('P_W')/1000
idx = list(csv.DictReader(open(os.path.join(RUN, 'ring', 'index.csv'))))
win = [(dt.datetime.strptime('2026-09-07 ' + x['start'][:8], '%Y-%m-%d %H:%M:%S'), dt.datetime.strptime('2026-09-07 ' + x['end'][:8], '%Y-%m-%d %H:%M:%S'), float(x['ch2_min']))
       for x in idx if x['start'] and x['end'] and x['ch2_min']]
KT = []; KV = []
for a, b, kmin in win: KT += [a, b]; KV += [kmin, kmin]
day = dt.datetime(2026, 9, 7); D = lambda h, m=0: day.replace(hour=h, minute=m)
fig, ax = plt.subplots(3, 1, figsize=(7.2, 5.8), sharex=True)
ax[0].plot(tt, P, color='#1f4e79', lw=0.6); ax[0].set_ylabel('array power (kW)'); ax[0].set_ylim(0, 16)
ax[1].plot(tt, V, color='#4a4e55', lw=0.5); ax[1].set_ylabel('DC-link voltage (V)'); ax[1].set_ylim(180, 560)
for y, text in ((416, 'HI'), (260, 'LO'), (200, 'UV trip')):
    ax[1].axhline(y, ls='--', color='#b0413e', lw=0.6); ax[1].text(1.005, (y - 180)/380, text, transform=ax[1].transAxes, fontsize=6.5, color='#b0413e', va='center', clip_on=False)
ax[2].plot(KT, KV, color='#c62828', lw=0.8); ax[2].set_ylabel('droop factor k\n(minimum per window)'); ax[2].set_ylim(0, 1.05)
for a in ax:
    a.axvline(D(7, 35), color='#555', ls='--', lw=0.7); a.axvline(D(7, 1), color='#c62828', lw=0.9); a.grid(alpha=0.25)
ax[0].text(D(7, 3), 15.2, 'trip 07:01', fontsize=6.5, color='#c62828', va='top'); ax[0].text(D(7, 38), 12.4, 'HI 0.66 → 0.80 at 07:35', fontsize=6.5, color='#555', va='top')
ax[2].set_xlabel('2026-09-07, time of day'); ax[2].xaxis.set_major_formatter(md.DateFormatter('%H:%M')); ax[2].set_xlim(D(5, 30), D(19, 0))
fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig06_real_clouds.png'), dpi=300, bbox_inches='tight'); print('fig06 saved; windows k<0.9:', sum(1 for w in win if w[2] < 0.9))
