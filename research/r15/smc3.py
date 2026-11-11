"""Order blocks, BOS/CHoCH and premium/discount on 5-min NIFTY bars (same harness and placebo as smc.py)."""
import smc
from smc import *
rg_=np.random.default_rng(3)
def pd_pos(i,b):
    hi=H5[i,:b+1].max(); lo=L5[i,:b+1].min()
    return (C5[i,b]-lo)/(hi-lo) if hi>lo else 0.5
def signals(i,kind):
    out=[]; lsh=lsl=None; ish=isl=0; trend=0
    for b in range(6,70):
        c=b-3  # swing confirmed 3 bars later
        if H5[i,c]>H5[i,c-3:c].max() and H5[i,c]>H5[i,c+1:b+1].max(): lsh,ish=H5[i,c],c
        if L5[i,c]<L5[i,c-3:c].min() and L5[i,c]<L5[i,c+1:b+1].min(): lsl,isl=L5[i,c],c
        if lsh is not None and C5[i,b]>lsh:
            typ="choch" if trend==-1 else "bos"
            if lsl is not None and isl<b:
                dn=[k for k in range(isl,b) if C5[i,k]<O5[i,k]]
                if dn and (kind=="all" or kind==typ):
                    k=min(dn,key=lambda q:L5[i,q]); out.append((b,1,H5[i,k],L5[i,k],typ))
            trend=1; lsh=None
        if lsl is not None and C5[i,b]<lsl:
            typ="choch" if trend==1 else "bos"
            if lsh is not None and ish<b:
                up=[k for k in range(ish,b) if C5[i,k]>O5[i,k]]
                if up and (kind=="all" or kind==typ):
                    k=max(up,key=lambda q:H5[i,q]); out.append((b,-1,L5[i,k],H5[i,k],typ))
            trend=-1; lsl=None
    return out
def run(kind,R=2.0,pdf=False,valid=24,mid=False):
    res=[];ys=[];plac=[]
    for i in range(51,n):
        taken=0
        for b,side,edge,stop,typ in signals(i,kind):
            if taken>=2: break
            m0=(b+1)*5
            if m0>330: continue
            if pdf:
                p=pd_pos(i,b)
                if (side>0 and p>=0.5) or (side<0 and p<=0.5): continue
            ent=(edge+stop)/2 if mid else edge
            if abs(ent-stop)<0.0004*ent: continue
            f=None
            for q in range(m0,min(m0+valid*5,MAXM)):
                if (side>0 and L[i,q]<=stop) or (side<0 and H[i,q]>=stop): break
                if (side>0 and L[i,q]<=ent) or (side<0 and H[i,q]>=ent): f=q;break
            if f is None: continue
            r=result(i,f,side,ent,stop,R)
            if r is None: continue
            res.append(r);ys.append(yr[i]);taken+=1
            q=int(rg_.integers(20,320)); s2=int(rg_.choice([-1,1])); e2=C[i,q]; pr=result(i,q,s2,e2,e2-s2*abs(ent-stop),R)
            if pr: plac.append(pr)
    return np.array(res),np.array(ys),np.array(plac)
print("=== ORDER BLOCK retest after structure break (limit at OB edge, stop beyond OB, exit 15:15) ===")
for kind in ("all","bos","choch"):
    for pdf in (False,True):
        for R in (1.0,2.0,3.0):
            x,y,p=run(kind,R,pdf); rep(f"OB {kind} R={R} P/D filter={pdf}",x,y,p)
print("=== FVG + premium/discount filter (long only in discount, short only in premium) ===")
def fvg_pd(R,pdf):
    res=[];ys=[]
    for i in range(51,n):
        taken=0
        for b,side,edge,sref in fvg_signals(i,False,1.5):
            if taken>=2: break
            m0=(b+1)*5
            if m0>330: continue
            p=pd_pos(i,b)
            if pdf and ((side>0 and p>=0.5) or (side<0 and p<=0.5)): continue
            ent=edge
            if abs(ent-sref)<0.0004*ent: continue
            f=None
            for q in range(m0,min(m0+120,MAXM)):
                if (side>0 and L[i,q]<=sref) or (side<0 and H[i,q]>=sref): break
                if (side>0 and L[i,q]<=ent) or (side<0 and H[i,q]>=ent): f=q;break
            if f is None: continue
            r=result(i,f,side,ent,sref,R)
            if r: res.append(r);ys.append(yr[i]);taken+=1
    return np.array(res),np.array(ys)
for R in (1.0,2.0,3.0):
    x,y=fvg_pd(R,True); rep(f"FVG R={R} discount/premium only",x,y)
