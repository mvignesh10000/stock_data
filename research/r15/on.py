from lib import *
d,O,H,L,C,V=load(); n=len(d); yr=d//10000
import datetime as dt
dd=[dt.date(x//10000,x//100%100,x%100) for x in d]
dh=np.nanmax(H,1); dl=np.nanmin(L,1); dc=C[:,364]
r=(C[:,364]/C[:,5]-1)            # 09:20->15:20 day move
ibs=(dc-dl)/np.maximum(dh-dl,1e-9)
tr=np.maximum(dh[1:]-dl[1:],np.maximum(abs(dh[1:]-dc[:-1]),abs(dl[1:]-dc[:-1])))
atrp=np.full(n,np.nan)
for i in range(15,n): atrp[i]=tr[i-14:i].mean()/dc[i-1]      # ATR% known at start of day i
z=r/atrp
t5=np.full(n,0.0)
for i in range(5,n): t5[i]=np.sign(dc[i]-dc[i-5])           # trend incl. today's close (as in repo: close 5 days ago)
nxt=np.full(n,np.nan); cd=np.zeros(n)
for i in range(n-1):
    nxt[i]=C[i+1,5]/C[i,364]-1; cd[i]=(dd[i+1]-dd[i]).days
net=(nxt*1e4)-cd*(0.075/365*1e4)-2.9   # bp net of carry and cost, LONG
def blk(m,sgn):
    x=(sgn*net)[m]; return x
def rep(name,m,sgn):
    x=blk(m,sgn); x=x[~np.isnan(x)]; yy=yr[m][~np.isnan((sgn*net)[m])]
    ys=" ".join(f"{u%100}:{x[yy==u].mean():+.0f}" for u in sorted(set(yy)) if (yy==u).sum()>=5)
    print(f"{name:44s} n={len(x):4d} mean={x.mean():+5.1f}bp t={tstat(x):+4.2f} | 15-20 {x[yy<=2020].mean():+5.1f} 21-26 {x[yy>=2021].mean():+5.1f} | {ys}")
ok=~np.isnan(z)&~np.isnan(nxt)
print("== LONG overnight after UP day (short PE proxy) ==")
rep("r>0.3% (repo)",ok&(r>0.003),1)
rep("r>0.3% & trend5 up (repo M-safe)",ok&(r>0.003)&(t5>0),1)
for zt in (0.5,0.75,1.0,1.25):
    rep(f"z>{zt} (move/ATR)",ok&(z>zt),1)
    rep(f"z>{zt} & trend up",ok&(z>zt)&(t5>0),1)
rep("r>0.3% & IBS>0.7 (closes strong)",ok&(r>0.003)&(ibs>0.7),1)
rep("r>0.3% & IBS<0.3 (fades into close)",ok&(r>0.003)&(ibs<0.3),1)
rep("z>0.75 & IBS>0.7 & trend",ok&(z>0.75)&(ibs>0.7)&(t5>0),1)
print("== SHORT overnight after DOWN day (short CE proxy) ==")
rep("r<-0.3% (repo)",ok&(r<-0.003),-1)
rep("r<-0.3% & trend5 down",ok&(r<-0.003)&(t5<0),-1)
for zt in (0.75,1.0,1.25):
    rep(f"z<-{zt}",ok&(z<-zt),-1)
rep("r<-0.3% & IBS<0.3",ok&(r<-0.003)&(ibs<0.3),-1)
# walk-forward threshold choice among r-thresholds & z thresholds, long side, trend aligned
print("== walk-forward: each year pick best-t threshold on prior years (long side, trend aligned) ==")
cands=[("r%.3f"%t,(lambda t=t: r>t)) for t in (0.0,0.002,0.003,0.004,0.005,0.006)]+[("z%.2f"%t,(lambda t=t: z>t)) for t in (0.5,0.75,1.0)]
tot=[];fx=[]
for Y in range(2019,2027):
    best=None
    for nm,f in cands:
        m=ok&f()&(t5>0)&(yr<Y); x=net[m]
        if len(x)>30:
            tt=tstat(x)
            if best is None or tt>best[0]: best=(tt,nm,f)
    m=ok&best[2]()&(t5>0)&(yr==Y); x=net[m]; tot+=list(x)
    m2=ok&(r>0.003)&(t5>0)&(yr==Y); fx+=list(net[m2])
    print(Y,best[1],f"n={len(x)} mean={x.mean():+.1f}bp  (fixed 0.3%: n={m2.sum()} {net[m2].mean():+.1f})")
print(f"walk-forward pooled {np.mean(tot):+.1f}bp t={tstat(tot):.2f} n={len(tot)} | fixed 0.3% pooled {np.mean(fx):+.1f}bp t={tstat(fx):.2f}")
print("== M signal by India VIX level at 15:20 (long side aligned; short side aligned), bp net of carry/cost ==")
vx=V[:,364]
for lo,hi in ((0,13),(13,16),(16,20),(20,99)):
    for nm,m,sg in (("UP&trend",(r>0.003)&(t5>0),1),("DN&trend",(r<-0.003)&(t5<0),-1)):
        mm=ok&m&(vx>=lo)&(vx<hi); x=(sg*net)[mm]
        if len(x)>8: print(f"VIX {lo:2d}-{hi:2d} {nm:9s} n={len(x):3d} mean={x.mean():+5.1f}bp t={tstat(x):+4.2f} 15-20 {x[yr[mm]<=2020].mean() if (yr[mm]<=2020).any() else float('nan'):+5.1f} 21-26 {x[yr[mm]>=2021].mean() if (yr[mm]>=2021).any() else float('nan'):+5.1f} worst night {x.min():+.0f}bp")
