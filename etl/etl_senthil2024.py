"""ETL: Kaggle 'senthilkumarvaithi/historical-nifty-options-2024-all-expiries' -> canonical Parquet.
Files: <root>/2024/2024MON/NIFTY-<EXPIRY>-<TRADEDATE>.csv (true 1m OHLC) + 2024Nifty/Nifty-2024MON.csv spot.
Keeps expiry_rank 0/1 per trade date, prunes |strike - spot@09:15| > 1500, fills a 375-minute grid.
"""
import sys, os, glob, re, datetime as dt, polars as pl

root, out = sys.argv[1], sys.argv[2]
files = glob.glob(f"{root}/2024/2024*/NIFTY-*.csv")
meta = []
for f in files:
    m = re.match(r"NIFTY-(\w{7})-(\w{7})\.csv", os.path.basename(f))
    e = dt.datetime.strptime(m.group(1), "%d%b%y").date(); d = dt.datetime.strptime(m.group(2), "%d%b%y").date()
    if e >= d: meta.append((f, d, e))
md = pl.DataFrame(meta, schema=["f", "d", "exp"], orient="row")
md = md.with_columns(pl.col("exp").rank("dense").over("d").cast(pl.UInt8).sub(1).alias("expiry_rank")).filter(pl.col("expiry_rank") <= 1)
print("files kept", md.height, "days", md["d"].n_unique())

spot = pl.concat([pl.read_csv(f) for f in glob.glob(f"{root}/2024/2024Nifty/*.csv")]).with_columns(
    pl.col("datetime").str.to_datetime("%Y-%m-%d %H:%M"))
spot = spot.with_columns(pl.col("datetime").dt.date().alias("d"),
    ((pl.col("datetime").dt.hour().cast(pl.Int32) * 60 + pl.col("datetime").dt.minute().cast(pl.Int32)) - 555).alias("m")
).filter(pl.col("m").is_between(0, 374)).unique(["d", "m"]).select("d", "m",
    pl.col("open").cast(pl.Float32).alias("spot_open"), pl.col("high").cast(pl.Float32).alias("spot_high"),
    pl.col("low").cast(pl.Float32).alias("spot_low"), pl.col("close").cast(pl.Float32).alias("spot_close"))
days = md.select("d").unique()
grid = days.join(pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32}), how="cross")
spot = grid.join(spot, on=["d", "m"], how="left").sort("d", "m").with_columns(
    pl.col("spot_open", "spot_high", "spot_low", "spot_close").forward_fill().backward_fill().over("d"))
missing = spot.group_by("d").agg(pl.col("spot_close").is_null().all().alias("x")).filter("x")
print("days without spot", missing.height)
s0 = spot.filter(pl.col("m") == 0).select("d", pl.col("spot_open").alias("s0"))

parts = []
for f, d, e, r in md.iter_rows():
    x = pl.read_csv(f, schema_overrides={"open": pl.Float32, "high": pl.Float32, "low": pl.Float32, "close": pl.Float32,
                                          "strike_price": pl.Float64, "open_interest": pl.Float64, "volume": pl.Float64})
    if x.height == 0: continue
    hm = x["datetime"].str.split(":")
    x = x.with_columns(((hm.list.get(0).cast(pl.Int32) * 60 + hm.list.get(1).str.slice(0, 2).cast(pl.Int32)) - 555).alias("m"),
                       pl.lit(d).alias("d"), pl.lit(e).alias("exp"), pl.lit(r, pl.UInt8).alias("expiry_rank"))
    parts.append(x.filter(pl.col("m").is_between(0, 374)).select(
        "d", "exp", "expiry_rank", "m", pl.col("strike_price").cast(pl.UInt32).alias("strike"),
        (pl.col("right") == "CE").alias("is_call"), "open", "high", "low", "close",
        pl.col("volume").fill_null(0).clip(0, 4e9).cast(pl.UInt32),
        pl.col("open_interest").fill_null(0).clip(0, 4e9).cast(pl.UInt32).alias("oi")))
opt = pl.concat(parts).join(s0, on="d").filter((pl.col("strike").cast(pl.Float32) - pl.col("s0")).abs() <= 1500).drop("s0")
opt = opt.unique(["d", "exp", "strike", "is_call", "m"], keep="last")
keys = opt.select("d", "exp", "expiry_rank", "strike", "is_call").unique()
full = keys.join(pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32}), how="cross")
opt = (full.join(opt, on=["d", "exp", "expiry_rank", "strike", "is_call", "m"], how="left")
       .sort("d", "expiry_rank", "is_call", "strike", "m")
       .with_columns(pl.col("close").forward_fill().over("d", "exp", "strike", "is_call").alias("cf"),
                     pl.col("oi").forward_fill().over("d", "exp", "strike", "is_call"),
                     pl.col("volume").fill_null(0))
       .with_columns(*[pl.col(c).fill_null(pl.col("cf")) for c in ["open", "high", "low", "close"]])
       .filter(pl.col("close").is_not_null()))
opt = opt.join(spot, on=["d", "m"])
ymd = lambda c: (pl.col(c).dt.year().cast(pl.UInt32) * 10000 + pl.col(c).dt.month().cast(pl.UInt32) * 100 + pl.col(c).dt.day().cast(pl.UInt32))
opt = opt.select(
    ymd("d").alias("trade_date"), ymd("exp").alias("expiry_date"),
    (pl.col("exp") - pl.col("d")).dt.total_days().cast(pl.UInt8).alias("dte"),
    "expiry_rank", pl.col("m").cast(pl.UInt16).alias("minute_idx"),
    "spot_open", "spot_high", "spot_low", "spot_close", "strike", "is_call",
    "open", "high", "low", "close", "volume", pl.col("oi").fill_null(0)
).sort("trade_date", "expiry_rank", "is_call", "strike", "minute_idx")
p = f"{out}/NIFTY_OHLC/year=2024"; os.makedirs(p, exist_ok=True)
opt.write_parquet(f"{p}/data.parquet", compression="zstd", compression_level=3)
print("rows", opt.height, "days", opt["trade_date"].n_unique())
