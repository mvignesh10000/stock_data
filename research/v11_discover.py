#!/usr/bin/env python3
"""v11 strategy discovery on 5 years of NIFTY weekly options (Dhan 2021-11..2024-09 + Breeze 2024 + Upstox 2024-10..2026-11).

Objective (user): max drawdown <= 6 % of Rs 2L (Rs 12k) incl. worst day; maximise smoothness (UPI) and the share of winning
months (target >= 85 %); raw return secondary. Costs at today's rates (STT 0.15 %), slippage 0.5 %/fill + 1 % on stops,
true exchange 1-min OHLC everywhere (pessimistic intrabar stops).

Protocol, chosen to use the never-seen data for testing:
  SELECT on 2024-01-01..2026-03-24 (the period earlier rounds already studied: no new information is spent),
  TEST once on two independent blocks: OLD = 2021-11-15..2023-12-31 (never looked at) and NEW = 2026-03-25..latest (holdout).
Families (an algo trader's menu, both sides of gamma):
  F1 expiry-day short fly (ATM short, premium-picked wings), early or LATE entries (theta-only window)
  F2 expiry-day short strangle by premium with wings, with/without re-entry
  F3 expiry-day ORB long option (buy the breakout side, long gamma), SL + trailing
  F4 expiry-day momentum long (buy CE/PE when premium jumps X % from the 09:20 reference)
  F5 DTE1-2 intraday short straddle with wings (non-expiry theta)
  F6 expiry-day ORB directional credit spread (sell ATM on the breakout side, hedge 4 strikes out)
Regime layer (second step, research/v11_regime.py): day features known by the entry minute (gap, prior-day range,
opening-range width, VIX) applied to the families that survive here.
Selection: per family, keep configs whose selection-period metrics pass the hard DD cap and whose +/-1 grid neighbours are
also positive (plateau); rank by UPI. Report the top configs and the best 2-3 strategy portfolio on both test blocks.
"""
import itertools, json, math, os, statistics, subprocess, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
OUT = os.path.join(ROOT, "results/v11")
CACHE = os.environ.get("V11_CACHE", os.path.join(ROOT, "data/cache/nifty_5y.bin"))
os.makedirs(OUT, exist_ok=True)
CAP = 200000
SEL = (20240101, 20260324)
OLD = (20211115, 20231231)
NEW = (20260325, 20991231)


def leg(side, opt, strike, **k):
    d = {"side": side, "opt": opt, "strike": strike}
    d.update(k)
    return d


def base(name, dte, entry, exit_="15:15", **k):
    c = {"kind": "algotest", "name": name, "entry_time": entry, "exit_time": exit_, "no_reentry_after": "14:45", "dte": dte,
         "underlying": "cash", "legs": [], "square_off": "partial", "sizing": {"mode": "fixed", "multiplier": 1}}
    c.update(k)
    return c


def families():
    out = []  # (family, key tuple, cfg)
    P = lambda v: {"mode": "closest_premium", "value": v}
    for e, sl, wp, osl, tbe in itertools.product(["09:20", "10:30", "12:00", "13:30"], [30, 50, 80], [3, 8], [1500, 3000], ["none", "sl_legs"]):
        c = base("F1_fly", [0], e, trail_to_breakeven=tbe, overall={"sl_mtm": osl})
        c["legs"] = [leg("sell", "CE", {"mode": "atm"}, sl={"kind": "pct", "value": sl}), leg("sell", "PE", {"mode": "atm"}, sl={"kind": "pct", "value": sl}),
                     leg("buy", "CE", P(wp)), leg("buy", "PE", P(wp))]
        out.append(("F1", (e, sl, wp, osl, tbe), c))
    for e, prem, sl, re, osl in itertools.product(["09:20", "11:00", "13:00"], [20, 40], [50, 100], [None, "cost"], [1500, 3000]):
        k = {"sl": {"kind": "pct", "value": sl}}
        if re:
            k["re_sl"] = {"kind": re, "count": 1}
        c = base("F2_strangle", [0], e, overall={"sl_mtm": osl})
        c["legs"] = [leg("sell", "CE", P(prem), **k), leg("sell", "PE", P(prem), **k), leg("buy", "CE", P(2)), leg("buy", "PE", P(2))]
        out.append(("F2", (e, prem, sl, re or "none", osl), c))
    for end, sl, tr in itertools.product(["09:30", "09:45", "10:15"], [20, 30, 40], [(20, 10), (40, 20), (80, 40)]):
        k = {"sl": {"kind": "pct", "value": sl}, "trail": {"kind": "pct", "x": tr[0], "y": tr[1]}}
        c = base("F3_orb_long", [0], "09:16", overall={"sl_mtm": 3000})
        c["legs"] = [leg("buy", "CE", {"mode": "atm"}, orb={"end": end, "side": "high"}, **k), leg("buy", "PE", {"mode": "atm"}, orb={"end": end, "side": "low"}, **k)]
        out.append(("F3", (end, sl, tr), c))
    for mom, sl, tr in itertools.product([20, 40, 60], [20, 30], [(20, 10), (50, 25)]):
        k = {"momentum": {"kind": "pct_up", "value": mom}, "sl": {"kind": "pct", "value": sl}, "trail": {"kind": "pct", "x": tr[0], "y": tr[1]}}
        c = base("F4_mom_long", [0], "09:20", overall={"sl_mtm": 3000})
        c["legs"] = [leg("buy", "CE", {"mode": "atm"}, **k), leg("buy", "PE", {"mode": "atm"}, **k)]
        out.append(("F4", (mom, sl, tr), c))
    for dte, e, sl, osl in itertools.product([[1], [2]], ["09:20", "13:00"], [25, 40], [1500, 3000]):
        c = base("F5_dte_straddle", dte, e, overall={"sl_mtm": osl}, trail_to_breakeven="sl_legs")
        c["legs"] = [leg("sell", "CE", {"mode": "atm"}, sl={"kind": "pct", "value": sl}), leg("sell", "PE", {"mode": "atm"}, sl={"kind": "pct", "value": sl}),
                     leg("buy", "CE", P(5)), leg("buy", "PE", P(5))]
        out.append(("F5", (dte[0], e, sl, osl), c))
    for end, sl in itertools.product(["09:31", "09:46", "10:16"], [30, 40, 60]):
        c = base("F6_orb_spread", [0], "09:16", overall={"sl_mtm": 2000})
        k = {"sl": {"kind": "pct", "value": sl}}
        c["legs"] = [leg("sell", "PE", {"mode": "atm"}, orb={"end": end, "side": "high"}, **k), leg("buy", "PE", {"mode": "otm", "n": 4}, orb={"end": end, "side": "high"}),
                     leg("sell", "CE", {"mode": "atm"}, orb={"end": end, "side": "low"}, **k), leg("buy", "CE", {"mode": "otm", "n": 4}, orb={"end": end, "side": "low"})]
        out.append(("F6", (end, sl), c))
    return out


