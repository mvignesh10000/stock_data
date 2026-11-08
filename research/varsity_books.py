#!/usr/bin/env python3
"""Zerodha-Varsity structures and the other trader's 'selling books', each with ONE pre-declared setting
(no tuning), 1 lot, realistic engine. Reported on expiry days (trading DTE 0) and non-expiry days, with
2024 (build) vs 2025-26 (check) split. Calendars are skipped: the cache holds one expiry per day."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5
from regime_v8 import stats

ROOT = v5.ROOT; OUT = os.path.join(ROOT, "results/audit_v9"); v5.WORK = OUT
ds = v5.dates(); info = json.loads(v5.sh([v5.BIN, "info", "--cache", v5.CACHE])); tdte = {d[0]: d[1] for d in info["dates"]}


def L(side, opt, mode, n=0, lots=1, sl=None, orb=None, value=0):
    l = {"side": side, "opt": opt, "lots": lots, "strike": {"mode": mode, "n": n, "value": value}}
    if sl:
        l["sl"] = {"kind": "pct", "value": sl}
    if orb:
        l["orb"] = {"end": "09:31", "side": orb}
    return l


def S(name, legs, entry="09:20", exit_="15:15", osl=2000, tbe="sl_legs", extra=None):
    c = {"kind": "algotest", "name": name, "entry_time": entry, "exit_time": exit_, "no_reentry_after": "14:30", "legs": legs,
         "trail_to_breakeven": tbe, "overall": ({"sl_mtm": osl} if osl else {}), "sizing": {"mode": "fixed", "multiplier": 1}}
    if extra:
        c.update(extra)
    return c


BOOKS = {
    # --- Varsity structures
    "Iron condor (sell OTM2, buy OTM6), 09:20": S("ic", [L("sell", "CE", "otm", 2, sl=50), L("sell", "PE", "otm", 2, sl=50), L("buy", "CE", "otm", 6), L("buy", "PE", "otm", 6)]),
    "Long call butterfly ATM±2 (debit), 09:20": S("fly", [L("buy", "CE", "itm", 2), L("sell", "CE", "atm", lots=2), L("buy", "CE", "otm", 2)], osl=0, tbe="none"),
    "Batman: call fly OTM1/3/5 + put fly OTM1/3/5 (debit)": S("batman", [L("buy", "CE", "otm", 1), L("sell", "CE", "otm", 3, lots=2), L("buy", "CE", "otm", 5),
                                                                         L("buy", "PE", "otm", 1), L("sell", "PE", "otm", 3, lots=2), L("buy", "PE", "otm", 5)], osl=0, tbe="none"),
    "Call+put ratio 1x2 (buy ATM, sell 2×OTM3) + OTM10 wings": S("ratio", [L("buy", "CE", "atm"), L("sell", "CE", "otm", 3, lots=2, sl=60), L("buy", "CE", "otm", 10),
                                                                          L("buy", "PE", "atm"), L("sell", "PE", "otm", 3, lots=2, sl=60), L("buy", "PE", "otm", 10)]),
    "Directional hedged spreads on 15-min ORB (bull put / bear call)": S("dirspread", [L("sell", "PE", "atm", sl=40, orb="high"), L("buy", "PE", "otm", 4, orb="high"),
                                                                                      L("sell", "CE", "atm", sl=40, orb="low"), L("buy", "CE", "otm", 4, orb="low")], entry="09:16", tbe="none"),
    # --- the other trader's selling books (our replication of their names)
    "straddle_920 (naked ATM, 25% leg SL)": S("s920", [L("sell", "CE", "atm", sl=25), L("sell", "PE", "atm", sl=25)], osl=0, tbe="none"),
    "straddle_1015 (naked ATM, 25% leg SL)": S("s1015", [L("sell", "CE", "atm", sl=25), L("sell", "PE", "atm", sl=25)], entry="10:15", osl=0, tbe="none"),
    "iron_fly_1200 (ATM + OTM4 wings)": S("if1200", [L("sell", "CE", "atm", sl=40), L("sell", "PE", "atm", sl=40), L("buy", "CE", "otm", 4), L("buy", "PE", "otm", 4)], entry="12:00"),
    "iron_fly_1430 (ATM + OTM4 wings)": S("if1430", [L("sell", "CE", "atm", sl=40), L("sell", "PE", "atm", sl=40), L("buy", "CE", "otm", 4), L("buy", "PE", "otm", 4)], entry="14:30"),
    # --- reference: our deployed strategy
    "OURS: expiry iron fly ATM + OTM12, 09:20": None,
}
F = json.load(open(os.path.join(ROOT, "results/final_v7/final.json")))
BOOKS["OURS: expiry iron fly ATM + OTM12, 09:20"] = {**F["cfg"], "dte": [], "sizing": {"mode": "fixed", "multiplier": 1}}
res = v5.run_batch([(k, c, (ds[0], ds[-1])) for k, c in BOOKS.items()], with_daily=True)
rows = []
for k in BOOKS:
    r = res[k]; ser = {int(d[0]): (d[1], d[5]) for d in r["daily"]}
    row = {"book": k}
    for scope, f in (("expiry", lambda d: tdte[d] == 0), ("non-expiry", lambda d: tdte[d] != 0)):
        a = stats([ser[d][0] for d in ds if f(d) and d < 20250101]); b = stats([ser[d][0] for d in ds if f(d) and d >= 20250101])
        al = stats([ser[d][0] for d in ds if f(d)])
        row[scope] = {"net": al["net"], "pf": al["pf"], "dd": al["dd"], "win": al["win"], "worst": al["worst"], "n": al["n"],
                      "net_2024": a["net"], "pf_2024": a["pf"], "net_2025_26": b["net"], "pf_2025_26": b["pf"],
                      "peak_margin": max((ser[d][1] for d in ds if f(d)), default=0)}
    rows.append(row)
    e, n = row["expiry"], row["non-expiry"]
    print(f"{k[:62]:62s} | EXP net {e['net']:>8,.0f} PF {e['pf']:.2f} (24 {e['net_2024']:>7,.0f} / 25-26 {e['net_2025_26']:>7,.0f}) "
          f"| NON-EXP net {n['net']:>9,.0f} PF {n['pf']:.2f} (24 {n['net_2024']:>8,.0f} / 25-26 {n['net_2025_26']:>8,.0f}) | margin≤₹{max(e['peak_margin'], n['peak_margin']):,.0f}")
json.dump(rows, open(f"{OUT}/varsity_books.json", "w"), indent=1)
