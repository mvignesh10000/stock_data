import smc
from smc import *
rng_=np.random.default_rng(2)
def run_sweep(level,R=2.0,confirm=3,align=None,minrisk=6):
    res=[];ys=[];plac=[]
    for i in range(51,n):
        if level=="pd": hi_lvl,lo_lvl,start=dh[i-1],dl[i-1],1
        else: hi_lvl,lo_lvl,start=np.max(H[i,:30]),np.min(L[i,:30]),31   # opening range 09:15-09:45
        done=0
        for b in range(max(start//5,1),68):
            if done>=1: break
            # bearish sweep: 5-min bar trades above level, closes back below (rejection)
            for side,lvl in ((-1,hi_lvl),(1,lo_lvl)):
                if side==-1: sw=H5[i,b]>lvl and C5[i,b]<lvl
                else: sw=L5[i,b]<lvl and C5[i,b]>lvl
                if not sw: continue
                if align is not None and ((dc[i-1]>e20[i-1])!=(side>0))==align: continue
                ent=C5[i,b]; stop=H5[i,b] if side==-1 else L5[i,b]
                risk=abs(ent-stop)
                if risk<minrisk: continue
                m=(b+1)*5-1
                if m>330: continue
                r=result(i,m,side,ent,stop,R)
                if r is None: continue
                res.append(r);ys.append(yr[i]);done+=1
                q=int(rng_.integers(20,320)); s2=int(rng_.choice([-1,1])); e2=C[i,q]; pr=result(i,q,s2,e2,e2-s2*risk,R)
                if pr: plac.append(pr)
                break
    return np.array(res),np.array(ys),np.array(plac)
print("=== LIQUIDITY SWEEP & REJECTION (stop-hunt reversal): enter at the rejection close, stop beyond sweep extreme, exit 15:15 ===")
for lv in ("pd","or"):
    for R in (1.0,2.0,3.0):
        for al in (None,False):   # None = any; False = only trade WITH daily trend (skip counter-trend)
            x,y,p=run_sweep(lv,R,align=al); rep(f"sweep {'prev-day H/L' if lv=='pd' else 'opening-range'} R={R} {'any' if al is None else 'with-trend only'}",x,y,p)
