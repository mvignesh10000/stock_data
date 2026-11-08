#!/usr/bin/env python3
"""ETL: Zenodo record 10899828 "Nifty spot, futures and options one-minute data from 2017 to 2020" (CC0)
-> canonical Parquet data/parquet/NIFTY_ZEN/year=YYYY/data.parquet  (expiry_rank 0 = the MONTHLY expiry only).

Source facts (checked):
  * options: one file per contract (".txt" 2017-18 named "PE 10250", ".csv" 2019-20 named "NIFTY11050CE"),
    rows: name, yyyy/mm/dd, hh:mm, O, H, L, C, volume. No OI. Only MONTHLY expiries (no weeklies), Jan-2018 absent.
  * bars are trade-only (a minute without trades has no row) and stamped with the bar END (first spot bar 09:16),
    so minute_idx = hh:mm - 09:16  (09:16 -> 0 = the 09:15 bar, same convention as the rest of the lake).
  * expiry of a monthly folder = last trade date in that folder.
  * rows after 15:30 (Muhurat/special sessions) dropped.
Missing minutes are forward-filled from the contract's last trade OF THE SAME DAY (no stale carry-over between days);
before a contract's first trade of the day it has no price (the engine then cannot use that strike that minute).
Usage: python etl/etl_zenodo.py <extracted root containing "NiftyOptions 20xx" and "20xx/20xx/NIFTY.csv"> <out parquet root>
"""
import glob, os, re, sys
import polars as pl

root, out = sys.argv[1], sys.argv[2]
PRUNE = 1500
NAME = re.compile(r"(?:(CE|PE)\s*(\d+))|(?:NIFTY(?:\d{2}[A-Za-z]{3}\d{2})?(\d+)(CE|PE))")  # NIFTY11050CE / NIFTY25JUN2010100PE


def read_any(f):
    x = pl.read_csv(open(f, "rb").read(), has_header=False, truncate_ragged_lines=True, ignore_errors=True, infer_schema=False)[:, :8]
    x.columns = ["name", "date", "time", "open", "high", "low", "close", "volume"]
    return x.with_columns(*[pl.col(c).cast(pl.Float64, strict=False) for c in ("open", "high", "low", "close", "volume")])


def with_m(df):
    hm = df["time"].str.split(":")
    return df.with_columns(pl.col("date").str.strip_chars().str.to_date("%Y/%m/%d").alias("d"),
                           (hm.list.get(0).cast(pl.Int32) * 60 + hm.list.get(1).cast(pl.Int32) - 556).alias("m")).filter(pl.col("m").is_between(0, 374))


# ---- spot
spot = pl.concat([with_m(read_any(f))
                  for f in glob.glob(f"{root}/20*/20*/NIFTY.csv")]).unique(["d", "m"]).select(
    "d", "m", *[pl.col(c).cast(pl.Float32).alias("spot_" + c) for c in ("open", "high", "low", "close")])

# ---- options, one monthly folder at a time
months = sorted(glob.glob(f"{root}/NiftyOptions 20*/*"))
parts, log = [], []
for mdir in months:
    files = [f for f in glob.glob(f"{mdir}/**/*", recursive=True) if f.lower().endswith((".txt", ".csv"))]
    frames = []
    for f in files:
        try:
            x = read_any(f)
        except Exception:  # noqa: BLE001
            continue
        if x.height == 0:
            continue
        g = NAME.search(str(x["name"][0]).replace(" ", " "))
        if not g:
            continue
        opt, strike = (g.group(1), int(g.group(2))) if g.group(1) else (g.group(4), int(g.group(3)))
        frames.append(with_m(x).with_columns(pl.lit(strike, pl.UInt32).alias("strike"), pl.lit(opt == "CE").alias("is_call")))
    if not frames:
        continue
    x = pl.concat([f.select("d", "m", "strike", "is_call", "open", "high", "low", "close", "volume") for f in frames])
    parts.append((x["d"].max(), os.path.basename(mdir), len(files), x))
parts.sort(key=lambda t: t[0])  # folder names sort alphabetically; order by expiry
kept, prev = [], None
for exp, nm, nf, x in parts:
    x = x.with_columns(pl.lit(exp).alias("exp"))
    if prev is not None:
        x = x.filter(pl.col("d") > prev)  # rank 0 = nearest monthly only
    log.append((nm, exp, nf, x["d"].n_unique()))
    kept.append(x)
    prev = exp
opt = pl.concat(kept).unique(["d", "strike", "is_call", "m"], keep="last")
s0 = spot.filter(pl.col("m") <= 5).group_by("d").agg(pl.col("spot_open").first().alias("s0"))
opt = opt.join(s0, on="d").filter((pl.col("strike").cast(pl.Float32) - pl.col("s0")).abs() <= PRUNE).drop("s0")

grid_m = pl.DataFrame({"m": list(range(375))}, schema={"m": pl.Int32})
days = opt.select("d").unique()
sp = (days.join(grid_m, how="cross").join(spot, on=["d", "m"], how="left").sort("d", "m")
      .with_columns(pl.col("spot_open", "spot_high", "spot_low", "spot_close").forward_fill().backward_fill().over("d")))
keys = opt.select("d", "exp", "strike", "is_call").unique()
full = (keys.join(grid_m, how="cross").join(opt.drop("exp"), on=["d", "strike", "is_call", "m"], how="left")
        .sort("d", "is_call", "strike", "m")
        .with_columns(pl.col("close").forward_fill().over("d", "strike", "is_call").alias("cf"), pl.col("volume").fill_null(0))
        .with_columns(*[pl.col(c).fill_null(pl.col("cf")) for c in ("open", "high", "low", "close")])
        .filter(pl.col("close").is_not_null()).join(sp, on=["d", "m"]))
ymd = lambda c: (pl.col(c).dt.year().cast(pl.UInt32) * 10000 + pl.col(c).dt.month().cast(pl.UInt32) * 100 + pl.col(c).dt.day().cast(pl.UInt32))
full = full.select(
    ymd("d").alias("trade_date"), ymd("exp").alias("expiry_date"), (pl.col("exp") - pl.col("d")).dt.total_days().cast(pl.UInt8).alias("dte"),
    pl.lit(0, pl.UInt8).alias("expiry_rank"), pl.col("m").cast(pl.UInt16).alias("minute_idx"),
    "spot_open", "spot_high", "spot_low", "spot_close", "strike", "is_call",
    *[pl.col(c).cast(pl.Float32) for c in ("open", "high", "low", "close")],
    pl.col("volume").clip(0, 4e9).cast(pl.UInt32), pl.lit(0, pl.UInt32).alias("oi"),
).sort("trade_date", "expiry_rank", "is_call", "strike", "minute_idx")
for y in range(2017, 2021):
    part = full.filter((pl.col("trade_date") // 10000) == y)
    if part.height:
        p = f"{out}/NIFTY_ZEN/year={y}"
        os.makedirs(p, exist_ok=True)
        part.write_parquet(f"{p}/data.parquet", compression="zstd", compression_level=3)
        print(y, "rows", part.height, "days", part["trade_date"].n_unique())
for r in log:
    print("month", r)
