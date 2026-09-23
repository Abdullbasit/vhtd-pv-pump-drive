#!/usr/bin/env python3
"""paper_figs.py - the figures for PAPER_DRAFT_20260910.md, straight from the
ring files and the day CSVs. Writes ../paper_figs/figNN_*.png (150 dpi) and a
figs.md with one caption per figure. No pandas: csv + numpy + matplotlib."""
import os, csv, glob, datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'paper_figs'); os.makedirs(OUT, exist_ok=True)
R = lambda day, f: os.path.join(HERE, 'runs', day, f)
caps = []

plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': 0.3, 'figure.dpi': 150})

def ring(path):
    rows = list(csv.DictReader(open(path)))
    if 't_to_trip_s' in rows[0]:
        t = np.array([float(r['t_to_trip_s']) for r in rows])
    else:
        t = np.array([float(r['t_s']) for r in rows]); t = t - t[0]
    v = np.array([float(r['vDcInst']) for r in rows])
    i = np.array([float(r['idc_units']) for r in rows]) if 'idc_units' in rows[0] else None
    k = np.array([float(r['iq_shed']) for r in rows]) if 'iq_shed' in rows[0] else None
    f = np.array([float(r['set_freq']) for r in rows]) if 'set_freq' in rows[0] else None
    return t, v, i, k, f

def edge_fig(path, name, title, t0_at=None, span=(-1.0, 6.0)):
    t, v, i, k, f = ring(path)
    if t0_at is None:
        below = np.where(v < 465)[0]
        t0 = t[below[0]] if len(below) else t[0]
    else:
        t0 = t0_at
    tt = t - t0
    m = (tt >= span[0]) & (tt <= span[1])
    fig, ax = plt.subplots(3, 1, figsize=(6.5, 5.2), sharex=True)
    ax[0].plot(tt[m], v[m], color='#1f4e79'); ax[0].set_ylabel('DC link (V)')
    ax[0].axhline(416, ls='--', color='#c55', lw=0.8); ax[0].text(span[1], 418, 'HI 0.80 Voc', ha='right', va='bottom', fontsize=7, color='#c55')
    ax[0].axhline(260, ls='--', color='#c55', lw=0.8); ax[0].text(span[1], 262, 'LO 0.50 Voc', ha='right', va='bottom', fontsize=7, color='#c55')
    if i is not None:
        ax[1].plot(tt[m], i[m], color='#2e7d32'); ax[1].set_ylabel('DC current (A)')
        ax1b = ax[1].twinx(); ax1b.plot(tt[m], v[m] * i[m] / 1000, color='#888', lw=0.8); ax1b.set_ylabel('kW', color='#888'); ax1b.grid(False)
    if k is not None:
        ax[2].plot(tt[m], k[m], color='#c62828'); ax[2].set_ylabel('droop factor k'); ax[2].set_ylim(0, 1.05)
    ax[2].set_xlabel('time from the edge (s)')
    fig.suptitle(title, fontsize=10); fig.tight_layout()
    p = os.path.join(OUT, name + '.png'); fig.savefig(p); plt.close(fig)
    return p

# ---- Fig 7: 5.1 kW step, droop on, constant-power behaviour -----------------
p = edge_fig(R('20260910', 'ring/ring_105802.csv'), 'fig07_step_5kW',
             '5.1 kW resistive step, droop armed (not reached) - 2026-09-10 10:57:53')
caps.append(('fig07', 'Resistive step of 5.1 kW onto a 14.2 kW operating point at 80 ms. The DC-link voltage falls 472 to 435 V in 160 ms while the drive current stays at 30 A: the constant-power characteristic. The droop line at 416 V is not reached; the tracker\'s sag retreat acts after ~1 s.'))

# ---- Fig 8: 10.4 kW step, droop on ------------------------------------------
p = edge_fig(R('20260910', 'ring/ring_111527.csv'), 'fig08_step_12kW_droop',
             '10.4 kW resistive step, droop on - 2026-09-10 11:15:18')
caps.append(('fig08', '10.4 kW step with the droop enabled. Bus 474 to 384 V within one sample; k to 0.79 in the same sample and the drive current cut 30 to 25 A; the droop holds the bus at 390-400 V for 2.5 s until the tracker\'s retreat catches up.'))

