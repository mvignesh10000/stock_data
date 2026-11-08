#!/usr/bin/env python3
"""Trend vs sideways days and what OI says about them.

For every trading day we measure, using ONLY information available by 09:30 (ex-ante features):
  gap %, previous-day range %, previous-day trend efficiency, India VIX (prev close), opening range
  09:15-09:30 width %, ATM straddle at 09:30 as % of spot (implied move), PCR (total put OI / call OI,
  strikes within +-1000 of spot), distance of the max-call-OI strike above spot and max-put-OI strike
  below spot (OI walls), first-15-min OI change of CE vs PE near ATM, trading DTE, weekday.
Outcome (09:30 -> 15:15): realised range % and trend efficiency = |close - open| / (high - low).
  SIDEWAYS = range below the median AND efficiency < 0.35;  TREND = efficiency >= 0.6 and range above median.
Then: which features separate the two (effect sizes), can a simple rule predict SIDEWAYS out of sample
(train 2024, test 2025-26), do OI walls contain the day (pinning) and does early OI change predict direction.
"""
import json, math, os, sys
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/audit_v9")
lake = pl.concat([pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY_OHLC/*/*.parquet"),
                  pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY/*/*.parquet").filter(pl.col("trade_date") >= 20250101)]).filter(pl.col("expiry_rank") == 0)
spot = lake.select("trade_date", "minute_idx", "spot_open", "spot_high", "spot_low", "spot_close").unique(["trade_date", "minute_idx"]).collect().sort("trade_date", "minute_idx")
opt = lake.filter(pl.col("minute_idx").is_in([0, 14])).select("trade_date", "minute_idx", "dte", "strike", "is_call", "close", "oi").collect()
vix = pl.read_csv(f"{ROOT}/data/india_vix_daily.csv").select(pl.col("date").alias("trade_date"), pl.col("prev_close").alias("vix"))

# ---- per-day spot stats
g = spot.group_by("trade_date").agg(
    pl.col("spot_open").first().alias("o915"),
    pl.col("spot_close").filter(pl.col("minute_idx") <= 14).max().alias("orh"), pl.col("spot_close").filter(pl.col("minute_idx") <= 14).min().alias("orl"),
    pl.col("spot_close").filter(pl.col("minute_idx") == 14).first().alias("c930"),
    pl.col("spot_high").filter(pl.col("minute_idx").is_between(15, 359)).max().alias("h"), pl.col("spot_low").filter(pl.col("minute_idx").is_between(15, 359)).min().alias("l"),
    pl.col("spot_close").filter(pl.col("minute_idx") == 359).first().alias("c1515"),
    pl.col("spot_high").max().alias("dh"), pl.col("spot_low").min().alias("dl"), pl.col("spot_close").last().alias("dc"), pl.col("spot_open").first().alias("do"),
).sort("trade_date")
g = g.with_columns(
    pl.col("dc").shift(1).alias("prev_close"), ((pl.col("dh") - pl.col("dl")) / pl.col("do") * 100).shift(1).alias("prev_range_pct"),
    ((pl.col("dc") - pl.col("do")).abs() / (pl.col("dh") - pl.col("dl"))).shift(1).alias("prev_eff"),
).with_columns(
    ((pl.col("o915") / pl.col("prev_close") - 1) * 100).alias("gap_pct"),
    ((pl.col("orh") - pl.col("orl")) / pl.col("o915") * 100).alias("or_pct"),
    ((pl.col("h") - pl.col("l")) / pl.col("c930") * 100).alias("range_pct"),
    ((pl.col("c1515") - pl.col("c930")).abs() / (pl.col("h") - pl.col("l"))).alias("eff"),
    ((pl.col("c1515") - pl.col("c930")) / pl.col("c930") * 100).alias("move_pct"),
)

# ---- OI / premium features at 09:30 (minute 14) and change since 09:15 (minute 0)
o14 = opt.filter(pl.col("minute_idx") == 14).join(g.select("trade_date", "c930"), on="trade_date").filter((pl.col("strike") - pl.col("c930")).abs() <= 1000)
atm = o14.with_columns((pl.col("strike") - pl.col("c930")).abs().alias("dist")).sort("dist").group_by("trade_date", "is_call").agg(pl.col("close").first().alias("p"), pl.col("strike").first().alias("k"))
straddle = atm.group_by("trade_date").agg(pl.col("p").sum().alias("straddle"))
pcr = o14.group_by("trade_date").agg((pl.col("oi").filter(~pl.col("is_call")).sum().cast(pl.Float64) / pl.col("oi").filter(pl.col("is_call")).sum().cast(pl.Float64)).alias("pcr"), pl.col("dte").first().alias("dte")) \
    .with_columns(pl.when(pl.col("pcr").is_finite() & (pl.col("pcr") > 0.05) & (pl.col("pcr") < 20)).then(pl.col("pcr")).otherwise(None).alias("pcr"))
cw = o14.filter(pl.col("is_call") & (pl.col("strike") >= pl.col("c930"))).sort("oi", descending=True).group_by("trade_date").agg(pl.col("strike").first().alias("call_wall"))
pw = o14.filter(~pl.col("is_call") & (pl.col("strike") <= pl.col("c930"))).sort("oi", descending=True).group_by("trade_date").agg(pl.col("strike").first().alias("put_wall"))
# max pain at 09:30
mp_rows = []
for (d,), part in o14.group_by(["trade_date"]):
    ks = sorted(set(part["strike"].to_list()))
    ce = dict(zip(part.filter(pl.col("is_call"))["strike"].to_list(), part.filter(pl.col("is_call"))["oi"].to_list()))
    pe = dict(zip(part.filter(~pl.col("is_call"))["strike"].to_list(), part.filter(~pl.col("is_call"))["oi"].to_list()))
    best = min(ks, key=lambda s: sum(oi * max(0, s - k) for k, oi in ce.items()) + sum(oi * max(0, k - s) for k, oi in pe.items()))
    mp_rows.append((d, best))
mp = pl.DataFrame(mp_rows, schema=["trade_date", "max_pain"], orient="row")
# early OI change near ATM (+-200): CE vs PE
o0 = opt.filter(pl.col("minute_idx") == 0).select("trade_date", "strike", "is_call", pl.col("oi").alias("oi0"))
dch = o14.filter((pl.col("strike") - pl.col("c930")).abs() <= 200).join(o0, on=["trade_date", "strike", "is_call"]).with_columns((pl.col("oi").cast(pl.Float64) - pl.col("oi0").cast(pl.Float64)).alias("doi")) \
    .group_by("trade_date").agg(pl.col("doi").filter(pl.col("is_call")).sum().alias("dce"), pl.col("doi").filter(~pl.col("is_call")).sum().alias("dpe"))
F = g.join(straddle, on="trade_date").join(pcr, on="trade_date").join(cw, on="trade_date", how="left").join(pw, on="trade_date", how="left") \
    .join(mp, on="trade_date", how="left").join(dch, on="trade_date", how="left").join(vix, on="trade_date", how="left").drop_nulls(["prev_close"])
F = F.with_columns((pl.col("straddle") / pl.col("c930") * 100).alias("implied_pct"),
                   ((pl.col("call_wall") - pl.col("c930")) / pl.col("c930") * 100).alias("cwall_pct"),
                   ((pl.col("c930") - pl.col("put_wall")) / pl.col("c930") * 100).alias("pwall_pct"),
                   ((pl.col("dpe") - pl.col("dce")) / (pl.col("dpe").abs() + pl.col("dce").abs() + 1)).alias("oi_tilt"),
                   pl.col("gap_pct").abs().alias("abs_gap"))
med_range = F["range_pct"].median()
F = F.with_columns(pl.when((pl.col("range_pct") < med_range) & (pl.col("eff") < 0.35)).then(pl.lit("SIDEWAYS"))
                   .when((pl.col("eff") >= 0.6) & (pl.col("range_pct") >= med_range)).then(pl.lit("TREND")).otherwise(pl.lit("MIXED")).alias("type"))
out = {"n_days": F.height, "counts": dict(F["type"].value_counts().rows())}
feats = ["abs_gap", "prev_range_pct", "prev_eff", "vix", "or_pct", "implied_pct", "pcr", "cwall_pct", "pwall_pct", "oi_tilt", "dte"]
eff_rows = []
for f in feats:
    a = F.filter(pl.col("type") == "SIDEWAYS")[f].drop_nulls(); b = F.filter(pl.col("type") == "TREND")[f].drop_nulls()
    sd = math.sqrt((a.var() + b.var()) / 2) if a.len() > 2 and b.len() > 2 else 1
    eff_rows.append([f, round(a.median(), 3), round(b.median(), 3), round((a.mean() - b.mean()) / sd, 2)])
out["effect_sizes"] = sorted(eff_rows, key=lambda r: -abs(r[3]))
print("counts", out["counts"]); print("feature | median SIDEWAYS | median TREND | Cohen d"); [print(r) for r in out["effect_sizes"]]
# ---- simple OOS predictor: rank the top features on 2024, choose threshold on 2024, test on 2025-26
tr = F.filter(pl.col("trade_date") < 20250101); te = F.filter(pl.col("trade_date") >= 20250101)
best = None
for f, *_ in out["effect_sizes"][:5]:
    for q in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        th = tr[f].quantile(q)
        for sign in (1, -1):
            sel = tr.filter((pl.col(f) * sign) <= th * sign)
            if sel.height < 30: continue
            p = (sel["type"] == "SIDEWAYS").mean(); base = (tr["type"] == "SIDEWAYS").mean()
            lift = p - base
            if best is None or lift > best[0]:
                best = (lift, f, q, th, sign, p, base, sel.height)
lift, f, q, th, sign, p, base, n = best
sel_te = te.filter((pl.col(f) * sign) <= th * sign)
out["predictor"] = {"feature": f, "rule": f"{f} {'<=' if sign == 1 else '>='} {th:.3f}", "train_sideways_rate_selected": p, "train_base": base, "train_n": n,
                    "test_sideways_rate_selected": (sel_te["type"] == "SIDEWAYS").mean(), "test_base": (te["type"] == "SIDEWAYS").mean(), "test_n": sel_te.height,
                    "test_trend_rate_selected": (sel_te["type"] == "TREND").mean(), "test_trend_base": (te["type"] == "TREND").mean()}
print("best ex-ante sideways rule (fit 2024, tested 2025-26):", out["predictor"])
# ---- OI walls containment & pinning (expiry days)
F = F.with_columns(((pl.col("h") <= pl.col("call_wall")) & (pl.col("l") >= pl.col("put_wall"))).alias("contained"),
                   (pl.col("c1515") - pl.col("max_pain")).abs().alias("d_mp"), (pl.col("c1515") - pl.col("c930")).abs().alias("d_open"))
e = F.filter(pl.col("dte") == 0)
out["oi_walls"] = {"all_days_contained_pct": F["contained"].mean() * 100, "expiry_contained_pct": e["contained"].mean() * 100,
                   "median_wall_width_pct": ((F["call_wall"] - F["put_wall"]) / F["c930"] * 100).median(),
                   "expiry_close_nearer_maxpain_than_0930_pct": (e["d_mp"] < e["d_open"]).mean() * 100,
                   "expiry_median_dist_close_to_maxpain": e["d_mp"].median(), "expiry_median_dist_close_to_0930": e["d_open"].median()}
print("OI walls / pinning:", {k: round(v, 2) for k, v in out["oi_walls"].items()})
# ---- does early OI tilt (PE writing > CE writing) predict the rest-of-day direction?
x = F.drop_nulls(["oi_tilt"]).with_columns(pl.col("move_pct").sign().alias("dirn"))
hit = (x.filter(pl.col("oi_tilt").abs() > 0.2).select(((pl.col("oi_tilt").sign() == pl.col("dirn"))).mean()).item())
cor = x.select(pl.corr("oi_tilt", "move_pct")).item()
pc = F.drop_nulls(["pcr"]).select(pl.corr("pcr", "move_pct")).item()
out["oi_direction"] = {"oi_tilt_hit_rate_when_strong": hit * 100, "corr_oi_tilt_vs_rest_of_day_move": cor, "corr_pcr_vs_rest_of_day_move": pc,
                       "n_strong": x.filter(pl.col("oi_tilt").abs() > 0.2).height}
print("OI direction:", {k: round(v, 3) for k, v in out["oi_direction"].items()})
F.select("trade_date", "type", *feats, "range_pct", "eff", "move_pct", "call_wall", "put_wall", "max_pain", "c930").write_csv(f"{OUT}/day_features.csv")
json.dump(out, open(f"{OUT}/regime_oi_study.json", "w"), default=str, indent=1)
