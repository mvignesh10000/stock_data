from ob import *
import sys
# daily closes for trend (from index data)
from lib import load
d_,O,H,L,C,V=load(); dc=dict(zip(d_.tolist(),C[:,364]))
def ema(x,k):
    o=[x[0]]; a=2/(k+1)
    for v in x[1:]: o.append(a*v+(1-a)*o[-1])
    return o
ds=d_.tolist(); e20=dict(zip(ds,ema([dc[x] for x in ds],20)))
def prevday(d):
    i=ds.index(d); return ds[i-1] if i>0 else None
# weekly credit spread per infographic
def spread(d,e,side,width,target_frac,m_ent,stop_mult,hold_expiry=True,exit_m=None):
    sp=S[d]["spot"][m_ent]; typ=1 if side=="put" else 0   # bull put spread = sell PE; bear call = sell CE
    ks=S[d]["ch"][e]["k"]; best=None
    for k in ks:
        if typ==1 and k>sp: continue
        if typ==0 and k<sp: continue
        kl=k-width if typ==1 else k+width
        ps=px(d,e,typ,int(k),m_ent); pl_=px(d,e,typ,int(kl),m_ent)
        if np.isnan(ps) or np.isnan(pl_): continue
        cr=ps-pl_; err=abs(cr/width-target_frac)
        if best is None or err<best[0]: best=(err,int(k),int(kl),cr,ps,pl_)
    return best
def run(label,width=200,frac=1/3,min_cal=4,max_cal=7,stop_mult=None,dir_rule="ema",m_ent=10,tgt_profit=None,fixed_dir=None):
    pnl=[];dates=[];dtl=[]
    done=set()
    for d in DAYS:
        es=[e for e in expiries(d,1) if min_cal<=cal(d,e)<=max_cal]
        if not es: continue
        e=es[0]
        if e in done: continue
        if d not in e20 or prevday(d) is None: continue
        pdd=prevday(d); bull=dc[pdd]>e20[pdd]
        if fixed_dir: side=fixed_dir
        else: side="put" if bull else "call"
        b=spread(d,e,side,width,frac,m_ent,stop_mult)
        if b is None: continue
        done.add(e)
        _,k,kl,cr,ps,pl_=b; typ=1 if side=="put" else 0
        ent=fill(ps,-1)-fill(pl_,+1)   # net credit received
        legs=[(-1,fill(ps,-1)),(1,fill(pl_,+1))]
        # walk forward day by day to expiry
        exitv=None; tradedays=[x for x in DAYS if d<=x<=e]
        stopv=ent*(1+stop_mult) if stop_mult else None
        for x in tradedays:
            r0=m_ent+1 if x==d else 0
            for m in range(r0,375):
                a=px(x,e,typ,k,m); bb=px(x,e,typ,kl,m)
                if np.isnan(a) and x==e and m>0: a=0.0 if np.isnan(a) else a
                if np.isnan(a): continue
                if np.isnan(bb): bb=0.0
                val=a-bb
                if stopv and val>=stopv and not(x==e and m>=360):
                    exitv=(val,fill(a,+1),fill(bb,-1)); break
                if tgt_profit and val<=ent*(1-tgt_profit):
                    exitv=(val,fill(a,+1),fill(bb,-1)); break
            if exitv: break
        if not exitv:
            sx=S[e]["spot"][374]
            a=max(sx-k,0) if typ==0 else max(k-sx,0); bb=max(sx-kl,0) if typ==0 else max(kl-sx,0)
            exitv=(a-bb,a,bb); legs+= [(1,a)] if a>0 else []
            legs+= [(-1,bb)] if bb>0 else []
        else:
            legs+=[(1,exitv[1]),(-1,exitv[2])]
        gross=(ent-exitv[0]) if not False else 0
        # recompute precisely using fills
        entc=fill(ps,-1)-fill(pl_,+1)
        if len(legs)==4 and exitv: 
            pass
        pnl.append((entc-(exitv[1]-exitv[2]) if len(legs)==4 and tgt_profit is None and stop_mult is None and False else entc-exitv[0])*LOT-cost(legs)); dates.append(d)
        dtl.append((d,e,side,k,kl,cr))
    print(f"{label:55s}",stats(pnl,dates))
    return pnl,dates,dtl
print("== Infographic credit spread on NIFTY weekly (2024-10..2026-11), 1 lot, real 1-min prices, costs+slippage ==")
for w in (100,200,300):
    run(f"w={w} credit=1/3 width, hold to expiry, trend-direction",width=w)
for sm in (0.75,1.0,2.0):
    run(f"w=200 stop at {int(sm*100)}% of credit loss",width=200,stop_mult=sm)
run("w=200 stop 100% + 50% profit target",width=200,stop_mult=1.0,tgt_profit=0.5)
run("w=200 always PUT spread (bullish bias)",width=200,fixed_dir="put")
run("w=200 always CALL spread",width=200,fixed_dir="call")
for fr in (0.15,0.25):
    run(f"w=200 credit={fr:.2f}*width (farther OTM), hold",width=200,frac=fr)
