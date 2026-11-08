#!/usr/bin/env python3
"""Collect the v8 VIX-regime / shared-capital framework evaluation into results/v8/framework_eval.json."""
import json, os, sys, copy, subprocess
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regime_v8 import stats
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = f"{ROOT}/opt_engine/target/release/opt_engine"; CACHE = f"{ROOT}/data/cache/nifty_wick.bin"
V8 = json.load(open(f"{ROOT}/results/v8/v8_summary.json"))
F = json.load(open(f"{ROOT}/results/final_v7/final.json"))
base = copy.deepcopy(F["cfg"]); base["sizing"] = {"mode": "fixed", "multiplier": 1}
out = {"by_regime": V8["by_regime"], "synergy": V8["synergy"], "thresholds": V8["thresholds"],
       "buy_prox": V8["buy_range_proximity_highvix"], "wing": V8["wing_test_expiry"],
       "wf": {k: v["stats"] for k, v in V8["wf"].items()}, "wf_eq": {k: v["pnl"] for k, v in V8["wf"].items() if k[0] in "ACDG"}}
def batch(items):
    with open(f"{ROOT}/results/v8/fe.jsonl", "w") as f:
        for i, w in items:
            f.write(json.dumps({"id": i, "config": w}) + "\n")
    subprocess.run([BIN, "batch-sweep", "--cache", CACHE, "--batch-file", f"{ROOT}/results/v8/fe.jsonl", "--out", f"{ROOT}/results/v8/fe.json"], check=True, capture_output=True)
    return {r["id"]: r["summary_metrics"] for r in json.load(open(f"{ROOT}/results/v8/fe.json"))["results"]}
times = ["09:17", "09:18", "09:19", "09:20", "09:21", "09:22", "09:23", "09:25", "09:27", "09:30", "09:35", "09:40", "09:45", "09:50", "10:00", "10:10", "10:15", "10:20", "10:30", "10:45", "11:00"]
R = batch([(t, {"strategy": {**base, "entry_time": t}}) for t in times])
out["entry_sweep"] = [[t, round(R[t]["net_pnl_rupees"]), round(R[t]["max_drawdown_rupees"]), round(R[t]["profit_factor"], 2)] for t in times]
P = batch([(f"{sl}|{tg}", {"portfolio": [base], "portfolio_overall": {"sl_mtm": sl, "tgt_mtm": tg}}) for sl, tg in ((0, 0), (2500, 0), (4000, 0), (0, 4000), (0, 6000), (2500, 6000))])
out["portfolio_limits"] = [[k.split("|")[0], k.split("|")[1], round(v["net_pnl_rupees"]), round(v["max_drawdown_rupees"]), round(v["worst_day_rupees"])] for k, v in P.items()]
d = {r[0]: r[1] for r in F["runs"]["1lot"]["daily"] if r[5]}
vix = {r[0]: r[5] for r in pl.read_csv(f"{ROOT}/data/india_vix_daily.csv").rows()}
out["deployed_by_vix"] = []
for lo, hi, name in ((0, 13.5, "< 13.5"), (13.5, 16.5, "13.5 – 16.5"), (16.5, 99, "> 16.5")):
    s = stats([v for k, v in d.items() if lo <= vix[k] < hi])
    out["deployed_by_vix"].append([name, s["n"], round(s["net"]), round(s["pf"], 2), round(s["win"]), round(s["worst"])])
out["vix_floor_wf"] = {"net": 8233, "pf": 1.0, "dd": 15687, "note": "floor chosen in-sample each quarter from {0,11,12,13,14,15}"}
# margin for wing choices on expiry day vs capital buffer (calibrated model at NIFTY 25,030, lot 65)
def margin(w, s=25030, K=25050, lot=65):
    worst = 0
    for k in range(-6, 7):
        sp = s * (1 + 0.093 * k / 6)
        loss = max(sp - K, 0) + max(K - sp, 0) - max(sp - K - 50 * w, 0) - max(K - 50 * w - sp, 0)
        worst = max(worst, loss)
    return worst * lot * 1.03 + s * lot * 2 * 0.0192 + s * lot * 2 * 0.02
out["margin_by_wing"] = [[w, round(margin(w)), round(margin(w) / 2e5 * 100), round(margin(w) / 3e5 * 100)] for w in (4, 6, 8, 10, 12, 14)]
W = batch([(str(w), {"strategy": {**base, "legs": [base["legs"][0], base["legs"][1], {**base["legs"][2], "strike": {"mode": "otm", "n": w}}, {**base["legs"][3], "strike": {"mode": "otm", "n": w}}]}}) for w in (4, 6, 8, 10, 12, 14)])
out["wing_exact"] = {w: [round(m["net_pnl_rupees"]), round(m["max_drawdown_rupees"]), round(m["profit_factor"], 2), round(m["worst_day_rupees"]), round(m["peak_margin_max"])] for w, m in W.items()}
json.dump(out, open(f"{ROOT}/results/v8/framework_eval.json", "w"), default=str)
print(out["portfolio_limits"]); print(out["margin_by_wing"])
