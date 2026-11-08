#!/usr/bin/env python3
"""Grade the v5 per-DTE winners with the pre-registered rules, build the portfolio, stress-test it,
size it for Rs2L / Rs3L with the SPAN-calibrated margin model and write results/v5/final_v5.json."""
import copy, json, math, os, subprocess, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import monte_carlo_dd, deflated_sharpe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
WICK = os.path.join(ROOT, "data/cache/nifty_wick.bin")
NOWICK = os.path.join(ROOT, "data/cache/nifty.bin")
V5 = os.path.join(ROOT, "results/v5")
CFG = os.path.join(ROOT, "configs/v5")
os.makedirs(CFG, exist_ok=True)
S = json.load(open(f"{V5}/v5_summary.json"))
PLATFORM_FEE_PER_STRATEGY_MONTH = 100.0  # AlgoTest live: 100 credits (~Rs83-100) per strategy per 28 days
SLIP2 = {"entry_slippage_pct": 1.0, "sl_slippage_pct": 2.0, "min_slippage_pts": 0.20}


def bt(wrapper, tag, cache=WICK, frm=0, to=99999999):
    p = f"{CFG}/{tag}.json"
    json.dump(wrapper, open(p, "w"), indent=1)
    o = f"{V5}/{tag}.json"
    subprocess.run([BIN, "backtest", "--cache", cache, "--strategy-config", p, "--date-from", str(frm), "--date-to", str(to), "--out", o], check=True, capture_output=True)
    return json.load(open(o))


def sized(cfg, capital, util=0.9, max_mult=6):
    c = copy.deepcopy(cfg)
    c["sizing"] = {"mode": "margin", "capital": capital, "util": util, "max_multiplier": max_mult}
    return c


def daily_net(r):
    return [d["net"] for d in r["daily"]]


def wf_stats(rows):
    pnl = [x for _, x in rows]
    w = sum(x for x in pnl if x > 0)
    l = -sum(x for x in pnl if x < 0)
    return {"net": sum(pnl), "pf": (w / l) if l > 0 else 99.0, "days": sum(1 for x in pnl if x != 0)}


