"""(1) Cross-check our 2024 OHLC source against an independent source (npartha / ICICI Breeze).
(2) Measure intra-minute wick distribution (how far high exceeds max(open,close)) on TRUE OHLC data,
    bucketed by premium and DTE, for 2024 (Breeze) and Oct-2026 (Kite, current regime) -> etl/wick_model.json
"""
import sys, json, polars as pl
src, ours, out = sys.argv[1], sys.argv[2], sys.argv[3]
b = pl.read_csv(f"{src}/nifty50_options_1m_2024-01-01_2024-10-24.csv", try_parse_dates=True)
k = pl.read_csv(f"{src}/nifty50_options_1m_2026-10-07_2026-11-04.csv", try_parse_dates=True)
def norm(df):
    return df.with_columns(
        pl.col("datetime").dt.date().alias("d"),
        ((pl.col("datetime").dt.hour().cast(pl.Int32) * 60 + pl.col("datetime").dt.minute().cast(pl.Int32)) - 555).alias("m"),
        pl.col("expiry").cast(pl.Date).alias("exp"), (pl.col("option_type") == "CE").alias("is_call"),
        pl.col("strike").cast(pl.UInt32))
b, k = norm(b), norm(k)
# (1) cross-check closes vs our parquet (NIFTY_OHLC, rank-0 expiry)
o = pl.read_parquet(f"{ours}/NIFTY_OHLC/year=2024/data.parquet").filter(pl.col("expiry_rank") == 0).with_columns(
    pl.col("trade_date").cast(pl.Utf8).str.to_date("%Y%m%d").alias("d"), pl.col("expiry_date").cast(pl.Utf8).str.to_date("%Y%m%d").alias("exp"),
    pl.col("minute_idx").cast(pl.Int32).alias("m"))
j = b.join(o.filter(pl.col("volume") > 0), on=["d", "exp", "strike", "is_call", "m"], suffix="_o").filter(pl.col("volume") > 0)
j = j.with_columns(((pl.col("close") - pl.col("close_o")).abs() / pl.col("close_o")).alias("rel"))
res = {"crosscheck_rows": j.height,
       "close_abs_rel_diff_median": j["rel"].median(), "close_abs_rel_diff_p95": j["rel"].quantile(0.95),
       "close_exact_match_pct": float((j["rel"] < 1e-6).mean() * 100),
       "high_exact_match_pct": float(((j["high"] - j["high_o"]).abs() < 0.051).mean() * 100)}
# (2) wick model on true OHLC
def wick(df, label):
    df = df.filter((pl.col("volume") > 0) & (pl.col("m").is_between(0, 374)))
    dte = (pl.col("exp") - pl.col("d")).dt.total_days()
    df = df.with_columns(
        (pl.col("high") / pl.max_horizontal("open", "close") - 1).alias("up"),
        (1 - pl.col("low") / pl.min_horizontal("open", "close")).alias("dn"),
        pl.when(pl.col("close") < 10).then(pl.lit("p<10")).when(pl.col("close") < 30).then(pl.lit("p10-30"))
          .when(pl.col("close") < 80).then(pl.lit("p30-80")).when(pl.col("close") < 200).then(pl.lit("p80-200")).otherwise(pl.lit("p200+")).alias("pb"),
        pl.when(dte == 0).then(pl.lit("d0")).when(dte <= 2).then(pl.lit("d1-2")).otherwise(pl.lit("d3+")).alias("db"))
    g = df.group_by("pb", "db").agg(pl.len().alias("n"), *[pl.col("up").quantile(q).alias(f"up_q{int(q*100)}") for q in (0.5, 0.75, 0.9, 0.95, 0.99)],
                                   pl.col("up").max().alias("up_max"), *[pl.col("dn").quantile(q).alias(f"dn_q{int(q*100)}") for q in (0.5, 0.9, 0.99)]).sort("pb", "db")
    print(label); print(g)
    # quantile table (percentiles 1..99) per bucket for sampling
    qs = [i / 100 for i in range(1, 100)]
    table = {}
    for (pb, db), part in df.group_by(["pb", "db"]):
        if part.height < 500: continue
        table[f"{pb}|{db}"] = {"up": [float(part["up"].quantile(q)) for q in qs], "dn": [float(part["dn"].quantile(q)) for q in qs], "n": part.height}
    return table
pl.Config.set_tbl_cols(14); pl.Config.set_tbl_width_chars(250)
res["wick_2024_breeze"] = wick(b, "2024 Breeze true OHLC")
res["wick_2026_kite"] = wick(k, "Oct-2026 Kite true OHLC")
json.dump(res, open(out, "w"))
print({k_: v for k_, v in res.items() if not k_.startswith("wick")})
