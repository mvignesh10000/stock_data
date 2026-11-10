"""Round 13: joined NIFTY index 1-min (debashis 2015.. + Upstox 2022..) -> daily table data/r13/idx_daily.parquet and minute arrays."""
import os, glob, numpy as np, polars as pl
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def minute(deb_dir):
    f = glob.glob(f"{deb_dir}/NIFTY*50_minute.csv")[0]
    a = pl.read_csv(f).with_columns(pl.col("date").str.to_datetime("%Y-%m-%d %H:%M:%S").alias("ts")).select("ts", "open", "high", "low", "close")
    b = pl.read_parquet(f"{ROOT}/data/upstox/index/NIFTY_1min.parquet").select(pl.col("ts").dt.replace_time_zone(None).cast(pl.Datetime("us")), "open", "high", "low", "close")
    a = a.with_columns(pl.col("ts").cast(pl.Datetime("us")))
    x = pl.concat([a.filter(pl.col("ts") < b["ts"].min()), b]).unique("ts").sort("ts")
    x = x.with_columns(pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"), (pl.col("ts").dt.hour().cast(pl.Int32) * 60 + pl.col("ts").dt.minute().cast(pl.Int32) - 555).alias("m"))
    return x.filter(pl.col("m").is_between(0, 374))
def at(x, m, name):
    return x.filter(pl.col("m") <= m).group_by("d").agg(pl.col("close").sort_by("m").last().alias(name))
def daily(x):
    d = x.group_by("d").agg(pl.col("open").sort_by("m").first().alias("o"), pl.col("high").max().alias("h"), pl.col("low").min().alias("l"), pl.col("close").sort_by("m").last().alias("c"), pl.len().alias("n"))
    for m, nm in ((4, "p0920"), (14, "p0930"), (44, "p1000"), (364, "p1520"), (344, "p1500"), (194, "p1230")):
        d = d.join(at(x, m, nm), on="d", how="left")
    return d.sort("d").filter(pl.col("n") > 300)
if __name__ == "__main__":
    import sys
    x = minute(sys.argv[1]); os.makedirs(f"{ROOT}/data/r13", exist_ok=True)
    x.write_parquet(f"{ROOT}/data/r13/idx_min.parquet"); d = daily(x); d.write_parquet(f"{ROOT}/data/r13/idx_daily.parquet")
    print(d.shape, d["d"].min(), d["d"].max())
