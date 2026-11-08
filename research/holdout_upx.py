#!/usr/bin/env python3
"""One-shot holdout + data-validation of the frozen strategies on Upstox TRUE exchange 1-min OHLC.

A. Overlap period (both datasets present, <= 2026-03-24): same strategy on the old cache (LTP + synthetic wicks)
   vs the Upstox true-OHLC cache -> how biased was the research data?
B. Untouched holdout 2026-03-25 .. latest: frozen configs, no re-tuning. Costs at today's rates (STT 0.15%).
Writes results/upx/holdout.json
"""
import json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
WICK = os.path.join(ROOT, "data/cache/nifty_wick.bin")
UPX = os.path.join(ROOT, "data/cache/nifty_upx.bin")
OUT = os.path.join(ROOT, "results/upx")
os.makedirs(OUT + "/runs", exist_ok=True)
A = lambda f: json.load(open(os.path.join(ROOT, "configs/audit", f)))

CFGS = {"fly400": A("fly400.json"), "fly600": A("fly600.json"), "orb_spread": A("spread.json"),
        "fly400+spread": {"portfolio": [A("fly400.json")["strategy"], A("spread.json")["strategy"]]}}


def build():
    if "--rebuild" in sys.argv or not os.path.exists(UPX):
        subprocess.run([BIN, "build-cache", "--parquet-dir", f"{ROOT}/data/parquet/NIFTY_UPX", "--out", UPX, "--rank", "0", "--step", "50"], check=True)


def bt(cfg, tag, cache, frm, to):
    p, o = f"{OUT}/runs/{tag}.cfg.json", f"{OUT}/runs/{tag}.json"
    c = dict(cfg)
    c.setdefault("gates", {"capital": 200000})
    json.dump(c, open(p, "w"))
    subprocess.run([BIN, "backtest", "--cache", cache, "--strategy-config", p, "--date-from", str(frm), "--date-to", str(to), "--out", o], check=True, capture_output=True)
    return json.load(open(o))


def summ(r):
    m = r["summary_metrics"]
    act = [d for d in r["daily"] if d.get("active") or d.get("traded")]
    return {"days": len(act), "net": round(m["net_pnl_rupees"]), "pf": round(m["profit_factor"], 2), "dd": round(m["max_drawdown_rupees"]),
            "worst_day": round(m["worst_day_rupees"]), "win_months_pct": round(m["profitable_months_pct"], 1), "months": m["months"],
            "win_rate": round(m["win_rate_pct"], 1), "monthly": r.get("monthly_pnl")}


def main():
    build()
    info = subprocess.run([BIN, "info", "--cache", UPX], capture_output=True, text=True).stdout
    print(info.strip()[:400])
    res = {"cache_info": info, "overlap": {}, "holdout": {}}
    first = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 20241001
    for k, c in CFGS.items():
        a = summ(bt(c, f"{k}_ovl_wick", WICK, first, 20260324))
        b = summ(bt(c, f"{k}_ovl_upx", UPX, first, 20260324))
        h = summ(bt(c, f"{k}_holdout", UPX, 20260325, 20991231))
        res["overlap"][k] = {"wick_ltp": a, "upx_true": b}
        res["holdout"][k] = h
        print(f"{k:14s} overlap wick ₹{a['net']:>8,} PF {a['pf']:.2f} ({a['days']}d) | true ₹{b['net']:>8,} PF {b['pf']:.2f} ({b['days']}d) "
              f"|| HOLDOUT ₹{h['net']:>8,} PF {h['pf']:.2f} DD ₹{h['dd']:,} worst ₹{h['worst_day']:,} winM {h['win_months_pct']}% ({h['days']}d)")
    json.dump(res, open(f"{OUT}/holdout.json", "w"), indent=1)


if __name__ == "__main__":
    main()
