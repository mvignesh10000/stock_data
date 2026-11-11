from lib import *
import itertools
d,O,H,L,C,V=load(); n=len(d); yr=d//10000
dh=np.nanmax(H,1); dl=np.nanmin(L,1); dc=C[:,364]
rng=dh-dl
tr=np.maximum(rng[1:],np.maximum(abs(dh[1:]-dc[:-1]),abs(dl[1:]-dc[:-1])))
atr=np.full(n,np.nan)
for i in range(15,n): atr[i]=tr[i-14:i].mean()   # ATR known before day i
ma20=np.full(n,np.nan); ma50=np.full(n,np.nan)
for i in range(50,n): ma20[i]=dc[i-20:i].mean(); ma50[i]=dc[i-50:i].mean()
trend5=np.full(n,0.0)
for i in range(6,n): trend5[i]=np.sign(dc[i-1]-dc[i-6])
SL=1.0  # points slippage per fill (index points proxy for ~futures/ITM option)
def sim(k,mode,align,s,t,exit_m=364):
    res=[];ys=[]
    for i in range(51,n):
        if np.isnan(atr[i]): continue
        o=O[i,0]; thr=k*atr[i]
        up=np.where(H[i,1:340]>=o+thr)[0]; dn=np.where(L[i,1:340]<=o-thr)[0]
        iu=up[0]+1 if len(up) else 9999; idn=dn[0]+1 if len(dn) else 9999
        if iu==idn==9999: continue
        first=1 if iu<idn else -1; m=min(iu,idn)
        # momentum: trade with the move; fade: against
        side=first if mode=="mom" else -first
        if align=="trend" and (first!=trend5[i]): continue
        if align=="trend_fade" and (first==trend5[i]): continue
        if align=="regime" and not ((dc[i-1]>ma50[i])==(first>0)): continue
        ent=o+first*thr; ent=ent+side*SL
        st=ent-side*s*atr[i]; tg=ent+side*t*atr[i] if t else None; px=None
        for q in range(m+1,exit_m+1):
            lo,hi=L[i,q],H[i,q]
            if side==1:
                if lo<=st: px=st;break
                if tg and hi>=tg: px=tg;break
            else:
                if hi>=st: px=st;break
                if tg and lo<=tg: px=tg;break
        if px is None: px=C[i,exit_m]
        px=px-side*SL
        res.append(side*(px-ent)/o*1e4); ys.append(yr[i])
    return np.array(res),np.array(ys)
rows=[]
for k,mode,align,(s,t) in itertools.product((0.3,0.5,0.8),("mom","fade"),("none","trend","regime","trend_fade"),((0.4,0.8),(0.5,1.0),(0.5,None),(0.8,1.6))):
    x,y=sim(k,mode,align,s,t)
    if len(x)<150: continue
    pos=sum(x[y==u].mean()>0 for u in set(y)); ny=len(set(y))
    a=x[y<=2020]; b=x[y>=2021]
    rows.append((tstat(x),k,mode,align,s,t,len(x),x.mean(),pos,ny,a.mean(),b.mean(),(x[x>0].sum()/-x[x<0].sum())))
rows.sort(reverse=True)
print("top 12 by t-stat (bp of index per trade, after 1pt slippage/fill; NO option costs):")
for r in rows[:12]: print(f"t={r[0]:+.2f} k={r[1]} {r[2]:4s} {r[3]:10s} stop={r[4]} tgt={r[5]} n={r[6]} mean={r[7]:+.1f}bp posYrs={r[8]}/{r[9]} 15-20={r[10]:+.1f} 21-26={r[11]:+.1f} PF={r[12]:.2f}")
print("bottom 5:")
for r in rows[-5:]: print(f"t={r[0]:+.2f} k={r[1]} {r[2]:4s} {r[3]:10s} stop={r[4]} tgt={r[5]} n={r[6]} mean={r[7]:+.1f}bp")
print("n combos",len(rows),"; share with t>2:",np.mean([r[0]>2 for r in rows]),"; share t<-2:",np.mean([r[0]<-2 for r in rows]))
