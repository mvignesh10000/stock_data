import polars as pl, numpy as np
def load2():
    a=pl.read_parquet(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"../../")+"data/upstox/index/NIFTY_1min.parquet").with_columns(pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"),(pl.col("ts").dt.hour().cast(pl.Int32)*60+pl.col("ts").dt.minute().cast(pl.Int32)-555).alias("m")).filter(pl.col("m").is_between(0,374))
    cnt=a.group_by("d").len().filter(pl.col("len")>=370); days=sorted(cnt["d"].to_list()); idx={d:i for i,d in enumerate(days)}
    n=len(days); arr={k:np.full((n,375),np.nan) for k in "OHLC"}
    s=a.filter(pl.col("d").is_in(days)); r=np.array([idx[x] for x in s["d"].to_list()]); m=s["m"].to_numpy()
    for k,c in zip("OHLC",["open","high","low","close"]): arr[k][r,m]=s[c].to_numpy()
    for k in "OHLC":
        x=arr[k]
        for i in range(n):
            row=x[i]; mm=np.isnan(row)
            if mm.any(): j=np.where(~mm,np.arange(375),0); np.maximum.accumulate(j,out=j); row[:]=row[j]
    return np.array(days),arr["O"],arr["H"],arr["L"],arr["C"]
