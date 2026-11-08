#!/usr/bin/env python3
"""Merge the day's 1-minute part files into data/upstox/bidask/date=YYYY-MM-DD/day.parquet (idempotent),
then remove the parts. Also appends a daily spread summary to data/upstox/bidask/spread_summary.parquet."""
import glob, os, sys
import polars as pl
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
B = os.path.join(ROOT, "data/upstox/bidask")
for d in sorted(glob.glob(f"{B}/date=*")):
    parts = sorted(glob.glob(f"{d}/part-*.parquet"))
    if not parts:
        continue
    day = f"{d}/day.parquet"
    frames = [pl.read_parquet(day)] if os.path.exists(day) else []
    frames += [pl.read_parquet(p) for p in parts]
    df = pl.concat(frames).unique(["ts", "key"]).sort("ts", "key")
    df.write_parquet(day + ".tmp", compression="zstd", compression_level=6)
    os.replace(day + ".tmp", day)
    for p in parts:
        os.remove(p)
    o = df.filter(pl.col("opt").is_not_null() & (pl.col("bid") > 0) & (pl.col("ask") > 0))
    s = (o.with_columns(((pl.col("ask") - pl.col("bid")) / ((pl.col("ask") + pl.col("bid")) / 2) * 100).alias("spr_pct"),
                        ((pl.col("strike") - pl.col("spot")).abs()).alias("dist"), pl.col("ts").dt.date().alias("date"),
                        (pl.col("expiry").str.to_date() == pl.col("ts").dt.date()).alias("expiry_day"))
         .group_by("date", "name", "expiry_day").agg(pl.len().alias("n"), pl.col("spr_pct").median().alias("spr_med_pct"),
                        pl.col("spr_pct").quantile(0.9).alias("spr_p90_pct"), (pl.col("ask") - pl.col("bid")).median().alias("spr_med_rs")))
    sp = f"{B}/spread_summary.parquet"
    if os.path.exists(sp):
        s = pl.concat([pl.read_parquet(sp), s]).unique(["date", "name", "expiry_day"], keep="last")
    s.sort("date").write_parquet(sp)
    print(os.path.basename(d), df.height, "rows ->", day)
