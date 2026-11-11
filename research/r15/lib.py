import polars as pl, numpy as np, os
D=os.path.join(os.path.dirname(os.path.abspath(__file__)),"../../data/deb/")
def load():
    f=os.path.join(os.path.dirname(os.path.abspath(__file__)),"../../data/r15/days.npz")
    if os.path.exists(f):
        z=np.load(f,allow_pickle=True); return z["d"],z["O"],z["H"],z["L"],z["C"],z["V"]
    a=pl.read_csv(D+"NIFTY%2050_minute.csv").with_columns(pl.col("date").str.to_datetime("%Y-%m-%d %H:%M:%S").alias("ts"))
    v=pl.read_csv(D+"INDIA%20VIX_minute.csv").with_columns(pl.col("date").str.to_datetime("%Y-%m-%d %H:%M:%S").alias("ts")).select("ts",pl.col("close").alias("vix"))
    a=a.join(v,on="ts",how="left")
    a=a.with_columns(pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"),(pl.col("ts").dt.hour().cast(pl.Int32)*60+pl.col("ts").dt.minute().cast(pl.Int32)-555).alias("m")).filter(pl.col("m").is_between(0,374))
    days=sorted(a["d"].unique().to_list()); 
    cnt=a.group_by("d").len(); good=set(cnt.filter(pl.col("len")>=370)["d"].to_list()); days=[x for x in days if x in good]
    idx={d:i for i,d in enumerate(days)}
    n=len(days)
    arr={k:np.full((n,375),np.nan) for k in "OHLCV"}
    di=a["d"].to_numpy(); mi=a["m"].to_numpy()
    sel=np.array([x in idx for x in di]); 
    r=np.array([idx.get(x,-1) for x in di])
    for k,c in zip("OHLCV",["open","high","low","close","vix"]):
        arr[k][r[sel],mi[sel]]=a[c].to_numpy()[sel]
    # ffill gaps
    for k in "OHLC":
        x=arr[k]; 
        for i in range(n):
            row=x[i]; m=np.isnan(row)
            if m.any():
                j=np.where(~m,np.arange(375),0); np.maximum.accumulate(j,out=j); row[:]=row[j]
    np.savez(f,d=np.array(days),O=arr["O"],H=arr["H"],L=arr["L"],C=arr["C"],V=arr["V"])
    return np.array(days),arr["O"],arr["H"],arr["L"],arr["C"],arr["V"]
def tstat(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    return (x.mean()/(x.std(ddof=1)/np.sqrt(len(x)))) if len(x)>2 and x.std()>0 else 0.0
