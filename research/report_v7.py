#!/usr/bin/env python3
"""Build reports/strategy_report.html (v2), WINNING_STRATEGIES.md and ALGOTEST_SETUP.md from results/final_v7."""
import json, os, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = json.load(open(f"{ROOT}/results/final_v7/final.json"))
A = json.load(open(f"{ROOT}/results/final_v7/audit.json"))


def cum(rows):
    c, out = 0.0, []
    for d, x in rows:
        c += x
        out.append([int(d), round(c, 2)])
    return out


lot = F["runs"]["1lot"]
wf6 = [[d, x] for d, x in F["wf_v6"]]
wf7 = [[d, x] for d, x in F["wf_v7"]]
first_wf = wf6[0][0] if wf6 else 0
full_daily = [[d[0], d[1]] for d in lot["daily"]]
DATA = {
    "generated": dt.date.today().isoformat(),
    "cfg": F["cfg"], "sheet": F["sheet"], "mult": F["multipliers_now"],
    "runs": {k: {kk: v[kk] for kk in ("metrics", "nowick", "slip2", "mc95", "mc99", "fee", "monthly", "quarterly", "yearly", "worst", "dd_episodes")} for k, v in F["runs"].items()},
    "equity": {"full": cum(full_daily), "wf6": cum(wf6), "wf7": cum(wf7), "full_from_wf": cum([r for r in full_daily if r[0] >= first_wf])},
    "daily_lot": [[d[0], d[1], d[3], d[5], d[6], d[7]] for d in lot["daily"] if d[5]],
    "wf6": F["wf_v6_metrics"], "wf7": F["wf_v7_metrics"], "wf_picks": F["wf_v7_picks"],
    "wf_other": F["wf_other_dte"], "wf_h2": F["wf_h2"],
    "dsr": F["dsr"], "sharpe": F["sharpe_ann"], "wf_sharpe": F["wf_sharpe_ann"],
    "forced": {k: v for k, v in F["forced"]["tdte"].items()}, "shock": F["shock_table"],
    "audit": A["audit"], "wick_validation": A["wick_validation"], "crosscheck": A["crosscheck"], "wick_q": A["wick_quantiles"], "span": A["span_calibration"],
    "trades_worst": F["runs"]["1lot"].get("trades_worst", []),
    "a9": {k: json.load(open(f"{ROOT}/results/audit_v9/{f}")) for k, f in (("overfit", "overfit_audit.json"), ("comp", "compounding_table.json"), ("regime", "regime_oi_study.json"),
           ("side", "sideways_strangles.json"), ("books", "varsity_books.json"), ("basket", "basket.json"), ("gng", "gap_and_go_only.json"))},
    "gw": {k: v["summary"] for k, v in json.load(open(f"{ROOT}/results/audit_v9/gap_williams.json")).items()},
    "fe": (lambda fe: {**{k: v for k, v in fe.items() if k != "wf_eq"}, "wf_eq": {k: cum(v) for k, v in fe["wf_eq"].items()}})(json.load(open(f"{ROOT}/results/v8/framework_eval.json"))),
}
tpl = open(f"{ROOT}/research/report_v7_template.html").read()
os.makedirs(f"{ROOT}/reports", exist_ok=True)
open(f"{ROOT}/reports/strategy_report.html", "w").write(tpl.replace("/*__DATA__*/null", json.dumps(DATA, separators=(",", ":"))))

# ------------------------------------------------------------------ markdown deliverables
m = lot["metrics"]; m3 = F["runs"]["3L"]["metrics"]; w6, w7 = F["wf_v6_metrics"], F["wf_v7_metrics"]
sh = F["sheet"]


def table(rows, head):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


setup = ["# AlgoTest setup — NIFTY Expiry-Day Iron Fly", "",
         "Every value below is an AlgoTest builder field (docs.algotest.in). Backtest it on AlgoTest with **taxes & charges ON and 0.5% slippage** before going live, then forward-test (paper) for at least 4–6 expiries.", "",
         "## Strategy (Backtest → Create strategy → Intraday)", ""] + table(sh["settings"], ["Field", "Value"]) + ["", "## Legs (Leg builder)", ""]
lh = list(sh["legs"][0].keys())
setup += table([[l[k] for k in lh] for l in sh["legs"]], lh)
setup += ["", "## Overall strategy settings", ""] + table(sh["overall"] or [["-", "-"]], ["Field", "Value"])
setup += ["", "## Portfolio, sizing and execution", ""] + table(sh["portfolio"], ["Field", "Value"])
setup += ["", "## Margin you need (calibrated on the exchange SPAN file, NIFTY ≈ 25,000, lot 65)", "",
          "- Expiry day, 1 lot of this iron fly: SPAN ≈ ₹40k + exposure ≈ ₹62k + SEBI expiry-day ELM 2% ≈ ₹65k → **≈ ₹1.67–1.74 lakh**.",
          "- 2 lots therefore need ≈ ₹3.5 lakh, so **₹2L and ₹3L both run 1 lot** (quantity multiplier 1). A ₹3L account keeps ~₹1.3L as buffer.",
          "- Always place the BUY wings first (Delay entry on SELL legs), otherwise the broker blocks naked-short margin (~₹2.2L+)."]
