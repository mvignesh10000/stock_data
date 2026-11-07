"""ETL: Kaggle 'pariminikhil/nifty-option-chain-3-oct-24-to-24-mar-26' -> canonical Parquet.

Source has 1-minute LTP (no OHLC) + volume + OI + underlying spot per row.
We map open = previous LTP, close = LTP, high/low = max/min(prev, LTP) (documented limitation: true
intra-bar extremes are unknown, the engine applies extra SL slippage on stop fills).
"""
import sys, polars as pl

src, out = sys.argv[1], sys.argv[2]
lf = pl.scan_csv(src, schema_overrides={"pcr": pl.Float64, "strike_price": pl.Float64},
                 infer_schema_length=10000)
lf = lf.select(
    pl.col("strike_price").cast(pl.UInt32).alias("strike"),
    (pl.col("option_type") == "CE").alias("is_call"),
    pl.col("expiry").str.slice(0, 10).str.to_date("%Y-%m-%d").alias("exp"),
    pl.col("timestamp").str.to_datetime("%Y-%m-%d %H:%M:%S").alias("ts"),
    pl.col("ltp").cast(pl.Float32),
    pl.col("volume").cast(pl.Float64).fill_null(0).clip(0, 4e9).cast(pl.UInt32),
    pl.col("oi").cast(pl.Float64).fill_null(0).clip(0, 4e9).cast(pl.UInt32),
    pl.col("underlying_spot_price").cast(pl.Float32).alias("spot"),
).with_columns(
    pl.col("ts").dt.date().alias("d"),
    ((pl.col("ts").dt.hour().cast(pl.Int32) * 60 + pl.col("ts").dt.minute().cast(pl.Int32)) - (9 * 60 + 15)).alias("m"),
).filter((pl.col("m") >= 0) & (pl.col("m") <= 374) & (pl.col("exp") >= pl.col("d")))
df = lf.collect(engine="streaming")
print("rows", df.height)

# Spot per minute (median across rows, robust to bad ticks), forward filled on full grid
spot = df.group_by("d", "m").agg(pl.col("spot").median()).sort("d", "m")
days = spot.select("d").unique().sort("d")
grid = days.join(pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32}), how="cross")
spot = grid.join(spot, on=["d", "m"], how="left").sort("d", "m").with_columns(
    pl.col("spot").forward_fill().backward_fill().over("d"))
# 1-minute spot "OHLC" from consecutive closes (spot open = previous close)
spot = spot.with_columns(
    pl.col("spot").shift(1).over("d").fill_null(pl.col("spot")).alias("spot_open"))
spot = spot.with_columns(
    pl.max_horizontal("spot", "spot_open").alias("spot_high"),
    pl.min_horizontal("spot", "spot_open").alias("spot_low"),
    pl.col("spot").alias("spot_close"))
open_spot = spot.filter(pl.col("m") == 0).select("d", pl.col("spot").alias("s0"))

# Expiry rank per trade date (0 = nearest)
er = df.select("d", "exp").unique().sort("d", "exp").with_columns(
    pl.col("exp").rank("dense").over("d").cast(pl.UInt8).sub(1).alias("expiry_rank"))
er = er.filter(pl.col("expiry_rank") <= 1)

opt = (df.join(er, on=["d", "exp"]).join(open_spot, on="d")
       .filter((pl.col("strike").cast(pl.Float32) - pl.col("s0")).abs() <= 1500)
       .group_by("d", "exp", "expiry_rank", "strike", "is_call", "m")
       .agg(pl.col("ltp").last(), pl.col("volume").sum(), pl.col("oi").max()))
# full minute grid per contract, forward-fill price, volume=0 on missing
keys = opt.select("d", "exp", "expiry_rank", "strike", "is_call").unique()
full = keys.join(pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32}), how="cross")
opt = (full.join(opt, on=["d", "exp", "expiry_rank", "strike", "is_call", "m"], how="left")
       .sort("d", "expiry_rank", "is_call", "strike", "m")
       .with_columns(pl.col("ltp").forward_fill().over("d", "exp", "strike", "is_call"),
                     pl.col("oi").forward_fill().over("d", "exp", "strike", "is_call"),
                     pl.col("volume").fill_null(0))
       .filter(pl.col("ltp").is_not_null()))
# LTP-only source: open = previous minute LTP, high/low = envelope of (prev, current) so stops cannot skip a move
opt = opt.with_columns(pl.col("ltp").shift(1).over("d", "exp", "strike", "is_call").fill_null(pl.col("ltp")).alias("po"))
opt = opt.join(spot.select("d", "m", "spot_open", "spot_high", "spot_low", "spot_close"), on=["d", "m"])
ymd = lambda c: (pl.col(c).dt.year().cast(pl.UInt32) * 10000 + pl.col(c).dt.month().cast(pl.UInt32) * 100 + pl.col(c).dt.day().cast(pl.UInt32))
opt = opt.select(
    ymd("d").alias("trade_date"), ymd("exp").alias("expiry_date"),
    (pl.col("exp") - pl.col("d")).dt.total_days().cast(pl.UInt8).alias("dte"),
    "expiry_rank", pl.col("m").cast(pl.UInt16).alias("minute_idx"),
    "spot_open", "spot_high", "spot_low", "spot_close", "strike", "is_call",
    pl.col("po").alias("open"), pl.max_horizontal("po", "ltp").alias("high"), pl.min_horizontal("po", "ltp").alias("low"), pl.col("ltp").alias("close"),
    "volume", pl.col("oi").fill_null(0)
).sort("trade_date", "expiry_rank", "is_call", "strike", "minute_idx")
import os
for y in opt.select((pl.col("trade_date") // 10000).alias("y")).unique().to_series().to_list():
    p = f"{out}/NIFTY/year={y}"; os.makedirs(p, exist_ok=True)
    part = opt.filter(pl.col("trade_date") // 10000 == y)
    part.write_parquet(f"{p}/data.parquet", compression="zstd", compression_level=3)
    print(y, part.height, part.select(pl.col("trade_date").n_unique()).item(), "days")
