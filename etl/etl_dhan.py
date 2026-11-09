#!/usr/bin/env python3
"""Dhan rolling expired-options (data/dhan/<SET>/*.parquet) -> canonical Parquet data/parquet/<NAME>_DHAN/year=YYYY/

Rolling -> per-contract: every row carries the actual strike, so each minute the union of offsets ATM-10..ATM+10 gives
the bars of all contracts within +/-10 strikes of spot. Duplicate (minute, strike, type) rows coming from different
offsets are collapsed (they are the same contract; agreement is reported).
Expiry date of the rank-0 (expiryCode 1) series is not in the response. It is inferred: a trading day is an expiry
day when the ATM straddle (offset 0 CE + PE) closes at 15:29 below 0.12% of spot (non-expiry days are far above),
and expiry_date(d) = first inferred expiry >= d. The weekday distribution of inferred expiries is printed as a check.
A contract that drifts outside the +/-10 band has no bars; within a day it is forward-filled from its last close
(affects far wings only; the share of filled bars is printed).
Rank 1 (expiryCode 2, NIFTY_W2, +/-3 strikes) is written with expiry_rank 1 when available.
Usage: python etl/etl_dhan.py NIFTY|SENSEX|BANKNIFTY
"""
import glob, os, sys
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name = sys.argv[1]
STEP = {"NIFTY": 50, "SENSEX": 100, "BANKNIFTY": 100}[name]


def load(setname):
    fs = sorted(glob.glob(f"{ROOT}/data/dhan/{setname}/*.parquet"))
    if not fs:
        return None
    d = pl.concat([pl.read_parquet(f) for f in fs]).with_columns(pl.col("ts").dt.date().alias("d"),
        (pl.col("ts").dt.hour().cast(pl.Int32) * 60 + pl.col("ts").dt.minute().cast(pl.Int32) - 555).alias("m"))
    return d.filter(pl.col("m").is_between(0, 374) & pl.col("strike").is_not_null() & pl.col("close").is_not_null())


r0 = load(f"{name}_W1")
# ---- expiry inference
atm = r0.filter((pl.col("offset") == 0) & (pl.col("m") == 374)).group_by("d").agg(
    pl.col("close").sum().alias("straddle"), pl.col("spot").first().alias("spot"), pl.len().alias("n"))
atm = atm.filter(pl.col("n") == 2).with_columns((pl.col("straddle") / pl.col("spot") * 100).alias("pct")).sort("d")
exp_days = atm.filter(pl.col("pct") < 0.12)["d"].to_list()
wd = pl.Series([d.weekday() for d in exp_days]).value_counts().sort("")
print(name, "inferred expiry days:", len(exp_days), "weekday counts (0=Mon):", dict(zip(*[wd[c].to_list() for c in wd.columns])))
print("  straddle% at 15:29 — expiry days max", round(atm.filter(pl.col("pct") < 0.12)["pct"].max(), 3),
      "| other days min", round(atm.filter(pl.col("pct") >= 0.12)["pct"].min(), 3))
emap = pl.DataFrame({"e": exp_days}).sort("e")


def canon(df, rank):
    # collapse offsets -> contracts
    agree = df.group_by("ts", "strike", "opt").agg(pl.col("close").n_unique().alias("u"))
    print(f"  rank {rank}: duplicate-offset rows disagreeing on close: {(agree['u'] > 1).mean() * 100:.2f}%")
    x = df.sort("offset").unique(["ts", "strike", "opt"], keep="first")
    days = x.select("d").unique().sort("d").join_asof(emap.rename({"e": "exp"}).with_columns(pl.col("exp").alias("d")),
                                                       on="d", strategy="forward").drop_nulls("exp")
    x = x.join(days.select("d", "exp"), on="d")
    if rank == 1:  # next expiry after the rank-0 expiry
        nxt = emap.with_columns(pl.col("e").shift(-1).alias("exp1")).rename({"e": "exp"})
        x = x.join(nxt, on="exp").drop("exp").rename({"exp1": "exp"}).drop_nulls("exp")
    spot = (x.group_by("d", "m").agg(pl.col("spot").median().alias("spot_close")).sort("d", "m")
            .with_columns(pl.col("spot_close").shift(1).over("d").fill_null(pl.col("spot_close")).alias("spot_open")))
    spot = spot.with_columns(pl.max_horizontal("spot_open", "spot_close").alias("spot_high"), pl.min_horizontal("spot_open", "spot_close").alias("spot_low"))
    grid = x.select("d", "exp", "strike", "opt").unique().join(pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32}), how="cross")
    full = (grid.join(x.select("d", "m", "strike", "opt", "open", "high", "low", "close", "volume", "oi"), on=["d", "m", "strike", "opt"], how="left")
            .sort("d", "opt", "strike", "m").with_columns(pl.col("close").is_null().alias("filled"),
            pl.col("close").forward_fill().over("d", "strike", "opt").alias("cf"), pl.col("oi").forward_fill().over("d", "strike", "opt"),
            pl.col("volume").fill_null(0))
            .with_columns(*[pl.col(c).fill_null(pl.col("cf")) for c in ("open", "high", "low", "close")])
            .filter(pl.col("close").is_not_null()).join(spot, on=["d", "m"]))
    s0 = full.filter(pl.col("m") == 0).group_by("d").agg(pl.col("spot_open").first().alias("s0"))
    full = full.join(s0, on="d").filter(((pl.col("strike") - pl.col("s0")).abs() <= 1500 if name == "NIFTY" else (pl.col("strike") - pl.col("s0")).abs() <= 5000))
    full = full.filter(pl.col("strike") % STEP == 0)
    print(f"  rank {rank}: forward-filled bar share {full['filled'].mean() * 100:.1f}%")
    ymd = lambda c: (pl.col(c).dt.year().cast(pl.UInt32) * 10000 + pl.col(c).dt.month().cast(pl.UInt32) * 100 + pl.col(c).dt.day().cast(pl.UInt32))
    return full.select(ymd("d").alias("trade_date"), ymd("exp").alias("expiry_date"), (pl.col("exp") - pl.col("d")).dt.total_days().cast(pl.UInt8).alias("dte"),
                       pl.lit(rank, pl.UInt8).alias("expiry_rank"), pl.col("m").cast(pl.UInt16).alias("minute_idx"),
                       *[pl.col(c).cast(pl.Float32) for c in ("spot_open", "spot_high", "spot_low", "spot_close")],
                       pl.col("strike").cast(pl.UInt32), (pl.col("opt") == "CE").alias("is_call"),
                       *[pl.col(c).cast(pl.Float32) for c in ("open", "high", "low", "close")],
                       pl.col("volume").fill_null(0).clip(0, 4e9).cast(pl.UInt32), pl.col("oi").fill_null(0).clip(0, 4e9).cast(pl.UInt32))


parts = [canon(r0, 0)]
r1 = load(f"{name}_W2")
if r1 is not None:
    parts.append(canon(r1, 1))
out = pl.concat(parts).sort("trade_date", "expiry_rank", "is_call", "strike", "minute_idx")
for y in sorted(set((out["trade_date"] // 10000).to_list())):
    p = f"{ROOT}/data/parquet/{name}_DHAN/year={y}"
    os.makedirs(p, exist_ok=True)
    part = out.filter((pl.col("trade_date") // 10000) == y)
    part.write_parquet(f"{p}/data.parquet", compression="zstd", compression_level=3)
    print(name, y, "rows", part.height, "days", part["trade_date"].n_unique(), "expiry days", part.filter(pl.col("dte") == 0)["trade_date"].n_unique())