def run_all(items):
    bf, of = f"{OUT}/batch.jsonl", f"{OUT}/res.json"
    with open(bf, "w") as f:
        for i, (fam, key, c) in enumerate(items):
            f.write(json.dumps({"id": i, "config": {"strategy": c, "gates": {"capital": CAP}}}) + "\n")
    subprocess.run([BIN, "batch-sweep", "--cache", CACHE, "--batch-file", bf, "--out", of, "--with-daily"], check=True, capture_output=True)
    return {r["id"]: r for r in json.load(open(of))["results"] if r["status"] == "SUCCESS"}


def met(series, a, b):
    s = [(d, n) for d, n in series if a <= d <= b]
    if not s:
        return None
    eq = peak = CAP
    dd = sq = 0.0
    months = defaultdict(float)
    for d, n in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        sq += ((peak - eq) / peak * 100) ** 2
        months[d // 100] += n
    ui = math.sqrt(sq / len(s))
    ann = (eq - CAP) / CAP * 100 / (len(s) / 248)
    tr = [n for _, n in s if n != 0]
    gw, gl = sum(x for x in tr if x > 0), -sum(x for x in tr if x < 0)
    mv = [v for v in months.values()]
    return {"net": round(eq - CAP), "ann_pct": round(ann, 2), "dd": round(dd), "ulcer": round(ui, 3), "upi": round(ann / ui, 2) if ui else 0.0,
            "worst_day": round(min(tr)) if tr else 0, "pf": round(gw / gl, 2) if gl else 0.0, "trades": len(tr),
            "win_months_pct": round(sum(v > 0 for v in mv) / len(mv) * 100, 1) if mv else 0.0, "months": len(mv)}


def ok(m):
    return m and m["trades"] >= 20 and m["dd"] <= 0.06 * CAP and m["net"] > 0


def main():
    items = families()
    print("configs", len(items), flush=True)
    res = run_all(items)
    ser = {i: [(int(d[0]), d[1]) for d in r["daily"]] for i, r in res.items()}
    rows = []
    byfam = defaultdict(dict)
    for i, (fam, key, c) in enumerate(items):
        if i not in ser:
            continue
        byfam[fam][key] = i
    for i, (fam, key, c) in enumerate(items):
        if i not in ser:
            continue
        s = met(ser[i], *SEL)
        # plateau: neighbours differ in exactly one key position
        nb = [j for k2, j in byfam[fam].items() if sum(a != b for a, b in zip(k2, key)) == 1]
        nbm = [met(ser[j], *SEL) for j in nb]
        plateau = statistics.median([m["net"] for m in nbm if m]) if nbm else 0
        rows.append({"id": i, "fam": fam, "key": key, "sel": s, "plateau_net_median": plateau,
                     "old": met(ser[i], *OLD), "new": met(ser[i], *NEW)})
    json.dump(rows, open(f"{OUT}/all.json", "w"), default=str)
    print("\nFamily summary on SELECTION period (share of configs with net>0, best UPI):")
    for fam in sorted(byfam):
        fr = [r for r in rows if r["fam"] == fam and r["sel"]]
        pos = sum(r["sel"]["net"] > 0 for r in fr) / max(1, len(fr)) * 100
        bu = max((r["sel"]["upi"] for r in fr), default=0)
        print(f"  {fam}: {len(fr)} configs, {pos:.0f}% profitable, best UPI {bu}")
    chosen = sorted([r for r in rows if ok(r["sel"]) and r["plateau_net_median"] > 0], key=lambda r: -r["sel"]["upi"])
    print("\nSelected (pass DD cap + positive plateau), top 15 by selection UPI; then the two never-used test blocks:")
    for r in chosen[:15]:
        s, o, n = r["sel"], r["old"] or {}, r["new"] or {}
        print(f"  {r['fam']} {r['key']}\n     SEL net {s['net']:>7} pf {s['pf']:.2f} dd {s['dd']:>6} worst {s['worst_day']:>6} winM {s['win_months_pct']:>5}% upi {s['upi']:>5}"
              f" | OLD net {o.get('net', 0):>7} pf {o.get('pf', 0):.2f} dd {o.get('dd', 0):>6} winM {o.get('win_months_pct', 0):>5}%"
              f" | NEW net {n.get('net', 0):>7} pf {n.get('pf', 0):.2f} dd {n.get('dd', 0):>6} winM {n.get('win_months_pct', 0):>5}%")
    json.dump({"chosen": chosen[:30], "protocol": __doc__}, open(f"{OUT}/v11_selected.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
