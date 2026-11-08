#!/usr/bin/env python3
"""Capital reuse & compounding metrics, in the same columns as the other trader's table.

Intraday positions release all margin at the close, so the same capital is reused on every trading day.
Compounding = re-sizing lots from current equity each day:
    lots = floor(equity * util / margin_per_lot(day))   (util 0.75 -> 25% cash buffer)
    pnl(lots) = lots * (pnl_1lot + brokerage_1lot) - brokerage_1lot     (brokerage is per order, not per lot)
"""
import json, math, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = f"{ROOT}/opt_engine/target/release/opt_engine"; CACHE = f"{ROOT}/data/cache/nifty_wick.bin"
BROK_PER_ORDER = 20 * 1.18


def run(cfg, tag, exec_cfg=None):
    p = f"{ROOT}/configs/audit/{tag}.json"
    w = {"strategy": cfg}
    if exec_cfg:
        w["exec"] = exec_cfg
    json.dump(w, open(p, "w"))
    o = f"{ROOT}/results/audit_v9/{tag}.json"
    subprocess.run([BIN, "backtest", "--cache", CACHE, "--strategy-config", p, "--out", o, "--no-trades"], check=True, capture_output=True)
    return [(d["date"], d["net"], d["margin"], d["orders"], d["traded"]) for d in json.load(open(o))["daily"]]


def metrics(rows, capital, util=0.75, max_lots=50, risk_per_trade=None):
    years = len(rows) / 252
    # 1 lot always
    eq1, peak1, dd1, low1 = capital, capital, 0.0, capital
    eqc, peakc, ddc_pct, lowc = capital, capital, 0.0, capital
    dd1_rs = 0.0
    daily_ret_c, by_year_c, by_year_1, by_q = [], {}, {}, {}
    lots_used = []
    for d, pnl1, margin1, orders, traded in rows:
        y = str(d // 10000); q = f"{y}-Q{((d // 100) % 100 - 1) // 3 + 1}"
        # 1 lot
        if traded and margin1 <= capital:
            eq1 += pnl1
        peak1 = max(peak1, eq1); dd1 = max(dd1, (peak1 - eq1) / peak1); dd1_rs = max(dd1_rs, peak1 - eq1); low1 = min(low1, eq1)
        by_year_1[y] = by_year_1.get(y, 0) + (pnl1 if traded else 0)
        # compounding
        start = eqc
        if traded:
            lots = min(max_lots, int(eqc * util // margin1)) if margin1 > 0 else 1
            if lots >= 1:
                brok = orders * BROK_PER_ORDER
                eqc += lots * (pnl1 + brok) - brok
                lots_used.append(lots)
        daily_ret_c.append(eqc / start - 1)
        by_year_c.setdefault(y, [start, eqc]); by_year_c[y][1] = eqc
        by_q[q] = by_q.get(q, 0) + (pnl1 if traded else 0)
        peakc = max(peakc, eqc); ddc_pct = max(ddc_pct, (peakc - eqc) / peakc); lowc = min(lowc, eqc)
    m = sum(daily_ret_c) / len(daily_ret_c); sd = math.sqrt(sum((r - m) ** 2 for r in daily_ret_c) / (len(daily_ret_c) - 1))
    dn = math.sqrt(sum(min(r, 0) ** 2 for r in daily_ret_c) / len(daily_ret_c))
    cagr1 = (eq1 / capital) ** (1 / years) - 1
    cagrc = (eqc / capital) ** (1 / years) - 1
    worst_year = min((v[1] / v[0] - 1) for v in by_year_c.values())
    return {
        "risk_per_trade_pct": risk_per_trade / capital * 100 if risk_per_trade else None,
        "rs_per_year_1lot": (eq1 - capital) / years, "simple_return_pct": (eq1 - capital) / years / capital * 100,
        "cagr_1lot_pct": cagr1 * 100, "cagr_comp_pct": cagrc * 100, "maxdd_comp_pct": ddc_pct * 100,
        "maxdd_1lot_pct": dd1 * 100, "maxdd_1lot_rs": dd1_rs, "lowest_equity_1lot": low1, "lowest_equity_comp": lowc,
        "worst_year_pct": worst_year * 100, "sharpe": m / sd * math.sqrt(252) if sd else 0, "sortino": m / dn * math.sqrt(252) if dn else 0,
        "calmar_comp": (cagrc / ddc_pct) if ddc_pct else 0, "quarters_pos": f"{sum(1 for v in by_q.values() if v > 0)}/{len(by_q)}",
        "years_pos": f"{sum(1 for v in by_year_1.values() if v > 0)}/{len(by_year_1)}", "final_equity_comp": eqc, "max_lots_used": max(lots_used or [0]),
        "avg_lots_used": sum(lots_used) / len(lots_used) if lots_used else 0}


if __name__ == "__main__":
    F = json.load(open(f"{ROOT}/results/final_v7/final.json"))
    base = {**F["cfg"], "sizing": {"mode": "fixed", "multiplier": 1}}
    w8 = json.loads(json.dumps(base)); w8["legs"][2]["strike"]["n"] = 8; w8["legs"][3]["strike"]["n"] = 8
    out = {}
    for name, cfg, cap in (("Expiry iron fly ±400 · ₹2L", w8, 2e5), ("Expiry iron fly ±600 · ₹3L", base, 3e5), ("Expiry iron fly ±600 · ₹2L", base, 2e5)):
        rows = run(cfg, name.split("·")[0].strip().replace(" ", "_").replace("±", ""))
        for util in (0.75, 0.9):
            out[f"{name} · util {int(util*100)}%"] = metrics(rows, cap, util, risk_per_trade=2000 + 400)
    json.dump(out, open(f"{ROOT}/results/audit_v9/compounding.json", "w"), indent=1)
    for k, v in out.items():
        print(k, {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items()})
