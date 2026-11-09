#!/usr/bin/env python3
"""v12: stress-test the two robust NIFTY expiry-day fly candidates from v11 before calling either deployable.

Candidates (09:20 entry, exit 15:15, sell ATM CE+PE, buy wings by premium, expiry day only, 1 lot = 65):
  A: leg SL 30 %, wings ~Rs 3, overall SL Rs 1,500, no trailing
  B: leg SL 50 %, wings ~Rs 3, overall SL Rs 3,000, trail other leg to breakeven after a stop
Stress set: slippage x2, close-based stops, entry 09:17 / 09:25, wings Rs 2 / Rs 5, leg SL +/-10, overall SL +/-500,
STT already 0.15 %. Then yearly / monthly stats, streaks, and bootstrap (block by month) Monte-Carlo drawdown for
1 and 2 lots on Rs 5L. Writes results/v12/stress.json
"""
import copy, json, math, os, random, subprocess, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
CACHE = os.path.join(ROOT, "data/cache/nifty_5y.bin")
OUT = os.path.join(ROOT, "results/v12")
os.makedirs(OUT, exist_ok=True)
CAP = 500000


def fly(entry="09:20", sl=30, wp=3, osl=1500, tbe="none"):
    P = {"mode": "closest_premium", "value": wp}
    return {"kind": "algotest", "name": "NIFTY_expiry_fly", "entry_time": entry, "exit_time": "15:15", "no_reentry_after": "14:45", "dte": [0],
            "underlying": "cash", "square_off": "partial", "trail_to_breakeven": tbe, "overall": {"sl_mtm": osl}, "sizing": {"mode": "fixed", "multiplier": 1},
            "legs": [{"side": "sell", "opt": "CE", "strike": {"mode": "atm"}, "sl": {"kind": "pct", "value": sl}},
                     {"side": "sell", "opt": "PE", "strike": {"mode": "atm"}, "sl": {"kind": "pct", "value": sl}},
                     {"side": "buy", "opt": "CE", "strike": P}, {"side": "buy", "opt": "PE", "strike": dict(P)}]}


CANDS = {"A": dict(sl=30, wp=3, osl=1500, tbe="none"), "B": dict(sl=50, wp=3, osl=3000, tbe="sl_legs")}


def variants(p):
    v = {"base": (fly(**p), {})}
    v["slippage x2"] = (fly(**p), {"entry_slippage_pct": 1.0, "sl_slippage_pct": 2.0, "min_slippage_pts": 0.2})
    v["close-based stops"] = (fly(**p), {"stop_on_close": True, "catastrophe_mult": 1.5})
    for e in ("09:17", "09:25"):
        v[f"entry {e}"] = (fly(entry=e, **p), {})
    for w in (2, 5):
        v[f"wings Rs {w}"] = (fly(**{**p, "wp": w}), {})
    for d in (-10, 10):
        v[f"leg SL {p['sl'] + d}%"] = (fly(**{**p, "sl": p["sl"] + d}), {})
    for d in (-500, 500):
        v[f"overall SL {p['osl'] + d}"] = (fly(**{**p, "osl": p["osl"] + d}), {})
    return v


def run(items):
    bf, of = f"{OUT}/batch.jsonl", f"{OUT}/res.json"
    with open(bf, "w") as f:
        for i, (cfg, ex) in enumerate(items):
            f.write(json.dumps({"id": i, "config": {"strategy": cfg, "exec": ex, "gates": {"capital": CAP}}}) + "\n")
    subprocess.run([BIN, "batch-sweep", "--cache", CACHE, "--batch-file", bf, "--out", of, "--with-daily"], check=True, capture_output=True)
    return {r["id"]: [(int(d[0]), d[1]) for d in r["daily"]] for r in json.load(open(of))["results"] if r["status"] == "SUCCESS"}


def stats(s, lots=1):
    s = [(d, n * lots) for d, n in s]
    eq = peak = CAP
    dd = 0.0
    m, y = collections.defaultdict(float), collections.defaultdict(float)
    for d, n in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        m[d // 100] += n
        y[d // 10000] += n
    tr = [n for _, n in s if n]
    gw, gl = sum(x for x in tr if x > 0), -sum(x for x in tr if x < 0)
    mv = list(m.values())
    streak = cur = 0
    for v in mv:
        cur = cur + 1 if v <= 0 else 0
        streak = max(streak, cur)
    yrs = len(s) / 248
    return {"net": round(eq - CAP), "per_year": round((eq - CAP) / yrs), "ann_pct_on_5L": round((eq - CAP) / CAP * 100 / yrs, 2),
            "pf": round(gw / gl, 2), "max_dd": round(dd), "max_dd_pct_5L": round(dd / CAP * 100, 2), "worst_day": round(min(tr)),
            "trades": len(tr), "win_rate": round(sum(x > 0 for x in tr) / len(tr) * 100, 1),
            "months": len(mv), "win_months_pct": round(sum(x > 0 for x in mv) / len(mv) * 100, 1), "worst_month": round(min(mv)),
            "max_losing_month_streak": streak, "years": {k: round(v) for k, v in sorted(y.items())}}


def mc_dd(s, lots=1, n=5000, seed=7):
    """Block bootstrap by calendar month over 5 years: distribution of max drawdown."""
    months = collections.defaultdict(list)
    for d, x in s:
        months[d // 100].append(x * lots)
    blocks = list(months.values())
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        eq = peak = dd = 0.0
        for _ in range(len(blocks)):
            for x in rnd.choice(blocks):
                eq += x
                peak = max(peak, eq)
                dd = max(dd, peak - eq)
        out.append(dd)
    out.sort()
    return {"median": round(out[n // 2]), "p95": round(out[int(n * 0.95)]), "p99": round(out[int(n * 0.99)])}


def main():
    items, names = [], []
    for c, p in CANDS.items():
        for vn, (cfg, ex) in variants(p).items():
            items.append((cfg, ex))
            names.append((c, vn))
    ser = run(items)
    res = {}
    for i, (c, vn) in enumerate(names):
        st = stats(ser[i])
        res.setdefault(c, {})[vn] = st
        print(f"{c} {vn:20s} net {st['net']:>7} /yr {st['per_year']:>6} pf {st['pf']:.2f} dd {st['max_dd']:>6} worst {st['worst_day']:>6} "
              f"winM {st['win_months_pct']:>5}% worstM {st['worst_month']:>7} streak {st['max_losing_month_streak']} {st['years']}")
        if vn == "base":
            for lots in (1, 2):
                res[c][f"{lots}lot_on_5L"] = stats(ser[i], lots)
                res[c][f"{lots}lot_mc_dd"] = mc_dd(ser[i], lots)
                print(f"     {lots} lot(s) on Rs 5L: {res[c][f'{lots}lot_on_5L']['ann_pct_on_5L']}%/yr, max DD {res[c][f'{lots}lot_on_5L']['max_dd_pct_5L']}%;"
                      f" bootstrap DD median {res[c][f'{lots}lot_mc_dd']['median']} p95 {res[c][f'{lots}lot_mc_dd']['p95']} p99 {res[c][f'{lots}lot_mc_dd']['p99']}")
    json.dump(res, open(f"{OUT}/stress.json", "w"), indent=1)


if __name__ == "__main__":
    main()
