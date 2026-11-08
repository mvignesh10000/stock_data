#!/usr/bin/env python3
"""Compounding with sizing appropriate to each book: selling books by margin (25% cash buffer),
buying books by risk (2.5% of equity per trade at the -30% premium stop). Lots re-computed daily from equity."""
import json, math, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compounding import run, BROK_PER_ORDER
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = json.load(open(f"{ROOT}/results/final_v7/final.json")); base = {**F["cfg"], "sizing": {"mode": "fixed", "multiplier": 1}}
w8 = json.loads(json.dumps(base)); w8["legs"][2]["strike"]["n"] = 8; w8["legs"][3]["strike"]["n"] = 8
fly600 = {r[0]: r for r in run(base, "fly600")}; fly400 = {r[0]: r for r in run(w8, "fly400")}
spr = {r[0]: (r[0], r[1], 77000.0, r[3], r[4]) for r in run(json.load(open(f"{ROOT}/configs/audit/spread.json"))["strategy"], "spread_c")}
G = json.load(open(f"{ROOT}/results/audit_v9/gap_williams.json"))["stress (+0.2%/side)"]["trades"]
gng = {t["date"]: (t["date"], t["net"], t["entry"] * 65, 2, True) for t in G if t["type"] == "gap_and_go"}
days = sorted(fly600)


def sim(books, cap, util=0.75, risk_pct=2.5):
    eq = cap; peak = cap; dd = 0.0; low = cap; rets = []; yrs = {}; q = {}
    eq1 = cap; pk1 = cap; dd1 = 0.0; dd1rs = 0.0; maxl = 0
    for d in days:
        start = eq; free = eq * util; day1 = 0.0
        for kind, b in books:
            r = b.get(d)
            if not r or not r[4]:
                continue
            pnl1, m1, orders = r[1], r[2], r[3]
            day1 += pnl1
            if kind == "sell":
                lots = int(free // m1) if m1 > 0 else 0
                free -= lots * m1
            else:  # buy, risk-based
                risk1 = 0.30 * m1
                lots = int(eq * risk_pct / 100 // risk1) if risk1 > 0 else 0
                lots = min(lots, int(free // m1)); free -= lots * m1
            if lots >= 1:
                brok = orders * BROK_PER_ORDER
                eq += lots * (pnl1 + brok) - brok
                maxl = max(maxl, lots)
        eq1 += day1; pk1 = max(pk1, eq1); dd1 = max(dd1, (pk1 - eq1) / pk1); dd1rs = max(dd1rs, pk1 - eq1)
        rets.append(eq / start - 1); peak = max(peak, eq); dd = max(dd, (peak - eq) / peak); low = min(low, eq)
        y = str(d // 10000); yrs.setdefault(y, [start, eq]); yrs[y][1] = eq
        qq = f"{y}Q{((d // 100) % 100 - 1) // 3 + 1}"; q[qq] = q.get(qq, 0) + day1
    yrsN = len(days) / 252
    m = sum(rets) / len(rets); sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1)); dn = math.sqrt(sum(min(r, 0) ** 2 for r in rets) / len(rets))
    cg = (eq / cap) ** (1 / yrsN) - 1; cg1 = (eq1 / cap) ** (1 / yrsN) - 1
    return {"rs_per_year_1lot": (eq1 - cap) / yrsN, "simple_return_pct": (eq1 - cap) / yrsN / cap * 100, "cagr_1lot_pct": cg1 * 100, "cagr_comp_pct": cg * 100,
            "maxdd_comp_pct": dd * 100, "maxdd_1lot_pct": dd1 * 100, "maxdd_1lot_rs": dd1rs, "lowest_equity": low, "worst_year_pct": min(v[1] / v[0] - 1 for v in yrs.values()) * 100,
            "sharpe": m / sd * math.sqrt(252) if sd else 0, "sortino": m / dn * math.sqrt(252) if dn else 0, "calmar_comp": cg / dd if dd else 0,
            "quarters_pos": f"{sum(1 for v in q.values() if v > 0)}/{len(q)}", "final_equity": eq, "max_lots": maxl}


books = {
    "Expiry iron fly ±400 · ₹2L": ([("sell", fly400)], 2e5),
    "Expiry iron fly ±600 · ₹3L": ([("sell", fly600)], 3e5),
    "Gap-and-Go only (buy ITM-150, +0.2% stress) · ₹1L": ([("buy", gng)], 1e5),
    "Fly ±400 + ORB hedged spread (both expiry) · ₹3L": ([("sell", fly400), ("sell", spr)], 3e5),
    "Fly ±600 + Gap-and-Go · ₹3L": ([("sell", fly600), ("buy", gng)], 3e5),
    "Fly ±400 + ORB spread + Gap-and-Go · ₹3L": ([("sell", fly400), ("sell", spr), ("buy", gng)], 3e5),
}
out = {}
for name, (bk, cap) in books.items():
    m = sim(bk, cap); out[name] = m
    print(f"{name:52s} ₹/yr {m['rs_per_year_1lot']:>8,.0f} simple {m['simple_return_pct']:5.1f}% CAGR1 {m['cagr_1lot_pct']:5.1f}% CAGRc {m['cagr_comp_pct']:5.1f}% DDc {m['maxdd_comp_pct']:4.1f}% "
          f"DD1 {m['maxdd_1lot_pct']:4.1f}% (₹{m['maxdd_1lot_rs']:,.0f}) worstY {m['worst_year_pct']:5.1f}% Sh {m['sharpe']:.2f} So {m['sortino']:.2f} Cal {m['calmar_comp']:.2f} Q+ {m['quarters_pos']} lots≤{m['max_lots']}")
json.dump(out, open(f"{ROOT}/results/audit_v9/compounding_table.json", "w"), indent=1)
