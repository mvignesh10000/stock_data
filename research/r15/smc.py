from lib import *
import sys
d,O,H,L,C,V=load(); n=len(d); yr=d//10000
dh=np.nanmax(H,1); dl=np.nanmin(L,1); dc=C[:,364]
def ema(x,k):
    o=[x[0]]; a=2/(k+1)
    for v in x[1:]: o.append(a*v+(1-a)*o[-1])
    return np.array(o)
e20=ema(dc,20)
# 5-min bars
O5=O[:,:375].reshape(n,75,5)[:,:,0]; C5=C[:,:375].reshape(n,75,5)[:,:,4]
H5=H[:,:375].reshape(n,75,5).max(2); L5=L[:,:375].reshape(n,75,5).min(2)
SL=1.0; COSTBP=6.0; MAXM=360
def walk(i,m0,side,ent,stop,tgt):
    """1-min walk from minute m0 (first bar AFTER fill bar) ; returns exit price"""
    for q in range(m0,MAXM+1):
        lo,hi=L[i,q],H[i,q]
        if side==1:
            if lo<=stop: return stop-SL
            if hi>=tgt: return tgt-SL
        else:
            if hi>=stop: return stop+SL
            if lo<=tgt: return tgt+SL
    return C[i,MAXM]-side*SL
def result(i,m,side,ent,stop,R):
    risk=abs(ent-stop)
    if risk<=0: return None
    tgt=ent+side*R*risk
    px=walk(i,m+1,side,ent,stop,tgt)
    g=side*(px-(ent+side*SL))/risk
    cost=(COSTBP*1e-4*ent)/risk
    return g,g-cost,risk/ent*1e4
def fvg_signals(i,align,disp):
    out=[]
    rg=H5[i]-L5[i]
    for b in range(21,70):
        av=rg[b-21:b-1].mean()
        # bull FVG: bars b-2,b-1,b
        if L5[i,b]>H5[i,b-2] and (rg[b-1]>=disp*av):
            out.append((b,1,L5[i,b],L5[i,b-2]))
        if H5[i,b]<L5[i,b-2] and (rg[b-1]>=disp*av):
            out.append((b,-1,H5[i,b],H5[i,b-2]))
    return out
def run_fvg(R=2.0,align=False,disp=1.5,valid=24,mid=False):
    res=[];ys=[];plac=[]
    rng=np.random.default_rng(1)
    for i in range(51,n):
        taken=0
        for b,side,edge,stopref in fvg_signals(i,align,disp):
            if taken>=2: break
            if align and not ((dc[i-1]>e20[i-1])==(side>0)): continue
            m0=(b+1)*5  # first minute after bar b closes
            if m0>330: continue
            zl,zh=(H5[i,b-2],L5[i,b]) if side>0 else (H5[i,b],L5[i,b-2])
            ent=(zl+zh)/2 if mid else (zh if side>0 else zl)
            stop=stopref
            if abs(ent-stop)<0.0004*ent: continue
            fill=None
            for q in range(m0,min(m0+valid*5,MAXM)):
                if side>0 and L[i,q]<=stop: break
                if side<0 and H[i,q]>=stop: break
                if (side>0 and L[i,q]<=ent) or (side<0 and H[i,q]>=ent): fill=q;break
            if fill is None: continue
            r=result(i,fill,side,ent,stop,R)
            if r is None: continue
            res.append(r);ys.append(yr[i]);taken+=1
            # placebo: random minute, random side, same risk distance
            q=int(rng.integers(20,320)); s2=int(rng.choice([-1,1])); e2=C[i,q]; st2=e2-s2*abs(ent-stop)
            pr=result(i,q,s2,e2,st2,R)
            if pr: plac.append(pr)
    return np.array(res),np.array(ys),np.array(plac)
def rep(nm,x,y,plac=None):
    if len(x)<30: print(nm,len(x)); return
    g=x[:,0];nt=x[:,1]
    ys=" ".join(f"{u%100}:{g[y==u].mean():+.2f}" for u in sorted(set(y)) if (y==u).sum()>=10)
    s=f"{nm:38s} n={len(g):5d} win={np.mean(g>0)*100:3.0f}% grossR={g.mean():+.3f} (t {tstat(g):+.2f}) netR={nt.mean():+.3f} avg stop={x[:,2].mean():.0f}bp"
    if plac is not None and len(plac): s+=f" | PLACEBO grossR={plac[:,0].mean():+.3f}"
    print(s); print("      by year grossR:",ys)
print("=== FVG (5-min, displacement candle >= disp x avg range), limit at gap edge, stop at candle-1 extreme, exit 15:15 ===")
for R in (1.0,2.0,3.0):
    for align in (False,True):
        for mid in (False,True):
            x,y,p=run_fvg(R=R,align=align,mid=mid); rep(f"FVG R={R} align={align} entry={'50%' if mid else 'edge'}",x,y,p)
