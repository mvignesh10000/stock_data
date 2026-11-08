#!/usr/bin/env python3
"""Deploy hedged strangles only on days predicted SIDEWAYS (ex-ante, by 09:30) — does it pay?

Configs (1 lot, entry 09:31 after the opening range is known, exit 15:10, trail-to-BE on SL legs, overall SL Rs2000):
  strangle OTM2 / OTM3 + wings OTM10;  iron fly ATM + OTM8;  OI-wall strangle (sell max-OI CE/PE within 10 steps) + wings OTM14
  x leg SL 30 / 50 %.
Day filters (thresholds learnt on 2024 ONLY, tested once on 2025-26):
  none; opening range 09:15-09:30 <= q; implied move (ATM straddle/spot) <= q; VIX (prev close) band; OR & implied both low.
Run on all trading days and on non-expiry days only.
"""
import json, os, sys, itertools
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5
from regime_v8 import stats

ROOT = v5.ROOT; OUT = os.path.join(ROOT, "results/audit_v9"); v5.WORK = OUT
ds = v5.dates()
info = json.loads(v5.sh([v5.BIN, "info", "--cache", v5.CACHE])); tdte = {d[0]: d[1] for d in info["dates"]}
F = pl.read_csv(f"{OUT}/day_features.csv")
feat = {r["trade_date"]: r for r in F.iter_rows(named=True)}

STRUCTS = {"strangle_otm2": ({"mode": "otm", "n": 2}, {"mode": "otm", "n": 10}), "strangle_otm3": ({"mode": "otm", "n": 3}, {"mode": "otm", "n": 10}),
           "ironfly_w8": ({"mode": "atm"}, {"mode": "otm", "n": 8}), "oi_wall": ({"mode": "max_oi", "n": 10}, {"mode": "otm", "n": 14})}


def cfg(sname, sl):
    s, h = STRUCTS[sname]
    leg = lambda o: {"side": "sell", "opt": o, "strike": s, "sl": {"kind": "pct", "value": sl}}
    return {"kind": "algotest", "name": sname, "entry_time": "09:31", "exit_time": "15:10", "no_reentry_after": "14:30",
            "legs": [leg("CE"), leg("PE"), {"side": "buy", "opt": "CE", "strike": h}, {"side": "buy", "opt": "PE", "strike": h}],
            "trail_to_breakeven": "sl_legs", "overall": {"sl_mtm": 2000}, "sizing": {"mode": "fixed", "multiplier": 1}}


items = [(f"{s}|{sl}", cfg(s, sl), (ds[0], ds[-1])) for s in STRUCTS for sl in (30, 50)]
res = v5.run_batch(items, with_daily=True)
series = {k: {int(d[0]): d[1] for d in r["daily"]} for k, r in res.items()}
train = [d for d in ds if d < 20250101 and d in feat]; test = [d for d in ds if d >= 20250101 and d in feat]


def filters_from(days):
    q = lambda f, p: F.filter(pl.col("trade_date").is_in(days))[f].quantile(p)
    fs = {"none": lambda d: True}
    for p in (0.3, 0.5):
        orq, imq = q("or_pct", p), q("implied_pct", p)
        fs[f"OR<=q{int(p*100)}"] = (lambda th: lambda d: feat[d]["or_pct"] is not None and feat[d]["or_pct"] <= th)(orq)
        fs[f"implied<=q{int(p*100)}"] = (lambda th: lambda d: feat[d]["implied_pct"] <= th)(imq)
        fs[f"OR&implied<=q{int(p*100)}"] = (lambda a, b: lambda d: feat[d]["or_pct"] <= a and feat[d]["implied_pct"] <= b)(orq, imq)
    fs["VIX 13.5-16.5"] = lambda d: feat[d]["vix"] is not None and 13.5 <= feat[d]["vix"] <= 16.5
    fs["OR>=q70 (trend-ish)"] = (lambda th: lambda d: feat[d]["or_pct"] >= th)(q("or_pct", 0.7))
    return fs


rows = []
for scope in ("all days", "non-expiry"):
    for fname, fn in filters_from(train).items():
        for k, s in series.items():
            sel = lambda days: [d for d in days if fn(d) and (scope == "all days" or tdte[d] != 0)]
            a, b = sel(train), sel(test)
            sa, sb = stats([s.get(d, 0.0) for d in a]), stats([s.get(d, 0.0) for d in b])
            rows.append({"scope": scope, "filter": fname, "config": k, "train_n": len(a), "train_net": sa["net"], "train_pf": sa["pf"],
                         "test_n": len(b), "test_net": sb["net"], "test_pf": sb["pf"], "test_dd": sb["dd"]})
df = pl.DataFrame(rows)
# for each scope: pick the best (filter, config) on TRAIN, report its TEST once
picks = []
for scope in ("all days", "non-expiry"):
    sub = df.filter((pl.col("scope") == scope) & (pl.col("train_n") >= 25)).sort("train_net", descending=True)
    best = sub.row(0, named=True)
    picks.append(best)
    print(f"[{scope}] best on 2024: {best['config']} + {best['filter']} -> train ₹{best['train_net']:,.0f} PF {best['train_pf']:.2f} (n {best['train_n']}) | "
          f"TEST 2025-26 ₹{best['test_net']:,.0f} PF {best['test_pf']:.2f} (n {best['test_n']}) DD ₹{best['test_dd']:,.0f}")
    print("   share of (filter,config) pairs profitable on test:", round((sub["test_net"] > 0).mean() * 100), "%; median test net", round(sub["test_net"].median()))
summary = df.group_by("scope", "filter").agg(pl.col("train_net").median().alias("train_median"), pl.col("test_net").median().alias("test_median"),
                                             (pl.col("test_net") > 0).mean().alias("test_share_profitable")).sort("scope", "test_median", descending=[False, True])
print(summary)
json.dump({"picks": picks, "by_filter": summary.rows(named=True), "all": rows}, open(f"{OUT}/sideways_strangles.json", "w"), default=str)
