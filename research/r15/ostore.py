import os, polars as pl, numpy as np, glob, pickle
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.join(HERE,"../..")
src=ROOT+"/data/parquet/NIFTY_UPX/*/data.parquet"
days={}
import sys
for f in sorted(glob.glob(src))+sorted(glob.glob(ROOT+"/data/r15/dhan_in/*.parquet")):
    x=pl.read_parquet(f,columns=["trade_date","expiry_date","dte","minute_idx","spot_close","strike","is_call","close"]).filter((pl.col("trade_date")<20241004 if "dhan_in" in f else pl.col("trade_date")>0)&(pl.col("strike")%50==0)&(pl.col("minute_idx")<375)&((pl.col("strike").cast(pl.Float64)-pl.col("spot_close")).abs()<=1500))
    if x.height==0: continue
    for (d,e),g in x.group_by(["trade_date","expiry_date"]):
        D=days.setdefault(int(d),{"spot":np.full(375,np.nan,np.float32),"ch":{}})
        sp=g.unique("minute_idx").sort("minute_idx"); D["spot"][sp["minute_idx"].to_numpy()]=sp["spot_close"].to_numpy()
        ks=np.array(sorted(g["strike"].unique().to_list()),np.int32); ki={k:i for i,k in enumerate(ks)}
        a=np.full((2,len(ks),375),np.nan,np.float32)
        a[(g["is_call"].not_().cast(pl.Int32).to_numpy(),np.array([ki[k] for k in g["strike"].to_list()]),g["minute_idx"].to_numpy())]=g["close"].to_numpy()
        for r in range(2):
            for j in range(len(ks)):
                row=a[r,j]; m=np.isnan(row)
                if m.all() or not m.any(): continue
                idx=np.where(~m,np.arange(375),0); np.maximum.accumulate(idx,out=idx); row[:]=np.where(np.arange(375)>=np.argmax(~m),row[idx],np.nan)
        D["ch"][int(e)]={"k":ks,"c":a}
pickle.dump(days,open(HERE+"/../../data/r15/ostore.pkl","wb")); print(len(days),min(days),max(days))