# ---- Fig 9: B3 trip ring ----------------------------------------------------
t, v, i, k, f = ring(R('20260910', 'ring/trip_113205.csv'))
m = t >= -1.5
fig, ax = plt.subplots(2, 1, figsize=(6.5, 4), sharex=True)
ax[0].plot(t[m], v[m], color='#1f4e79'); ax[0].set_ylabel('DC link (V)'); ax[0].axhline(200, ls='--', color='#c55', lw=0.8); ax[0].text(0, 205, 'UV trip 200 V', ha='right', fontsize=7, color='#c55')
ax[1].plot(t[m], i[m], color='#2e7d32'); ax[1].set_ylabel('DC current (A)'); ax[1].set_xlabel('time to the overcurrent trip (s)')
fig.suptitle('Combined disturbance (string out + 10.4 kW), droop OFF: OC trip - 2026-09-10 11:32:05', fontsize=10); fig.tight_layout()
fig.savefig(os.path.join(OUT, 'fig09_B3_trip.png')); plt.close(fig)
caps.append(('fig09', 'The frozen capture ring of shot B3 (droop disabled). The bus falls 471 to 410 V in 0.4 s with the drive current unchanged at 30 A; the current loop loses authority and the drive trips on overcurrent (dq tracking) with the bus still at 411 V - far above the 200 V undervoltage trip.'))

# ---- Fig 10: A6 combined, droop on ------------------------------------------
p = edge_fig(R('20260910', 'ring/ring_114451.csv'), 'fig10_A6_combined_droop',
             'Combined disturbance (string out + 10.4 kW), droop ON: ride-through - 2026-09-10 11:44:45', span=(-1.0, 6.0))
caps.append(('fig10', 'The same combined disturbance with the droop enabled (shot A6). The string leaves at t=0 (477 to 413-424 V), the bank lands 0.4 s later (to 325 V); k drops 0.98 to 0.40 within one 80 ms sample, the current 29.5 to 14.1 A, and the drive settles at 331 V (0.64 Voc) for the 90 s. No trip.'))

# ---- Fig 5: 2026-09-08 dawn limit cycle -------------------------------------
files = sorted(glob.glob(R('20260908', 'ring/ring_065[3-8]*.csv')))
T, V, K, F = [], [], [], []
for fpath in files:
    rows = list(csv.DictReader(open(fpath)))
    for r in rows:
        hh, mm, ss = r['iso'].split(':'); T.append(int(mm) * 60 + float(ss) - 53 * 60)
        V.append(float(r['vDcInst'])); K.append(float(r['iq_shed'])); F.append(float(r.get('set_freq') or r.get('idc_units')))
T, V, K, F = map(np.array, (T, V, K, F))
fig, ax = plt.subplots(3, 1, figsize=(7, 5.2), sharex=True)
ax[0].plot(T, V, '.', ms=2, color='#1f4e79'); ax[0].set_ylabel('DC link (V)')
ax[1].plot(T, F, '.', ms=2, color='#2e7d32'); ax[1].set_ylabel('DC current (A)')
ax[2].plot(T, K, '.', ms=2, color='#c62828'); ax[2].set_ylabel('droop factor k'); ax[2].set_xlabel('seconds from 06:53:00, 2026-09-08')
fig.suptitle('MPP-approach limit cycle at dawn, clear sky: eleven collapses at 26 s', fontsize=10); fig.tight_layout()
fig.savefig(os.path.join(OUT, 'fig05_limit_cycle.png')); plt.close(fig)
caps.append(('fig05', 'Dawn of 2026-09-08 (80 ms record, gaps are the ring pulls). The tracker climbs 0.2 Hz per verdict into the array\'s short-circuit current (~7 A), the bus collapses 488 to 300 V in 0.5 s, the droop catches it (k 0.21), the bus returns to Voc, the droop releases and the tracker climbs back - eleven times.'))

# ---- Fig 6: 2026-09-07 real clouds --------------------------------------------
idx = list(csv.DictReader(open(R('20260907', 'ring/index.csv'))))
ep = [(x['start'][:8], float(x['ch0_min']), float(x['ch2_min'])) for x in idx if x['start'] and x['ch2_min'] and float(x['ch2_min']) < 0.95]
fig, ax = plt.subplots(figsize=(6.5, 3.2))
tt = [datetime.datetime.strptime(e[0], '%H:%M:%S') for e in ep]
ax.scatter(tt, [e[2] for e in ep], c=[e[1] for e in ep], cmap='viridis', s=28)
ax.set_ylabel('droop factor k_min per 18 s window'); ax.set_ylim(0, 1)
ax.set_title('Real clouds, 2026-09-07: every droop engagement (colour = bus minimum, V)', fontsize=10)
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(os.path.join(OUT, 'fig06_real_clouds.png')); plt.close(fig)
caps.append(('fig06', 'All droop engagements on the cloudy day 2026-09-07 (k_min per 18 s ring window; colour is the bus minimum). Seven deep episodes to k 0.29-0.33 at 313-318 V; every one ridden through, zero closed-loop trips after HI was set to 0.80 at 07:35.'))