open(f"{ROOT}/results/final_v7/ALGOTEST_SETUP_base.md", "w").write("\n".join(setup) + "\n")

md = ["# WINNING_STRATEGIES — NIFTY intraday non-directional selling (v2, realistic engine)", "",
      f"Generated {DATA['generated']}. Interactive report: `reports/strategy_report.html`. AlgoTest field-by-field setup: `ALGOTEST_SETUP.md`.", "",
      "## Bottom line", "",
      "- After the external review the engine was made realistic: slippage, intra-minute wicks, SPAN margin with the expiry-day ELM, and trading-day DTE. Under it, **the earlier P1 portfolio does not survive** (holdout Calmar 11.6 → 0.7) and the DTE 4–6 strategy loses money out of sample.",
      "- **One strategy survives an honest anchored walk-forward: the expiry-day (trading DTE 0) iron fly.** In the walk-forward every quarter's parameters were chosen only from earlier data; the procedure picked the same structure, entry time and stop logic each quarter.",
      "- Intraday selling on DTE 1, 2, 3 and 4 (morning or afternoon) **lost money out of sample** after costs. So nothing is deployed on Mon/Wed/Thu/Fri; the capital is idle on purpose.",
      f"- **Expected (walk-forward, 1 lot): ≈ ₹{w6['net'] / 1.73:,.0f}/yr (~{w6['net'] / 1.73 / 2000:.0f}% on ₹2L), max DD ≈ ₹{w6['dd']:,.0f}.** Full-sample optimised (an upper bound): ₹{m['net_pnl_rupees']:,.0f} over 2.2 yrs, DD ₹{m['max_drawdown_rupees']:,.0f}, PF {m['profit_factor']:.2f}.",
      "- The edge is **shrinking**: 2024 ₹{:,.0f}, 2025 ₹{:,.0f}, 2026-Q1 ₹{:,.0f} (1 lot).".format(*[lot["yearly"].get(y, 0) for y in ("2024", "2025", "2026")]),
      f"- **Statistical caution:** the Deflated Sharpe ratio is {F['dsr']['1000']:.2f} at 1,000 effective trials. 117 expiry days are too few to prove the edge is not luck. **Paper-trade first.**", "",
      "## The strategy", "", "```json", json.dumps(F["cfg"], indent=1), "```", ""]
md += table([["Full sample, 1 lot (₹2L)", m["traded_days"], f"₹{m['net_pnl_rupees']:,.0f}", f"{m['roi_annual_pct']:.1f}%", f"₹{m['max_drawdown_rupees']:,.0f}", f"{m['calmar_ratio']:.2f}", f"{m['profit_factor']:.2f}", f"{m['win_rate_pct']:.1f}%", f"₹{m['expectancy_per_trade_rupees']:,.0f}", f"₹{m['worst_day_rupees']:,.0f}"],
             ["Full sample, ₹3L margin-sized", m3["traded_days"], f"₹{m3['net_pnl_rupees']:,.0f}", f"{m3['roi_annual_pct']:.1f}%", f"₹{m3['max_drawdown_rupees']:,.0f}", f"{m3['calmar_ratio']:.2f}", f"{m3['profit_factor']:.2f}", f"{m3['win_rate_pct']:.1f}%", f"₹{m3['expectancy_per_trade_rupees']:,.0f}", f"₹{m3['worst_day_rupees']:,.0f}"],
             ["Walk-forward OOS v6 (clean), 1 lot", w6["n"], f"₹{w6['net']:,.0f}", f"{w6['net'] / 1.73 / 2000:.1f}%", f"₹{w6['dd']:,.0f}", f"{w6['calmar']:.2f}", f"{w6['pf']:.2f}", "-", "-", f"₹{w6['worst']:,.0f}"],
             ["Walk-forward OOS v7-H1, 1 lot", w7["n"], f"₹{w7['net']:,.0f}", f"{w7['net'] / 1.73 / 2000:.1f}%", f"₹{w7['dd']:,.0f}", f"{w7['calmar']:.2f}", f"{w7['pf']:.2f}", "-", "-", f"₹{w7['worst']:,.0f}"]],
            ["Window", "Trade days", "Net", "ROI/yr", "Max DD", "Calmar", "PF", "Win %", "Exp/day", "Worst day"])
