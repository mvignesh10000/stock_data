from lib import *
d,O,H,L,C,V=load(); n=len(d); yr=d//10000
dh=np.nanmax(H,1); dl=np.nanmin(L,1); dc=C[:,364]; do=O[:,0]
def ema(x,k):
    o=np.zeros_like(x); o[0]=x[0]; a=2/(k+1)
    for i in range(1,len(x)): o[i]=a*x[i]+(1-a)*o[i-1]
    return o
e20=ema(dc,20); e50=ema(dc,50)
rng=dh-dl
tr=np.maximum(rng[1:],np.maximum(abs(dh[1:]-dc[:-1]),abs(dl[1:]-dc[:-1]))); atr=np.r_[np.nan,np.convolve(tr,np.ones(14)/14,'full')[:n-1]]
atr=np.r_[np.full(15,np.nan),[tr[i-14:i].mean() for i in range(15,n)]][:n]
def run(side,filt,exit_,stop_atr=None,tgt_atr=None,slip=1.0):
    out=[];yrs=[]
    for i in range(51,n):
        pl_,ph=dl[i-1],dh[i-1]
        if not filt(i): continue
        lvl=pl_ if side==-1 else ph
        if side==-1: hit=np.where(L[i,1:360]<lvl)[0]
        else: hit=np.where(H[i,1:360]>lvl)[0]
        if len(hit)==0: continue
        m=hit[0]+1
        ent=min(lvl,O[i,m]) if side==-1 else max(lvl,O[i,m])
        ent=ent-slip if side==-1 else ent+slip   # worse fill
        st=None; tg=None
        if stop_atr: st=ent-side*stop_atr*atr[i]
        if tgt_atr: tg=ent+side*tgt_atr*atr[i]
        px=None
        for k in range(m,365):
            lo,hi=L[i,k],H[i,k]
            if side==-1:
                if st is not None and hi>=st and k>m: px=st+slip;break
                if tg is not None and lo<=tg and k>m: px=tg+slip;break
            else:
                if st is not None and lo<=st and k>m: px=st-slip;break
                if tg is not None and hi>=tg and k>m: px=tg-slip;break
        if px is None: px=C[i,364]+(slip if side==-1 else -slip)
        out.append(side*(px-ent)/ent*1e4); yrs.append(yr[i])
    return np.array(out),np.array(yrs)
def rep(name,r):
    x,y=r
    if len(x)<5: print(name,"n",len(x));return
    ys=" ".join(f"{u%100}:{x[y==u].mean():+.0f}" for u in sorted(set(y)))
    print(f"{name:42s} n={len(x):4d} mean={x.mean():+6.1f}bp t={tstat(x):+5.2f} win={np.mean(x>0)*100:3.0f}% | {ys}")
green=lambda i: dc[i-1]>do[i-1]
nr=lambda i: rng[i-1]<=np.min(rng[i-7:i])
below=lambda i: dc[i-1]<e20[i-1]
fall=lambda i: e20[i-1]<e20[i-2]
anyd=lambda i: True
print("== SHORT (puts) on previous-day-low break, index points -> bp of underlying, exit 15:20 ==")
for nm,f in [("all",anyd),("below EMA20",below),("below EMA20 & falling",lambda i:below(i) and fall(i)),("below EMA50",lambda i:dc[i-1]<e50[i-1]),("green prev day & below EMA20",lambda i:green(i) and below(i)),("narrow-range(7) & below EMA20",lambda i:nr(i) and below(i)),("ABOVE EMA20 (should fail)",lambda i:not below(i))]:
    rep("S "+nm,run(-1,f,None))
print("== stops/targets (ATR14 daily) ==")
for s,t in [(0.5,None),(None,1.0),(0.5,1.0),(0.5,1.5),(1.0,2.0)]:
    rep(f"S below EMA20 stop{s} tgt{t}",run(-1,below,None,s,t))
print("== MIRROR: long on previous-day-high break ==")
above=lambda i: dc[i-1]>e20[i-1]
for nm,f in [("all",anyd),("above EMA20",above),("above EMA20 & rising",lambda i:above(i) and e20[i-1]>e20[i-2]),("BELOW EMA20 (should fail)",lambda i:not above(i))]:
    rep("L "+nm,run(1,f,None))
print("== BASELINE: random day, short/long at 09:20 to 15:20 ==")
b=(C[51:,364]-C[51:,5])/C[51:,5]*1e4
print(f"unconditional long 09:20->15:20 mean {b.mean():+.1f}bp t {tstat(b):+.2f}")
