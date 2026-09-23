"""The broken-cloud day 2026-09-11, minimal: array power and DC-link voltage.
No text over the curves: shot labels in a strip above, level labels in the right margin,
everything else in the caption."""
import csv, os, datetime as dt, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as md
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
RUN = os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260911')
rows = list(csv.DictReader(open(os.path.join(RUN, 'solar_day_20260911.csv'))))
def col(n):
    out = []
    for r in rows:
        try: out.append(float(r[n]))
        except Exception: out.append(np.nan)
    return np.array(out)
tt = np.array([dt.datetime.strptime(r['iso'], '%Y-%m-%d %H:%M:%S') for r in rows])
P = col('P_W')/1000; V = col('VDC')
day = dt.datetime(2026, 9, 11); D = lambda h, m=0: day.replace(hour=h, minute=m)
idx = list(csv.DictReader(open(os.path.join(RUN, 'ring', 'index.csv'))))
eng = [(dt.datetime.strptime('2026-09-11 ' + x['start'][:8], '%Y-%m-%d %H:%M:%S'), float(x['ch2_min']), float(x['ch0_min']))
       for x in idx if x['start'] and x['ch2_min'] and float(x['ch2_min']) < 0.9]
shots = [('07:54:12', 'A7', 0), ('08:01:01', 'B7', 1), ('08:17:15', 'A8', 0), ('08:24:01', 'B8', 1), ('10:11:24', 'A9', 0),
         ('10:18:32', 'B9', 1), ('10:59:41', 'A10', 0), ('11:06:49', 'B10', 1), ('14:37:08', 'L1', 0)]
shot_t = [dt.datetime.strptime('2026-09-11 ' + s[0], '%Y-%m-%d %H:%M:%S') for s in shots]
nat = [e for e in eng if e[0] >= D(7) and not any(abs((e[0] - s).total_seconds()) < 240 for s in shot_t)]
fig = plt.figure(figsize=(7.2, 5.2)); gs = fig.add_gridspec(3, 1, height_ratios=[0.22, 1, 1.15], hspace=0.06)
lab = fig.add_subplot(gs[0]); ax0 = fig.add_subplot(gs[1]); ax1 = fig.add_subplot(gs[2], sharex=ax0)
lab.set_xlim(D(5, 45), D(19, 10)); lab.set_ylim(0, 1); lab.axis('off'); ax0.set_xlim(D(5, 45), D(19, 10))
for (tstr, name, trip), t0 in zip(shots, shot_t):
    c = '#c62828' if trip else '#2e7d32'
    lab.text(t0, 0.78 if not trip else 0.18, name, fontsize=6.5, color=c, ha='center', va='center')
    for a in (ax0, ax1): a.axvline(t0, color=c, lw=0.6, alpha=0.7)
ax0.plot(tt, P, color='#1f4e79', lw=0.6); ax0.set_ylabel('array power (kW)'); ax0.set_ylim(0, 16); ax0.tick_params(labelbottom=False)
ax1.plot(tt, V, color='#4a4e55', lw=0.5); ax1.set_ylabel('DC-link voltage (V)'); ax1.set_ylim(180, 560)
for y, text in ((416, 'HI'), (260, 'LO'), (200, 'UV trip')):
    ax1.axhline(y, ls='--', color='#b0413e', lw=0.6)
    ax1.text(1.005, (y - 180)/380, text, transform=ax1.transAxes, fontsize=6.5, color='#b0413e', va='center', ha='left', clip_on=False)
for t, k, vmin in nat:
    ax1.plot([t, t], [182, 182 + 70*(1 - k)], color='#1565c0', lw=1.3, solid_capstyle='butt')
ax1.set_xlabel('2026-09-11, time of day'); ax1.xaxis.set_major_formatter(md.DateFormatter('%H:%M'))
for a in (ax0, ax1): a.grid(alpha=0.25)
fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig16_cloudy_day_20260911.png'), dpi=300, bbox_inches='tight'); print('fig16 saved', len(nat))