md += ["", "₹3L note: the 2-lot days are all before 20-Nov-2024. Since the 2% expiry-day ELM, ₹3L funds only 1 lot, so going forward the ₹3L result ≈ the ₹2L result.", "",
       "## Hard-gate check (your spec)", "", f"- Expectancy ≥ ₹450/lot-day: **pass** (₹{m['expectancy_per_trade_rupees']:,.0f}).",
       f"- Worst day ≤ 1.5% of capital (₹3,000): **fail** (₹{-m['worst_day_rupees']:,.0f}); ≤ 2.5× p90 win: pass.",
       f"- ≤ 15% losing months: **fail** ({m['losing_months_pct']:.0f}%). With ~4 trades/month some red months are unavoidable.",
       f"- Max underwater ≤ 25 active days: **pass** ({m['max_dd_duration_active_days']}).", "",
       "## Stress tests (1 lot)", ""]
md += table([["Base (wicks + 0.5%/1% slippage)", f"₹{m['net_pnl_rupees']:,.0f}", f"₹{m['max_drawdown_rupees']:,.0f}"],
             ["No synthetic wicks (optimistic)", f"₹{lot['nowick']['net_pnl_rupees']:,.0f}", f"₹{lot['nowick']['max_drawdown_rupees']:,.0f}"],
             ["Slippage ×2 (1% / 2% / ₹0.20 min)", f"₹{lot['slip2']['net_pnl_rupees']:,.0f}", f"₹{lot['slip2']['max_drawdown_rupees']:,.0f}"],
             ["Monte-Carlo DD 95th / 99th pct", "-", f"₹{lot['mc95']:,.0f} / ₹{lot['mc99']:,.0f}"],
             ["AlgoTest platform fee (100 credits/28 days)", f"−₹{lot['fee']:,.0f} total", "-"]], ["Scenario", "Net", "Max DD"])
md += ["", "Same rules forced onto every day (shows why the DTE-0 filter is structural):", ""]
md += table([[k, f"₹{v['net_rupees']:,.0f}", v["days"]] for k, v in sorted(F["forced"]["tdte"].items(), key=lambda x: int(x[0]))], ["Trading DTE", "Net (1 lot)", "Days"])
md += ["", "## Monthly P&L (₹, 1 lot)", ""]
years = sorted({k[:4] for k in lot["monthly"]})
md += table([[y] + [f"{lot['monthly'].get(f'{y}-{i:02d}', 0):,.0f}" if f"{y}-{i:02d}" in lot["monthly"] else "" for i in range(1, 13)] + [f"**{lot['yearly'].get(y, 0):,.0f}**"] for y in years],
            ["Year"] + [f"{i:02d}" for i in range(1, 13)] + ["Year"])
md += ["", "Quarterly: " + ", ".join(f"{k}: ₹{v:,.0f}" for k, v in lot["quarterly"].items()), "", "## Worst 5 days (1 lot)", ""]
md += table([[d["date"], d["tdte"], f"₹{d['net']:,.0f}", d["stops"], f"{d['exit']} @ {d['exit_time']}"] for d in lot["worst"]], ["Date", "DTE", "Net", "Stops", "Final exit"])
md += ["", "## What was rejected (walk-forward out-of-sample, 1 lot)", ""]
md += table([[b.replace('tdte', 'DTE '), "morning grid (v6)", f"₹{v['net']:,.0f}", f"{v['pf']:.2f}"] for b, v in F["wf_other_dte"].items()] +
            [[b.replace('tdte', 'DTE '), "afternoon grid (v7-H2)", f"₹{v['net']:,.0f}", f"{v['pf']:.2f}" if v['n'] else "no stable config"] for b, v in F["wf_h2"].items()], ["Day", "Search", "OOS net", "OOS PF"])
md += ["", "Earlier strategies re-tested on the realistic engine (holdout Calmar / PF, full-period net):", ""]
md += table([[r[0], r[1], r[2], r[3], f"₹{r[4]:,.0f}", f"₹{r[5]:,.0f}"] for r in A["audit"]], ["Strategy", "Model", "Holdout Calmar", "Holdout PF", "Full net", "Full DD"])
md += ["", "## Caveats", "",
       "- 2025–26 option data is minute LTP; true intra-minute highs are modelled with wicks calibrated on true OHLC (validated on Oct–Dec 2024). True OHLC for 2025–26 (e.g. Upstox expired-instrument API) would remove this approximation.",
       "- 551 trading days include only 117 expiry days. The Deflated Sharpe is low, and the out-of-sample edge (PF 1.44–1.66) is real but modest.",
       "- Results use today's lot (65) and today's charges for every year so they read as 'what this would make now'.",
       "- The AlgoTest backtest checks overall SL at candle close; live trading checks it on LTP, so live exits can be slightly earlier or later.",
       "- This is research, not investment advice."]
open(f"{ROOT}/results/final_v7/WINNING_STRATEGIES_base.md", "w").write("\n".join(md) + "\n")
print("ok")