def main():
    var_sr, n_trials = S["var_sr"], S["n_trials"]
    grades, chosen = {}, {}
    for b, cands in S["final"].items():
        c = cands[0]
        r = bt({"strategy": c["cfg"], "gates": {"capital": 200000}}, f"{b}_1lot")
        x = daily_net(r)
        dsr, sr0 = deflated_sharpe(x, n_trials, var_sr)
        wf = wf_stats(S["wf_oos"].get(b, []))
        rules = {
            "hard_gate_full_sample": c["metrics"]["gate_passed"],
            "stability>=0.75": c["stability"] >= 0.75,
            "walk_forward_OOS_profitable_PF>=1.2": wf["net"] > 0 and wf["pf"] >= 1.2,
            "deflated_sharpe>=0.90": dsr >= 0.90,
        }
        grades[b] = {"rules": rules, "deployable": all(rules.values()), "dsr": dsr, "sr0_daily": sr0, "wf": wf,
                     "gate_failures": c["metrics"]["gate_failures"], "stability": c["stability"], "params": c["params"], "cfg": c["cfg"]}
        print(b, c["params"]["fam"], "deployable" if grades[b]["deployable"] else "REJECT", {k: v for k, v in rules.items()}, f"DSR {dsr:.3f} WF net {wf['net']:,.0f} PF {wf['pf']:.2f}")
        if grades[b]["deployable"]:
            chosen[b] = c["cfg"]
    # fall back: if fewer than 2 deployable, also evaluate the best 'near-miss' set separately (clearly labelled)
    near = {b: g["cfg"] for b, g in grades.items() if not g["deployable"] and g["rules"]["stability>=0.75"] and g["wf"]["net"] > 0}
    out = {"grades": grades, "chosen": list(chosen), "near_miss": list(near), "n_trials": n_trials, "var_sr": var_sr, "portfolios": {}}
    sets = {"DEPLOY": chosen}
    if near:
        sets["DEPLOY+NEAR"] = {**chosen, **near}
    for name, comp in sets.items():
        if not comp:
            continue
        cfgs = [comp[b] for b in sorted(comp)]
        P = {}
        for cap_label, cap in [("2L", 200000), ("3L", 300000)]:
            port = {"portfolio": [sized(c, cap) for c in cfgs], "gates": {"capital": cap}}
            base = bt(port, f"{name}_{cap_label}_base")
            nowick = bt(port, f"{name}_{cap_label}_nowick", cache=NOWICK)
            slip2 = bt({**port, "exec": SLIP2}, f"{name}_{cap_label}_slip2")
            pnl = daily_net(base)
            months = len(base["monthly_pnl"])
            fee = PLATFORM_FEE_PER_STRATEGY_MONTH * len(cfgs) * months
            P[cap_label] = {
                "base": base["summary_metrics"], "nowick": nowick["summary_metrics"], "slip2": slip2["summary_metrics"],
                "mc_dd95": monte_carlo_dd(pnl, pct=95), "mc_dd99": monte_carlo_dd(pnl, pct=99),
                "platform_fee_total": fee, "monthly": base["monthly_pnl"], "quarterly": base["quarterly_pnl"], "yearly": base["yearly_pnl"],
                "daily": [[d["date"], d["net"], d["tdte"], d["margin"], d["lots"], d["traded"], d["exit"]] for d in base["daily"]],
                "worst_days": sorted([d for d in base["daily"] if d["traded"]], key=lambda d: d["net"])[:5],
                "dd_episodes": base["worst_drawdown_episodes"],
            }
            print(name, cap_label, f"net {base['summary_metrics']['net_pnl_rupees']:,.0f} DD {base['summary_metrics']['max_drawdown_rupees']:,.0f} "
                  f"| nowick {nowick['summary_metrics']['net_pnl_rupees']:,.0f} | slip2 {slip2['summary_metrics']['net_pnl_rupees']:,.0f} | MC95 {P[cap_label]['mc_dd95']:,.0f}")
        # walk-forward OOS of the same buckets (procedure-level honest estimate, 1 lot)
        wfp = defaultdict(float)
        for b in comp:
            for d, x in S["wf_oos"].get(b, []):
                wfp[int(d)] += x
        P["walk_forward_1lot"] = sorted(wfp.items())
        # forced-all-days tail test + shock days per component (1 lot)
        P["forced_all_days"] = {}
        for b, c in comp.items():
            f = copy.deepcopy(c)
            f["dte"] = []
            r = bt({"strategy": f, "gates": {"capital": 200000}}, f"{name}_{b}_forced")
            dd = sorted(r["daily"], key=lambda d: d["net"])[:5]
            P["forced_all_days"][b] = {"metrics": r["summary_metrics"], "worst": [[d["date"], d["tdte"], d["net"], d["exit"]] for d in dd],
                                       "by_date": {d["date"]: d["net"] for d in r["daily"]}}
        out["portfolios"][name] = P
    # shock days = largest intraday spot ranges in the sample (from the Parquet lake)
    import polars as pl
    sp = pl.concat([pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY_OHLC/*/*.parquet"), pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY/*/*.parquet")]) \
        .group_by("trade_date", "minute_idx").agg(pl.col("spot_open").first(), pl.col("spot_high").first(), pl.col("spot_low").first(), pl.col("spot_close").first()) \
        .group_by("trade_date").agg(pl.col("spot_open").sort_by("minute_idx").first().alias("o"), pl.col("spot_high").max().alias("h"),
                                    pl.col("spot_low").min().alias("l"), pl.col("spot_close").sort_by("minute_idx").last().alias("c")).collect()
    sp = sp.unique("trade_date").with_columns(((pl.col("h") - pl.col("l")) / pl.col("o") * 100).alias("range_pct"), ((pl.col("c") - pl.col("o")) / pl.col("o") * 100).alias("oc_pct"))
    out["shock_days"] = sp.sort("range_pct", descending=True).head(12).select("trade_date", "range_pct", "oc_pct").rows()
    json.dump(out, open(f"{V5}/final_v5.json", "w"), indent=1)
    print("wrote", f"{V5}/final_v5.json")


if __name__ == "__main__":
    main()
