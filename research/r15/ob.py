import os, pickle, numpy as np, datetime as dt
S=pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"../../data/r15/ostore.pkl"),"rb"))
DAYS=sorted(S); LOT=65
def dd(d): return dt.date(d//10000,d//100%100,d%100)
def cal(a,b): return (dd(b)-dd(a)).days
def px(d,e,typ,k,m):
    c=S[d]["ch"].get(e)
    if c is None: return np.nan
    j=np.searchsorted(c["k"],k)
    if j>=len(c["k"]) or c["k"][j]!=k: return np.nan
    return float(c["c"][typ,j,m])
def fill(p,side):  # side +1 buy, -1 sell; slippage max(0.5%,0.1)
    s=max(0.005*p,0.10); return p+s if side>0 else max(p-s,0.0)
def cost(legs):  # legs: list of (side, price)
    t=0
    for side,p in legs:
        v=p*LOT; t+=20+v*0.0003503*1.18+(v*0.0015 if side<0 else 0)+(v*0.00003 if side>0 else 0)
    return t
def expiries(d,mind=0):
    return sorted(e for e in S[d]["ch"] if cal(d,e)>=mind)
def stats(pnl,dates):
    p=np.array(pnl); 
    if len(p)==0: return "no trades"
    cum=np.cumsum(p); dd_=(np.maximum.accumulate(np.r_[0,cum])[1:]-cum).max()
    w=p[p>0].sum(); l=-p[p<0].sum()
    yrs=(dd(max(dates))-dd(min(dates))).days/365.25
    mo={}
    for x,dtt in zip(p,dates): mo[dtt//100]=mo.get(dtt//100,0)+x
    wm=np.mean([v>0 for v in mo.values()])*100
    return f"n={len(p):4d} win={np.mean(p>0)*100:3.0f}% net/yr={p.sum()/yrs:9.0f} avg={p.mean():7.0f} PF={w/l if l else 99:4.2f} maxDD={dd_:8.0f} WM={wm:3.0f}% worst={p.min():8.0f}"
