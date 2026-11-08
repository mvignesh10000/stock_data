#!/usr/bin/env python3
"""v8b — (1) walk-forward where the VIX floor for expiry-day selling is chosen IN-SAMPLE each quarter;
(2) portfolio-level max loss / max profit (AlgoTest broker-level) and delayed entry on the deployed strategy."""
import json, os, sys, copy, subprocess
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5, discover_v6 as v6
import regime_v8 as r8

ROOT = v5.ROOT
v5.WORK = os.path.join(ROOT, "results/v8")
ds = v5.dates()
info = json.loads(v5.sh([v5.BIN, "info", "--cache", v5.CACHE])); tdte = {d[0]: d[1] for d in info["dates"]}
vix = {r[0]: r[5] for r in pl.read_csv(os.path.join(ROOT, "data/india_vix_daily.csv")).rows()}
S, Sp = r8.run_grid(r8.SELL_DIMS, r8.sell_cfg, {}, ds)
folds = [d for q, d in v5.quarter_starts(ds) if d >= 20240701]
FLOORS = [0, 11, 12, 13, 14, 15]
pnl, picks = [], []
for i, f0 in enumerate(folds):
    f1 = folds[i + 1] if i + 1 < len(folds) else 99999999
    train = [d for d in ds if d < f0 and tdte[d] == 0]
    best = (-1e9, None, None)
    for fl in FLOORS:
        days = [d for d in train if vix[d] >= fl]
        k = r8.plateau_pick(S, r8.SELL_DIMS, days)
        if not k:
            continue
        sc = v6.score(v6.win_metrics([(d, S[k].get(d, 0.0)) for d in train if vix[d] >= fl] or [(train[0], 0.0)], train[0], train[-1]))
        if sc > best[0]:
            best = (sc, fl, k)
    _, fl, k = best
    picks.append([f0, fl, Sp[k]["struct"] if k else None, Sp[k]["entry"] if k else None])
    for d in ds:
        if f0 <= d < f1:
            pnl.append((d, S[k].get(d, 0.0) if (k and tdte[d] == 0 and vix[d] >= fl) else 0.0))
st = r8.stats([x for _, x in pnl])
print("WF expiry-day selling with in-sample VIX floor:", {k: round(v) for k, v in st.items()}, "picks", picks)

# (2) joint-engine tests on the deployed v7 strategy
F = json.load(open(os.path.join(ROOT, "results/final_v7/final.json")))
base = copy.deepcopy(F["cfg"]); base["sizing"] = {"mode": "fixed", "multiplier": 1}
def bt(w):
    p = os.path.join(ROOT, "configs/audit/j.json"); json.dump(w, open(p, "w"))
    o = os.path.join(ROOT, "results/v8/j.json")
    subprocess.run([v5.BIN, "backtest", "--cache", v5.CACHE, "--strategy-config", p, "--out", o, "--no-trades"], check=True, capture_output=True)
    return json.load(open(o))["summary_metrics"]
print("deployed strategy alone:", {k: round(bt({'strategy': base})[k]) for k in ("net_pnl_rupees", "max_drawdown_rupees", "worst_day_rupees")})
for sl, tg in ((2500, 0), (0, 4000), (0, 6000), (2500, 6000)):
    m = bt({"portfolio": [base], "portfolio_overall": {"sl_mtm": sl, "tgt_mtm": tg}})
    print(f"portfolio-level SL {sl} / TGT {tg}:", {k: round(m[k]) for k in ("net_pnl_rupees", "max_drawdown_rupees", "worst_day_rupees")})
for et in ("09:20", "09:30", "09:45", "10:00", "10:15"):
    c = copy.deepcopy(base); c["entry_time"] = et
    m = bt({"strategy": c})
    print(f"entry {et}:", {k: round(m[k], 2) for k in ("net_pnl_rupees", "max_drawdown_rupees", "profit_factor")})