# ---- Fig 11: 2026-09-10 day arc with the disturbances --------------------------
rows = list(csv.DictReader(open(R('20260910', 'solar_day_20260910.csv'))))
def col(name, f=float):
    out = []
    for r in rows:
        try: out.append(f(r[name]))
        except Exception: out.append(np.nan)
    return np.array(out)
tt = [datetime.datetime.strptime(r['iso'], '%Y-%m-%d %H:%M:%S') for r in rows]
P, Vd, Hz, Q = col('P_W'), col('VDC'), col('f_rot'), col('Q_m3h')
fig, ax = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
ax[0].plot(tt, P / 1000, lw=0.6, color='#1f4e79'); ax[0].set_ylabel('DC power (kW)')
ax[1].plot(tt, Hz, lw=0.6, color='#555'); ax[1].set_ylabel('rotor (Hz)'); ax[1].axhline(26.4, ls='--', lw=0.7, color='#c55')
ax[2].plot(tt, Q, lw=0.6, color='#2e7d32'); ax[2].set_ylabel('flow (m3/h)')
marks = [l for l in open(R('20260910', 'marks.log')) if 'MARK' in l and ('COMBINED' in l or 'kW' in l or 'string' in l.lower()) and 'result' not in l and 'clamp' not in l]
for l in marks:
    tm = datetime.datetime.strptime('2026-09-10 ' + l[:8], '%Y-%m-%d %H:%M:%S')
    for a in ax: a.axvline(tm, color='#c62828', lw=0.5, alpha=0.6)
ax[2].set_xlabel('2026-09-10 (red lines: disturbances)'); fig.autofmt_xdate(); fig.tight_layout()
fig.savefig(os.path.join(OUT, 'fig11_day_arc_20260910.png')); plt.close(fig)
caps.append(('fig11', 'The controlled-test day 2026-09-10: DC power, rotor speed (dashed: pump cut-in 26.4 Hz) and flow, with every disturbance marked. Droop-off shots end in a trip and a 3-4 min restart; droop-on shots are dips.'))

# ---- Fig 4: 2026-09-08 dawn probes -------------------------------------------
rows = list(csv.DictReader(open(R('20260908', 'solar_day_20260908.csv'))))
rows = [r for r in rows if '2026-09-08 05:50' <= r['iso'] <= '2026-09-08 06:25']
tt = [datetime.datetime.strptime(r['iso'], '%Y-%m-%d %H:%M:%S') for r in rows]
voc = np.array([float(r['mppt_voc'] or 'nan') for r in rows]); st = np.array([int(r['starts'] or 0) for r in rows])
fig, ax = plt.subplots(2, 1, figsize=(6.5, 3.8), sharex=True)
ax[0].plot(tt, voc, '.', ms=2, color='#1f4e79'); ax[0].set_ylabel('Voc at energise (V)')
ax[1].step(tt, st - st[0], where='post', color='#555'); ax[1].set_ylabel('start attempts'); ax[1].set_xlabel('2026-09-08 dawn')
fig.suptitle('Dawn start probes: one clean attempt every 90 s until the array can carry the I-f current (06:18)', fontsize=9); fig.autofmt_xdate(); fig.tight_layout()
fig.savefig(os.path.join(OUT, 'fig04_dawn_probes.png')); plt.close(fig)
caps.append(('fig04', 'Dawn 2026-09-08 with the start probe: nine attempts 05:53-06:16, each stopped cleanly within ~1 s when the bus fell under 0.88 Voc, no fault; the tenth (06:18:07) held once the array reached ~950 W. Voc is re-sampled at every energise and follows the rising sun.'))

with open(os.path.join(OUT, 'figs.md'), 'w', encoding='utf-8') as fh:
    fh.write('# Figures (generated by PC_AGENT_PY/paper_figs.py)\n\n')
    for n, c in sorted(caps):
        fh.write('## %s\n![%s](%s.png)\n\n%s\n\n' % (n, n, [f for f in os.listdir(OUT) if f.startswith(n)][0][:-4], c))
print('figures:', sorted(os.listdir(OUT)))
