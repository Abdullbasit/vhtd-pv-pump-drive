"""Array I-V / P-V with the load lines - explanatory version, 2026-09-14.
Explicit single-diode form anchored on the measured day: V_oc 519 V (tracker's Voc
capture, 2026-09-10 median), MPP 472 V / 30 A (14.2 kW), I_sc 34 A. One string out
= 2/3 I_sc at the same V_oc (12S3P array)."""
import os, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
Voc, Vmp, Imp, Isc = 519.0, 472.0, 30.0, 34.0
C2 = (Vmp/Voc - 1)/np.log(1 - Imp/Isc); C1 = (1 - Imp/Isc)*np.exp(-Vmp/(C2*Voc))
def I_arr(V, scale=1.0): return scale*Isc*(1 - C1*(np.exp(V/(C2*Voc)) - 1))
V = np.linspace(0, Voc, 600); Ia = np.clip(I_arr(V), 0, None); Ib = np.clip(I_arr(V, 2/3), 0, None)
P = Vmp*Imp; Icpl = P/V[1:]; Iv2 = Imp*(V/Vmp)
fig, ax = plt.subplots(1, 2, figsize=(7.2, 3.4))
a = ax[0]
a.plot(V, Ia, color='#1f4e79', lw=2, label='array, all strings (14.2 kW at the MPP)')
a.plot(V, Ib, color='#1f4e79', lw=1.2, ls='--', label='array, one string out (2/3 I_sc)')
a.plot(V[1:], Icpl, color='k', lw=1.4, label='constant-power load 14.2 kW (FOC; V/f at the ceiling)')
a.plot(V, Iv2, color='#777', lw=1.2, ls=':', label='P ∝ V² load through the same point (resistor; steady-state V/f)')
a.plot([Vmp], [Imp], 'o', color='#c62828', ms=6, zorder=5)
a.annotate('operating point\n472 V, 30 A', (Vmp, Imp), xytext=(437, 41), fontsize=7, arrowprops=dict(arrowstyle='->', lw=0.8))
a.axvspan(0, Vmp, color='#c62828', alpha=0.06)
a.text(12, 57.5, 'left of the knee: no stable point for a\nconstant-power load (eq. 1) — the bus runs away', fontsize=6.5, color='#c62828', va='top')
a.annotate('one string out: the 14.2 kW hyperbola\nnever meets the reduced array', (330, 43), xytext=(70, 44), fontsize=6.5, arrowprops=dict(arrowstyle='->', lw=0.8))
d = np.abs(Iv2 - Ib); k0 = np.searchsorted(V, 200); j = np.argmin(d[k0:]) + k0
a.plot([V[j]], [Iv2[j]], 's', color='#2e7d32', ms=5, zorder=5)
a.annotate('P ∝ V² load: a new point exists\n(%d V, %.0f A)' % (V[j], Iv2[j]), (V[j], Iv2[j]), xytext=(40, 27), fontsize=6.5, arrowprops=dict(arrowstyle='->', lw=0.8))
a.set_xlim(0, 540); a.set_ylim(0, 60); a.set_xlabel('DC-link voltage (V)'); a.set_ylabel('current (A)')
a.set_title('(a) array I–V and the load lines', fontsize=9)
a.legend(fontsize=5.6, loc='lower left', frameon=True, framealpha=0.95, edgecolor='none'); a.grid(alpha=0.3)
b = ax[1]
b.plot(V, V*Ia/1000, color='#1f4e79', lw=2, label='array power, all strings')
b.plot(V, V*Ib/1000, color='#1f4e79', lw=1.2, ls='--', label='one string out')
b.axhline(P/1000, color='k', lw=1.4, label='constant-power demand 14.2 kW')
b.plot(V, V*Iv2/1000, color='#777', ls=':', lw=1.2, label='P ∝ V² demand')
b.plot([Vmp], [P/1000], 'o', color='#c62828', ms=6, zorder=5)
pk = np.max(V*Ib)/1000
b.annotate('reduced array peaks at %.1f kW:\nthe 14.2 kW demand cannot be met\nat any voltage' % pk, (V[np.argmax(V*Ib)], pk), xytext=(60, 16.5), fontsize=6.5, arrowprops=dict(arrowstyle='->', lw=0.8))
b.set_xlim(0, 540); b.set_ylim(0, 20); b.set_xlabel('DC-link voltage (V)'); b.set_ylabel('power (kW)')
b.set_title('(b) array P–V and the demand lines', fontsize=9)
b.legend(fontsize=5.8, loc='lower left', frameon=True, framealpha=0.95, edgecolor='none'); b.grid(alpha=0.3)
fig.suptitle('Array of the test day 2026-09-10, clear sky, 10:45–13:00: 14.2 kW at the MPP, V_oc 519 V, V_mp 472 V', fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(ROOT, 'paper_figs', 'fig02_iv.png'), dpi=300)
print('fig02_iv saved')
