from ob import *
from lib2 import load2
import polars as pl
d_,O,H,L,C=load2(); ds=d_.tolist(); n=len(ds); dc=C[:,364]
v=pl.read_parquet(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"../../")+"data/upstox/index/VIX_1min.parquet").with_columns(pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"),(pl.col("ts").dt.hour().cast(pl.Int32)*60+pl.col("ts").dt.minute().cast(pl.Int32)-555).alias("m")).filter(pl.col("m")<=364).group_by("d").agg(pl.col("close").sort_by("m").last().alias("v"))
VX=dict(zip(v["d"].to_list(),v["v"].to_list()))
def run(label,vcut=None,mode="none",wing=0.0,start=0,quiet=False,exit_m=4,ent_m=364):
    pnl=[];dates=[]
    for i in range(6,n-1):
        d=ds[i]; d2=ds[i+1]
        if d not in S or d2 not in S or d<start or d not in VX: continue
        r=C[i,ent_m]/C[i,5]-1; t=np.sign(dc[i]-dc[i-5])
        up=r>0.003 and t>0; dn=r<-0.003 and t<0
        if not(up or dn): continue
        hv=VX[d]>(vcut or 1e9)
        if hv and mode=="skipdn" and dn: continue
        if hv and mode=="skipall": continue
        typ=1 if up else 0
        es=expiries(d,1)
        if not es: continue
        e=es[0]
        if cal(d2,e)<0: continue
        sp=C[i,ent_m]; k=int(round(sp/50)*50)
        p0=px(d,e,typ,k,ent_m); p1=px(d2,e,typ,k,exit_m)
        if np.isnan(p0) or np.isnan(p1) or p0<1: continue
        L_=[(-1,fill(p0,-1)),(1,fill(p1,+1))]; pn=fill(p0,-1)-fill(p1,+1)
        if wing:
            kw=int(round(sp*(1-wing if typ==1 else 1+wing)/50)*50)
            w0=px(d,e,typ,kw,ent_m); w1=px(d2,e,typ,kw,exit_m)
            if np.isnan(w0) or np.isnan(w1): continue
            L_+=[(1,fill(w0,+1)),(-1,fill(w1,-1))]; pn+=fill(w1,-1)-fill(w0,+1)
        pnl.append(pn*LOT-cost(L_)); dates.append(d)
    p=np.array(pnl); dts=np.array(dates)
    ys=" ".join(f"{y%100}:{p[dts//10000==y].sum()/1000:+.0f}k" for y in sorted(set(dts//10000)))
    print(f"{label:46s}",stats(pnl,dates),"\n      ",ys)
print("== M naked ATM, both legs + trend, 2022-2026 (Dhan 2021-24 + Upstox lake), real prices ==")
run("baseline")
for vc in (18,20,22):
    run(f"skip DN when VIX>{vc}",vc,"skipdn")
run("skip ALL when VIX>20",20,"skipall")
print("-- 2024-10+ with 3% wing (M-safe) --")
run("M-safe baseline",wing=0.03,start=20241004)
run("M-safe skip DN VIX>20",20,"skipdn",wing=0.03,start=20241004)
print("-- how many trades/PnL occur in VIX>20 --")
import collections
for lo,hi in ((0,16),(16,20),(20,99)):
    pass
