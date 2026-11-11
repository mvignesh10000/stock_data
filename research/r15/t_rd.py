from ob import *
from lib2 import load2
d_,O,H,L,C=load2(); ds=d_.tolist(); n=len(ds); pos={d:i for i,d in enumerate(ds)}
dc=C[:,364]; dh=np.nanmax(H,1); dl=np.nanmin(L,1); do=O[:,0]
def ema(x,k):
    o=[x[0]]; a=2/(k+1)
    for v in x[1:]: o.append(a*v+(1-a)*o[-1])
    return np.array(o)
e20=ema(dc,20); rng=dh-dl
def strike_for(sp,typ,itm): # typ 1=put ; itm pts
    atm=int(round(sp/50)*50); return atm+itm if typ==1 else atm-itm
def trade(i,side,itm,mind,stopf,tgtf,exit_m=364,filt=None):
    d=ds[i]
    if d not in S: return None
    pl_,ph=dl[i-1],dh[i-1]; lvl=pl_ if side==-1 else ph
    hit=np.where(L[i,1:360]<lvl)[0] if side==-1 else np.where(H[i,1:360]>lvl)[0]
    if len(hit)==0: return None
    m=hit[0]+1+1  # enter on the bar after the break (close)
    if m>=360: return None
    es=expiries(d,mind)
    if not es: return None
    e=es[0]; typ=1 if side==-1 else 0
    k=strike_for(S[d]["spot"][m],typ,itm if typ==1 else itm)
    p0=px(d,e,typ,k,m)
    if np.isnan(p0) or p0<2: return None
    ent=fill(p0,+1); stop=ent*(1-stopf) if stopf else None; tgt=ent*(1+tgtf) if tgtf else None
    xp=None
    for q in range(m+1,exit_m+1):
        p=px(d,e,typ,k,q)
        if np.isnan(p): continue
        if stop and p<=stop: xp=fill(p,-1); break
        if tgt and p>=tgt: xp=fill(p,-1); break
    if xp is None:
        p=px(d,e,typ,k,exit_m); 
        if np.isnan(p): return None
        xp=fill(p,-1)
    return (xp-ent)*LOT-cost([(1,ent),(-1,xp)])
def run(label,side,itm,mind,stopf,tgtf,filt):
    pnl=[];dates=[]
    for i in range(25,n):
        if not filt(i): continue
        r=trade(i,side,itm,mind,stopf,tgtf)
        if r is None: continue
        pnl.append(r); dates.append(ds[i])
    print(f"{label:60s}",stats(pnl,dates))
below=lambda i: dc[i-1]<e20[i-1]
green=lambda i: dc[i-1]>do[i-1]
nr=lambda i: rng[i-1]<=np.min(rng[i-7:i])
anyd=lambda i: True
print("== REDDIT: buy PUT when prev-day LOW breaks (real NIFTY weekly option prices, 2024-10..2026-11, 1 lot, exit 15:20 same day) ==")
for itm in (0,200,500):
    for mind in (2,):
        for nm,f in [("all breaks",anyd),("below EMA20",below),("green prev day & below EMA20",lambda i:green(i) and below(i)),("narrow range & below EMA20",lambda i:nr(i) and below(i))]:
            run(f"put ITM{itm} dte>={mind} {nm}",-1,itm,mind,None,None,f)
print("-- with premium stop 30% / target 60%")
run("put ATM below EMA20 stop30 tgt60",-1,0,2,0.3,0.6,below)
run("put ITM200 below EMA20 stop30 tgt60",-1,200,2,0.3,0.6,below)
print("== mirror: buy CALL when prev-day HIGH breaks, above EMA20 ==")
above=lambda i: dc[i-1]>e20[i-1]
for itm in (0,200):
    run(f"call ITM{itm} above EMA20",1,itm,2,None,None,above)
