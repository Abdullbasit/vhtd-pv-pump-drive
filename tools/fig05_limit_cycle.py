"""MPP-approach limit cycle, dawn 2026-09-08 (80 ms ring records) - readable version:
full 5 min as lines (gaps = ring pulls), plus one cycle zoomed."""
import csv, glob, os, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
files = sorted(glob.glob(os.path.join(ROOT, 'PC_AGENT_PY', 'runs', '20260908', 'ring', 'ring_065[3-8]*.csv')))
T, V, I, K = [], [], [], []
for f in files:
    for r in csv.DictReader(open(f)):
        hh, mm, ss = r['iso'].split(':'); T.append(int(mm)*60 + float(ss) - 53*60)
        V.append(float(r['vDcInst'])); K.append(float(r['iq_shed'])); I.append(float(r.get('idc_units') or r.get('set_freq')))
    T.append(np.nan); V.append(np.nan); I.append(np.nan); K.append(np.nan)   # break the line at each pull
T, V, I, K = map(np.array, (T, V, I, K))
fig = plt.figure(figsize=(7.2, 5.0)); gs = fig.add_gridspec(3, 2, width_ratios=[2.2, 1], hspace=0.12, wspace=0.28)
L = [fig.add_subplot(gs[i, 0]) for i in range(3)]; R = [fig.add_subplot(gs[i, 1]) for i in range(3)]
for axs, m, ttl in ((L, np.ones_like(T, bool), 'five minutes, eleven collapses at a 26 s period'), (R, (T >= 128) & (T <= 160), 'one cycle, 128–160 s')):
    axs[0].plot(T[m], V[m], color='#1f4e79', lw=0.9); axs[0].set_ylabel('DC link (V)'); axs[0].set_title(ttl, fontsize=8)
    axs[1].plot(T[m], I[m], color='#2e7d32', lw=0.9); axs[1].set_ylabel('DC current (A)')
    axs[2].plot(T[m], K[m], color='#c62828', lw=0.9); axs[2].set_ylabel('droop factor k'); axs[2].set_ylim(0, 1.05)
    for a in axs: a.grid(alpha=0.3)
    axs[2].set_xlabel('seconds from 06:53:00')
    for a in axs[:2]: a.tick_params(labelbottom=False)
L[0].axhline(416, ls='--', color='#c55', lw=0.7); L[0].text(2, 420, 'HI 0.80 V_oc', fontsize=6, color='#c55')
L[0].axhline(260, ls='--', color='#c55', lw=0.7); L[0].text(2, 264, 'LO 0.50 V_oc', fontsize=6, color='#c55')
fig.suptitle('MPP-approach limit cycle at dawn, clear sky, 2026-09-08 (80 ms record; gaps are ring pulls)', fontsize=9)
fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig05_limit_cycle.png'), dpi=300, bbox_inches='tight'); print('fig05 saved', len(files), 'files')
