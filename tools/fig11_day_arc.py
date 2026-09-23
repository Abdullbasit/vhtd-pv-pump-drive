"""Day arc 2026-09-10 with every disturbance numbered and a key under the figure."""
import csv, os, datetime as dt, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt, matplotlib.dates as md
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
RUN = os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260910')
rows = list(csv.DictReader(open(os.path.join(RUN, 'solar_day_20260910.csv'))))
def col(n):
    out = []
    for r in rows:
        try: out.append(float(r[n]))
        except Exception: out.append(np.nan)
    return np.array(out)
tt = np.array([dt.datetime.strptime(r['iso'], '%Y-%m-%d %H:%M:%S') for r in rows])
P = col('P_W')/1000; F = col('f_rot'); Q = col('Q_m3h')
day = dt.datetime(2026, 9, 10)
m = (tt >= day.replace(hour=10, minute=30)) & (tt <= day.replace(hour=19))
shots = [('10:46:46', 'A1 2.8 kW step', 0), ('10:53:14', 'A2 5.1 kW step', 0), ('10:57:50', 'A2 repeat', 0), ('11:03:28', 'A3 7.9 kW step', 0),
         ('11:08:33', 'A4 string out', 0), ('11:15:15', 'A5 10.4 kW step', 0), ('11:21:15', 'B1 string out, droop off', 0), ('11:27:25', 'B2 10.4 kW, droop off', 0),
         ('11:32:00', 'B3 string+10.4 kW, off', 1), ('11:44:40', 'A6 string+10.4 kW, on', 0), ('12:01:47', "A2' string+bank, on", 0), ('12:08:42', "B2' string+bank, off", 1),
         ('12:18:45', "A3' string+bank, on", 0), ('12:25:32', "B3' string+bank, off", 1), ('12:37:24', 'A7 load, then string out/in, on', 0), ('12:49:03', 'B7 load, then string out/in, off', 1),
         ('14:24:17', 'A4" string+bank, on', 0), ('14:31:05', 'B4" string+bank, off', 1), ('15:34:37', 'A5" string+bank, on', 0), ('15:41:23', 'B5" string+bank, off', 1), ('16:03:58', 'A6" string+bank, on', 0)]
fig, ax = plt.subplots(3, 1, figsize=(7.2, 8.0), sharex=True)
ax[0].plot(tt[m], P[m], color='#1f4e79', lw=0.8); ax[0].set_ylabel('DC power (kW)'); ax[0].set_ylim(0, 17.5)
ax[1].plot(tt[m], F[m], color='#444', lw=0.8); ax[1].set_ylabel('rotor speed (Hz)'); ax[1].axhline(26.4, ls='--', color='#c55', lw=0.8)
ax[1].text(day.replace(hour=17, minute=20), 27.5, 'pump cut-in 26.4 Hz', fontsize=6.5, color='#c55'); ax[1].set_ylim(0, 50)
ax[2].plot(tt[m], np.clip(Q[m], 0, None), color='#2e7d32', lw=0.8); ax[2].set_ylabel('flow (m³/h)'); ax[2].set_ylim(0, 60)
key = []
for i, (tstr, lab, trip) in enumerate(shots, 1):
    t0 = dt.datetime.strptime('2026-09-10 ' + tstr, '%Y-%m-%d %H:%M:%S'); c = '#c62828' if trip else '#2e7d32'
    for a in ax: a.axvline(t0, color=c, lw=0.7, alpha=0.8)
    ytxt = 16.4 if i % 2 else 14.6
    ax[0].text(t0, ytxt, str(i), fontsize=5.8, color='white', ha='center', va='center',
               bbox=dict(boxstyle='circle,pad=0.15', fc=c, ec='none'))
    key.append('%2d  %s%s' % (i, lab, '  (trip)' if trip else ''))
ax[0].axvspan(day.replace(hour=10, minute=40), day.replace(hour=13, minute=0), color='#ddd', alpha=0.4, lw=0)
ax[0].text(day.replace(hour=13, minute=5), 3.0, 'shaded: controlled-test block 10:40-13:00; numbered lines are the shots (key below)\ngreen = droop on (no trip)   red = droop off (trip and restart)', fontsize=6.2, color='#333')
ax[0].annotate('clear-sky afternoon:\ntracker follows the sun down', (day.replace(hour=16, minute=30), 6.0), xytext=(day.replace(hour=17, minute=10), 10.5), fontsize=6.5, arrowprops=dict(arrowstyle='->', lw=0.7))
ax[2].annotate('dusk: clean linger stops and 90 s probes,\nno fault (Section VII-B)', (day.replace(hour=17, minute=25), 3), xytext=(day.replace(hour=14, minute=50), 22), fontsize=6.5, arrowprops=dict(arrowstyle='->', lw=0.7))
ax[2].set_xlabel('2026-09-10, time of day'); ax[2].xaxis.set_major_formatter(md.DateFormatter('%H:%M'))
for a in ax: a.grid(alpha=0.3)
fig.suptitle('The test day 2026-09-10: power, rotor speed and flow, with every disturbance marked', fontsize=9)
cols = [key[0:11], key[11:21]]
for x, c in zip((0.06, 0.54), cols):
    fig.text(x, 0.005, '\n'.join(c), fontsize=8.2, va='bottom', family='DejaVu Sans Mono')
fig.tight_layout(rect=(0, 0.20, 1, 1)); fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig11_day_arc_20260910.png'), dpi=300); print('fig11 saved')
