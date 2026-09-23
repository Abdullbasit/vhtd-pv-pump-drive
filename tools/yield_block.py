"""L/Wh over a clock window from solar_day (FOC) or e5_vf_day (V/f) CSVs."""
import csv, sys
def block(path, t0, t1, kind):
    rows=list(csv.DictReader(open(path)))
    E=0; V=0; prev=None; P=[]; Q=[]; hz=[]
    for r in rows:
        clk=r['iso'][11:19]
        if not (t0<=clk<=t1): continue
        on = (r['sts']=='ON') if kind=='foc' else (r['sts']=='1')
        try: p=float(r['P_W']); q=float(r['Q_m3h']); h=float(r['hz']); t=float(r['t_s'])
        except (ValueError, KeyError): continue
        if not on: continue
        if prev is not None:
            dt=t-prev; E+=p*dt; V+=max(q,0)*dt/3600
        prev=t; P.append(p); Q.append(q); hz.append(h)
    if not P: return None
    Wh=E/3600
    return dict(n=len(P), P_W=round(sum(P)/len(P)), Q_m3h=round(sum(Q)/len(Q),2), hz=round(sum(hz)/len(hz),2), Wh=round(Wh), m3=round(V,3), L_per_Wh=round(V*1000/Wh,3) if Wh else None)
if __name__=='__main__':
    print(block(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]))
