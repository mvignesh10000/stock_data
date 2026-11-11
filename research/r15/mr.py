from lib import *
d,O,H,L,C,V=load(); n=len(d); yr=d//10000
dh=np.nanmax(H,1); dl=np.nanmin(L,1); dc=C[:,364]; do=O[:,0]
def rsi(x,k):
    o=np.full(len(x),np.nan); g=np.zeros(len(x)); l=np.zeros(len(x))
    dif=np.diff(x,prepend=x[0]); g=np.maximum(dif,0); l=np.maximum(-dif,0)
    ag=g[1:k+1].mean(); al=l[1:k+1].mean()
    for i in range(k+1,len(x)):
        ag=(ag*(k-1)+g[i])/k; al=(al*(k-1)+l[i])/k
        o[i]=100-100/(1+ag/al) if al>0 else 100
    return o
r2=rsi(dc,2); ma200=np.full(n,np.nan)
for i in range(200,n): ma200[i]=dc[i-200:i+1].mean()
tr=np.maximum(dh[1:]-dl[1:],np.maximum(abs(dh[1:]-dc[:-1]),abs(dl[1:]-dc[:-1]))); atr=np.full(n,np.nan)
for i in range(15,n): atr[i]=tr[i-14:i].mean()
COST=8.0  # bp round trip: futures STT 5bp + ~3bp slippage/brokerage
def trades(side,sig,exit_kind,maxd=5,stop_atr=2.0):
    out=[];ys=[];dates=[]
    i=201
    while i<n-maxd-1:
        if sig(i):
            ent=dc[i]; j=i; px=None
            for j in range(i+1,i+maxd+1):
                st=ent-side*stop_atr*atr[i]
                if side==1 and dl[j]<=st: px=min(st,O[j,0]) if O[j,0]<st else st;break
                if side==-1 and dh[j]>=st: px=max(st,O[j,0]) if O[j,0]>st else st;break
                if exit_kind=="prevhl":
                    if side==1 and dc[j]>dh[j-1]: px=dc[j];break
                    if side==-1 and dc[j]<dl[j-1]: px=dc[j];break
                if exit_kind=="ma5":
                    m5=dc[j-4:j+1].mean()
                    if (side==1 and dc[j]>m5) or (side==-1 and dc[j]<m5): px=dc[j];break
            if px is None: px=dc[j]
            out.append(side*(px-ent)/ent*1e4-COST); ys.append(yr[i]); dates.append(d[i]); i=j+1
        else: i+=1
    return np.array(out),np.array(ys),dates
def rep(nm,res):
    x,y,dts=res
    if len(x)<10: print(nm,len(x)); return
    cum=np.cumsum(x); ddn=(np.maximum.accumulate(cum)-cum).max()
    ys=" ".join(f"{u%100}:{x[y==u].sum():+.0f}" for u in sorted(set(y)))
    print(f"{nm:50s} n={len(x):3d} avg={x.mean():+6.1f}bp t={tstat(x):+4.2f} win={np.mean(x>0)*100:3.0f}% PF={x[x>0].sum()/max(-x[x<0].sum(),1e-9):4.2f} sumBP={x.sum():+6.0f} maxDDbp={ddn:5.0f} | 15-20 avg {x[y<=2020].mean():+5.1f} 21-26 {x[y>=2021].mean():+5.1f}\n     yearly sum(bp): {ys}")
up=lambda i: dc[i]>ma200[i]
print("== LONG pullbacks in uptrend (close>200DMA), entry at signal close, costs 8bp RT ==")
rep("RSI2<10, exit close>prevHigh, max5d, stop2ATR",trades(1,lambda i:up(i) and r2[i]<10,"prevhl"))
rep("RSI2<5",trades(1,lambda i:up(i) and r2[i]<5,"prevhl"))
rep("RSI2<10, exit close>5dMA",trades(1,lambda i:up(i) and r2[i]<10,"ma5",maxd=7))
rep("3 lower closes",trades(1,lambda i:up(i) and dc[i]<dc[i-1]<dc[i-2]<dc[i-3],"prevhl"))
rep("IBS<0.2 & close<prev low",trades(1,lambda i:up(i) and (dc[i]-dl[i])/(dh[i]-dl[i])<0.2 and dc[i]<dl[i-1],"prevhl"))
rep("RSI2<10 NO trend filter (control)",trades(1,lambda i:r2[i]<10,"prevhl"))
print("== SHORT bounces in downtrend (close<200DMA) ==")
rep("RSI2>90, close<200DMA",trades(-1,lambda i:(not up(i)) and r2[i]>90,"prevhl"))
print("== buy&hold bp/yr context:", f"{(dc[-1]/dc[201]-1)*100:.0f}% total since {d[201]}")
