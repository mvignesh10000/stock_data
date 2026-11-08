"""Synthetic intra-minute wicks for the LTP-only source (2025-26).

The LTP source only gives the last price each minute, so a stop that a real 1-minute HIGH would have
touched is invisible. We calibrate the empirical distribution of upper/lower wicks on TRUE OHLC bars
(2024, ICICI Breeze; verified 99.96% identical to our 2024 source) by premium bucket x DTE bucket, and
inject a deterministic pseudo-random draw (hash of contract+minute) on every traded LTP bar:
    high = max(open, close) * (1 + up_draw),  low = min(open, close) * (1 - dn_draw)
CE/PE draws are independent (conservative: real wicks of CE and PE are anti-correlated).
"""
import sys, json, polars as pl
src, wick_json, out = sys.argv[1], sys.argv[2], sys.argv[3]
table = json.load(open(wick_json))["wick_2024_breeze"]
rows = [{"pb": k.split("|")[0], "db": k.split("|")[1], "qi": i, "uq": v["up"][i], "dq": v["dn"][i]} for k, v in table.items() for i in range(99)]
qt = pl.DataFrame(rows).with_columns(pl.col("qi").cast(pl.Int64))
qu = qt.select("pb", "db", pl.col("qi").alias("iu"), "uq")
qd = qt.select("pb", "db", pl.col("qi").alias("idn"), "dq")
import glob, os
for f in sorted(glob.glob(f"{src}/year=*/data.parquet")):
    df = pl.read_parquet(f)
    df = df.with_columns(
        pl.when(pl.col("close") < 10).then(pl.lit("p<10")).when(pl.col("close") < 30).then(pl.lit("p10-30"))
          .when(pl.col("close") < 80).then(pl.lit("p30-80")).when(pl.col("close") < 200).then(pl.lit("p80-200")).otherwise(pl.lit("p200+")).alias("pb"),
        pl.when(pl.col("dte") == 0).then(pl.lit("d0")).when(pl.col("dte") <= 2).then(pl.lit("d1-2")).otherwise(pl.lit("d3+")).alias("db"),
        (pl.struct("trade_date", "strike", "is_call", "minute_idx").hash(seed=7) % 99).cast(pl.Int64).alias("iu"),
        (pl.struct("trade_date", "strike", "is_call", "minute_idx").hash(seed=11) % 99).cast(pl.Int64).alias("idn"),
    ).join(qu, on=["pb", "db", "iu"], how="left").join(qd, on=["pb", "db", "idn"], how="left")
    df = df.with_columns(
        pl.when(pl.col("volume") > 0).then(pl.col("uq")).otherwise(0.0).fill_null(0.0).alias("u"),
        pl.when(pl.col("volume") > 0).then(pl.col("dq")).otherwise(0.0).fill_null(0.0).alias("dd"),
    ).with_columns(
        (pl.max_horizontal("open", "close") * (1 + pl.col("u"))).cast(pl.Float32).alias("high"),
        (pl.min_horizontal("open", "close") * (1 - pl.col("dd").clip(0, 0.95))).cast(pl.Float32).alias("low"),
    ).drop("pb", "db", "iu", "idn", "uq", "dq", "u", "dd")
    y = f.split("year=")[1].split("/")[0]
    p = f"{out}/year={y}"; os.makedirs(p, exist_ok=True)
    df.write_parquet(f"{p}/data.parquet", compression="zstd", compression_level=3)
    print(y, df.height, "mean (high/close-1) on traded bars:", df.filter(pl.col("volume") > 0).select((pl.col("high") / pl.col("close") - 1).mean()).item())
