#!/usr/bin/env python3
"""Final evaluation of the deployable strategy (expiry-day iron fly from v7-H1) + audit + stress tests.
Writes results/final_v7/final.json used by research/report_v7.py."""
import copy, json, math, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import monte_carlo_dd, deflated_sharpe, moments
from algotest_sheet import sheet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
WICK, NOWICK = os.path.join(ROOT, "data/cache/nifty_wick.bin"), os.path.join(ROOT, "data/cache/nifty.bin")
OUT = os.path.join(ROOT, "results/final_v7"); CFG = os.path.join(ROOT, "configs/final_v7")
os.makedirs(OUT, exist_ok=True); os.makedirs(CFG, exist_ok=True)
V6 = json.load(open(os.path.join(ROOT, "results/v6/v6_summary.json")))
V7 = json.load(open(os.path.join(ROOT, "results/v7/v7_summary.json")))
SLIP2 = {"entry_slippage_pct": 1.0, "sl_slippage_pct": 2.0, "min_slippage_pts": 0.20}
FEE_PER_MONTH = 100.0  # AlgoTest live execution: 100 credits (~Rs83-100) per strategy per 28 days


def bt(w, tag, cache=WICK, frm=0, to=99999999):
    p = f"{CFG}/{tag}.json"; json.dump(w, open(p, "w"), indent=1)
    o = f"{OUT}/{tag}.json"
    subprocess.run([BIN, "backtest", "--cache", cache, "--strategy-config", p, "--date-from", str(frm), "--date-to", str(to), "--out", o], check=True, capture_output=True)
    return json.load(open(o))


