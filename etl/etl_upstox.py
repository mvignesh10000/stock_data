#!/usr/bin/env python3
"""Upstox lake (data/upstox) -> canonical Parquet for the Rust engine (true exchange 1-minute OHLC+OI).

Input : data/upstox/index/{NAME}_1min.parquet, data/upstox/options/{NAME}/expiry=YYYY-MM-DD.parquet
Output: data/parquet/{NAME}_UPX/expiry=YYYY-MM-DD/data.parquet, rows for expiry_rank 0 (trade days for which this
        is the nearest expiry) and expiry_rank 1 (trade days for which it is the next expiry; calendars).
Only trade days whose rank-0 AND previous expiry are both in the lake are emitted (no rank gaps at the edges).
375-minute grid 09:15..15:29 (bars after 15:29 since the Aug-2026 hours extension are dropped; strategies exit
earlier). Missing minutes forward-filled from the contract's last close (open=high=low=close, volume 0).

Usage: python etl/etl_upstox.py NIFTY|SENSEX [--force]
"""
import datetime as dt, glob, os, sys
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKE = os.path.join(ROOT, "data/upstox")
PRUNE = {"NIFTY": 1500, "SENSEX": 5000}
name = sys.argv[1]
force = "--force" in sys.argv
out_root = os.path.join(ROOT, f"data/parquet/{name}_UPX")

files = sorted(glob.glob(f"{LAKE}/options/{name}/expiry=*.parquet"))
exps = [dt.date.fromisoformat(os.path.basename(f)[7:17]) for f in files]
fmap = dict(zip(exps, files))

spot = pl.read_parquet(f"{LAKE}/index/{name}_1min.parquet").with_columns(
    pl.col("ts").dt.date().alias("d"),
    (pl.col("ts").dt.hour().cast(pl.Int32) * 60 + pl.col("ts").dt.minute().cast(pl.Int32) - 555).alias("m"),
).filter(pl.col("m").is_between(0, 374))
tdays = sorted(spot["d"].unique().to_list())
grid_m = pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32})


def rank_of(d):
    """(rank0 expiry, rank1 expiry) of trade day d from the lake's expiry list, or None if not contiguous."""
    i = next((k for k, e in enumerate(exps) if e >= d), None)
    if i is None or i == 0:  # nearest unknown, or the previous expiry is missing (lake edge)
        return None
    return exps[i], (exps[i + 1] if i + 1 < len(exps) else None)


assign = {}  # expiry -> [(trade_day, rank)]
for d in tdays:
    r = rank_of(d)
    if not r:
        continue
    assign.setdefault(r[0], []).append((d, 0))
    if r[1] is not None:
        assign.setdefault(r[1], []).append((d, 1))

ymd = lambda c: (pl.col(c).dt.year().cast(pl.UInt32) * 10000 + pl.col(c).dt.month().cast(pl.UInt32) * 100 + pl.col(c).dt.day().cast(pl.UInt32))
n_out = 0
for e, lst in sorted(assign.items()):
    out = f"{out_root}/expiry={e}/data.parquet"
    if os.path.exists(out) and not force and os.path.getmtime(out) > os.path.getmtime(fmap[e]):
        continue
    dr = pl.DataFrame(lst, schema={"d": pl.Date, "expiry_rank": pl.UInt8}, orient="row")
    sp = (dr.select("d").join(grid_m, how="cross").join(spot.select("d", "m", "open", "high", "low", "close"), on=["d", "m"], how="left")
          .sort("d", "m").with_columns(pl.col("open", "high", "low", "close").forward_fill().backward_fill().over("d"))
          .select("d", "m", *[pl.col(c).cast(pl.Float32).alias("spot_" + c) for c in ("open", "high", "low", "close")]))
    s0 = sp.filter(pl.col("m") == 0).select("d", pl.col("spot_open").alias("s0"))
    x = pl.read_parquet(fmap[e]).with_columns(
        pl.col("ts").dt.date().alias("d"),
        (pl.col("ts").dt.hour().cast(pl.Int32) * 60 + pl.col("ts").dt.minute().cast(pl.Int32) - 555).alias("m"),
    ).filter(pl.col("m").is_between(0, 374)).join(dr, on="d").join(s0, on="d").filter(
        (pl.col("strike").cast(pl.Float32) - pl.col("s0")).abs() <= PRUNE[name]).select(
        "d", "expiry_rank", "m", pl.col("strike").cast(pl.UInt32), (pl.col("opt") == "CE").alias("is_call"),
        *[pl.col(c).cast(pl.Float32) for c in ("open", "high", "low", "close")],
        pl.col("volume").clip(0, 4e9).cast(pl.UInt32), pl.col("oi").clip(0, 4e9).cast(pl.UInt32))
    x = x.unique(["d", "strike", "is_call", "m"], keep="last")
    if x.height == 0:
        continue
    keys = x.select("d", "expiry_rank", "strike", "is_call").unique()
    full = (keys.join(grid_m, how="cross").join(x, on=["d", "expiry_rank", "strike", "is_call", "m"], how="left")
            .sort("d", "expiry_rank", "is_call", "strike", "m")
            .with_columns(pl.col("close").forward_fill().over("d", "strike", "is_call").alias("cf"),
                          pl.col("oi").forward_fill().over("d", "strike", "is_call"), pl.col("volume").fill_null(0))
            .with_columns(*[pl.col(c).fill_null(pl.col("cf")) for c in ("open", "high", "low", "close")])
            .filter(pl.col("close").is_not_null()).join(sp, on=["d", "m"]))
    full = full.with_columns(pl.lit(e).alias("exp")).select(
        ymd("d").alias("trade_date"), ymd("exp").alias("expiry_date"),
        (pl.col("exp") - pl.col("d")).dt.total_days().cast(pl.UInt8).alias("dte"),
        "expiry_rank", pl.col("m").cast(pl.UInt16).alias("minute_idx"),
        "spot_open", "spot_high", "spot_low", "spot_close", "strike", "is_call",
        "open", "high", "low", "close", "volume", pl.col("oi").fill_null(0),
    ).sort("trade_date", "expiry_rank", "is_call", "strike", "minute_idx")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    full.write_parquet(out + ".tmp", compression="zstd", compression_level=3)
    os.replace(out + ".tmp", out)
    n_out += 1
    print(name, e, "days", full["trade_date"].n_unique(), "rows", full.height, flush=True)
print(name, "expiry files written:", n_out, "| lake expiries:", len(exps))
