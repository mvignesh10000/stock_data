from ob import *
from lib2 import load2
d_,O,H,L,C=load2(); ds=d_.tolist(); n=len(ds)
dc=C[:,364]
def run(label,legs="both",thr=0.003,trend=True,wing=0.0,exit_m=4,ent_m=364,start=0):
    pnl=[];dates=[]
    for i in range(6,n-1):
        d=ds[i]; d2=ds[i+1]
        if d not in S or d2 not in S or d<start: continue
        r=C[i,ent_m]/C[i,5]-1; up=r>thr; dn=r<-thr
        if trend:
            t=np.sign(dc[i]-dc[i-5]); up=up and t>0; dn=dn and t<0
        if not(up or dn): continue
        if up and legs=="dn": continue
        if dn and legs=="up": continue
        typ=1 if up else 0   # sell PE after up day, sell CE after down
        es=[e for e in expiries(d,1)]
        if not es: continue
        e=es[0]
        if cal(d2,e)<0: continue
        sp=C[i,ent_m]; k=int(round(sp/50)*50)
        p0=px(d,e,typ,k,ent_m); p1=px(d2,e,typ,k,exit_m)
        if np.isnan(p0) or np.isnan(p1) or p0<1: continue
        L_=[(-1,fill(p0,-1)),(1,fill(p1,+1))]; pn=(fill(p0,-1)-fill(p1,+1))
        if wing:
            kw=int(round(sp*(1-wing if typ==1 else 1+wing)/50)*50)
            w0=px(d,e,typ,kw,ent_m); w1=px(d2,e,typ,kw,exit_m)
            if np.isnan(w0) or np.isnan(w1): continue
            L_+=[(1,fill(w0,+1)),(-1,fill(w1,-1))]; pn+=(fill(w1,-1)-fill(w0,+1))
        pnl.append(pn*LOT-cost(L_)); dates.append(d)
    print(f"{label:52s}",stats(pnl,dates)); return pnl,dates
print("== Strategy M replication, own engine, real prices, 2024-10..2026-11 (only 2.1 yrs available) ==")
run("naked both, no trend filter",trend=False)
run("naked both + trend filter")
run("naked up-only + trend filter",legs="up")
run("naked down-only + trend filter",legs="dn")
run("M-safe: both + trend + 3% wing",wing=0.03)
run("both, no filter, 3% wing",trend=False,wing=0.03)
run("M-safe exit 09:30 (idx14)",wing=0.03,exit_m=14)
run("M-safe exit 10:00 (idx44)",wing=0.03,exit_m=44)
run("M-safe, thr 0.5%",wing=0.03,thr=0.005)
run("M-safe, 1.5% wing",wing=0.015)
run("both+trend, 2% wing",wing=0.02)