def main():
    h1 = next(r for r in V7["runs"] if r["tag"] == "H1")
    cfg = copy.deepcopy(h1["final_cfg"]); cfg["name"] = "NIFTY_ExpiryDay_IronFly"
    res = {"cfg": cfg, "sheets": {}, "runs": {}}
    # 1 lot (fixed) + margin-sized for 2L / 3L
    variants = {"1lot": {**cfg, "sizing": {"mode": "fixed", "multiplier": 1}}}
    for lab, cap in (("2L", 200000), ("3L", 300000)):
        variants[lab] = {**cfg, "sizing": {"mode": "margin", "capital": cap, "util": 0.9, "max_multiplier": 6}}
    for lab, c in variants.items():
        cap = 200000 if lab != "3L" else 300000
        r = bt({"strategy": c, "gates": {"capital": cap}}, f"{lab}_base")
        nw = bt({"strategy": c, "gates": {"capital": cap}}, f"{lab}_nowick", cache=NOWICK)
        s2 = bt({"strategy": c, "gates": {"capital": cap}, "exec": SLIP2}, f"{lab}_slip2")
        pnl = [d["net"] for d in r["daily"]]
        months = len(r["monthly_pnl"])
        res["runs"][lab] = {"metrics": r["summary_metrics"], "nowick": nw["summary_metrics"], "slip2": s2["summary_metrics"],
                            "mc95": monte_carlo_dd(pnl, pct=95), "mc99": monte_carlo_dd(pnl, pct=99), "fee": FEE_PER_MONTH * months,
                            "monthly": r["monthly_pnl"], "quarterly": r["quarterly_pnl"], "yearly": r["yearly_pnl"],
                            "daily": [[d["date"], d["net"], d["tdte"], d["margin"], d["lots"], d["traded"], d["exit"], d["exit_time"]] for d in r["daily"]],
                            "worst": sorted([d for d in r["daily"] if d["traded"]], key=lambda d: d["net"])[:5],
                            "dd_episodes": r["worst_drawdown_episodes"],
                            "trades_worst": [t for t in r["trades"] if t["trade_date"] in {d["date"] for d in sorted([d for d in r["daily"] if d["traded"]], key=lambda d: d["net"])[:5]}]}
        mlt = sorted({d["lots"] for d in r["daily"] if d["traded"]})
        print(lab, f"net {r['summary_metrics']['net_pnl_rupees']:,.0f} DD {r['summary_metrics']['max_drawdown_rupees']:,.0f} PF {r['summary_metrics']['profit_factor']:.2f} "
              f"| nowick {nw['summary_metrics']['net_pnl_rupees']:,.0f} slip2 {s2['summary_metrics']['net_pnl_rupees']:,.0f} | MC95 {res['runs'][lab]['mc95']:,.0f} | short-lots used {mlt} | peak margin {r['summary_metrics']['peak_margin_max']:,.0f}")
    # walk-forward (procedure-level, 1 lot): v6 (clean) and v7-H1 (search region informed by v6)
    res["wf_v6"] = V6["buckets"]["tdte0"]["wf_oos"]; res["wf_v6_metrics"] = V6["buckets"]["tdte0"]["wf_metrics"]
    res["wf_v7"] = h1["wf_oos"]; res["wf_v7_metrics"] = h1["wf_metrics"]; res["wf_v7_picks"] = h1["wf_picks"]
    res["wf_other_dte"] = {b: V6["buckets"][b]["wf_metrics"] for b in ("tdte1", "tdte2", "tdte3", "tdte4")}
    res["wf_h2"] = {r["bucket"]: r["wf_metrics"] for r in V7["runs"] if r["tag"] == "H2"}
    # deflated Sharpe at several trial counts
    x = [d[1] for d in res["runs"]["1lot"]["daily"]]
    var_sr = V6["var_sr"]
    res["dsr"] = {str(n): deflated_sharpe(x, n, var_sr)[0] for n in (100, 1000, 6000, 50000)}
    m, sd, sk, ku = moments(x); res["sharpe_ann"] = m / sd * math.sqrt(252)
    wf = [v for _, v in res["wf_v6"]]; m2, sd2, _, _ = moments(wf); res["wf_sharpe_ann"] = m2 / sd2 * math.sqrt(252)
    # forced on every day (what the DTE filter avoids) incl. 4-Jun-2024
    f = copy.deepcopy(variants["1lot"]); f["dte"] = []
    rf = bt({"strategy": f, "gates": {"capital": 200000}}, "forced_all_days")
    res["forced"] = {"metrics": rf["summary_metrics"], "tdte": rf["dte_breakdown"], "by_date": {str(d["date"]): [d["net"], d["tdte"]] for d in rf["daily"]}}
    # shock days
    import polars as pl
    sp = pl.concat([pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY_OHLC/*/*.parquet"), pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY/*/*.parquet")]) \
        .filter(pl.col("expiry_rank") == 0).select("trade_date", "minute_idx", "spot_open", "spot_high", "spot_low", "spot_close").unique(["trade_date", "minute_idx"]) \
        .group_by("trade_date").agg(pl.col("spot_open").sort_by("minute_idx").first().alias("o"), pl.col("spot_high").max().alias("h"),
                                    pl.col("spot_low").min().alias("l"), pl.col("spot_close").sort_by("minute_idx").last().alias("c")).collect()
    sp = sp.with_columns(((pl.col("h") - pl.col("l")) / pl.col("o") * 100).alias("rng"), ((pl.col("c") - pl.col("o")) / pl.col("o") * 100).alias("oc"))
    res["shock_days"] = [[int(d), round(r_, 2), round(o_, 2)] for d, r_, o_ in sp.sort("rng", descending=True).head(12).select("trade_date", "rng", "oc").rows()]
    bd = {str(d["date"]): d for d in res["runs"]["1lot"]["daily"] and [dict(zip(["date", "net", "tdte", "margin", "lots", "traded", "exit", "exit_time"], row)) for row in res["runs"]["1lot"]["daily"]]}
    res["shock_table"] = [[d, r_, o_, res["forced"]["by_date"].get(str(d), [None, None])[1], (bd.get(str(d)) or {}).get("net") if (bd.get(str(d)) or {}).get("traded") else None,
                           res["forced"]["by_date"].get(str(d), [None])[0]] for d, r_, o_ in res["shock_days"]]
    # AlgoTest sheets with multipliers
    ml2 = max([d[4] for d in res["runs"]["2L"]["daily"] if d[5] and d[0] >= 20241120] or [0]) // 2
    ml3 = max([d[4] for d in res["runs"]["3L"]["daily"] if d[5] and d[0] >= 20241120] or [0]) // 2
    res["multipliers_now"] = {"2L": ml2, "3L": ml3}
    res["sheet"] = sheet(cfg, ml2, ml3)
    # current-day margin estimate at today's spot (Nifty 25,030) via the calibrated model
    json.dump(res, open(f"{OUT}/final.json", "w"))
    print("DSR", {k: round(v, 3) for k, v in res["dsr"].items()}, "sharpe", round(res["sharpe_ann"], 2), "wf sharpe", round(res["wf_sharpe_ann"], 2), "mults", res["multipliers_now"])
    print("forced all days tdte breakdown", {k: round(v["net_rupees"]) for k, v in res["forced"]["tdte"].items()})
    for row in res["shock_table"]:
        print(row)


if __name__ == "__main__":
    main()
