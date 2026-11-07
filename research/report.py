#!/usr/bin/env python3
"""Build reports/strategy_report.html and WINNING_STRATEGIES.md from results/final/."""
import json, os, html, datetime as dt
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIN = os.path.join(ROOT, "results/final")
S = json.load(open(f"{FIN}/final_summary.json"))
sp = S["splits"]


def hhmm(m):
    t = 555 + m
    return f"{t // 60:02d}:{t % 60:02d}"


def rules(c):
    out = []
    st = c.get("structure", "straddle")
    dte = c.get("dte_allowed") or []
    out.append("Trade only on days with DTE " + (", ".join(map(str, dte)) if dte else "any") + " (calendar days to the nearest weekly expiry).")
    ent = ", ".join(hhmm(m) for m in c.get("entry_minutes", [10]))
    if st == "straddle":
        out.append(f"At {ent}: sell the ATM CE + ATM PE (ATM = strike near spot with the smallest |CE−PE|, i.e. synthetic-future ATM).")
    elif st == "strangle_premium":
        out.append(f"At {ent}: sell the OTM CE and OTM PE whose premium is closest to ₹{c['target_premium']} each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹{c['target_premium']}).")
    else:
        out.append(f"At {ent}: sell CE at ATM+{c['otm_steps']} strikes and PE at ATM−{c['otm_steps']} strikes ({c['otm_steps']*50} pts each side).")
    if c.get("hedge_premium", 0) > 0:
        out.append(f"Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹{c['hedge_premium']:g}, at least {c.get('hedge_min_steps', 4)} strikes beyond the shorts — for margin benefit and gap protection.")
    if c.get("sl_mode", "leg") == "leg":
        out.append(f"Per-leg stop-loss: {c['sl_pct']:g}% above each leg's sell price (SL-M).")
    else:
        out.append(f"Combined stop-loss: exit both shorts if CE+PE premium rises {c['combined_sl_pct']:g}% above the combined sell premium.")
    if c.get("move_sl_to_cost"):
        off = c.get("cost_offset", 0) * 100
        out.append(f"When one leg is stopped, move the other leg's SL to its sell price {'+' if off >= 0 else '−'}{abs(off):.1f}% (move-SL-to-cost).")
    if c.get("max_reentries", 0):
        out.append(f"Re-entry: if a stopped leg trades back to its original sell price before {hhmm(c.get('reentry_cutoff', 300))}, re-sell it (max {c['max_reentries']}×).")
    if c.get("wt_drop_pct", 0):
        out.append(f"Wait & trade: sell each leg only after it decays {c['wt_drop_pct']}% from its reference price (within {c.get('wt_window', 60)} min).")
    if c.get("or_filter_pct", 0):
        out.append(f"Skip the day if the first {c.get('or_minutes', 15)}-min spot range exceeds {c['or_filter_pct']}% of spot.")
    if c.get("max_loss_pts", 0):
        out.append(f"Portfolio max loss: exit everything at −{c['max_loss_pts']:g} premium points (≈ ₹{c['max_loss_pts']*65:,.0f} per lot, before costs).")
    if c.get("lock_trigger_pts", 0):
        t = f"Profit lock: once MTM ≥ +{c['lock_trigger_pts']:g} pts, lock {c['lock_pct']*100:.0f}% of it"
        if c.get("trail_step_pts", 0):
            t += f", then raise the lock by {c['trail_by_pts']:g} pts for every further {c['trail_step_pts']:g} pts"
        out.append(t + ".")
    if c.get("roll_ratio", 0):
        out.append(f"Rolling: if |CE−PE|/(CE+PE) > {c['roll_ratio']}, roll the decayed leg to match the other leg's premium (max {c['max_rolls']}×).")
    out.append(f"Time exit: square off everything at {hhmm(c.get('exit_minute', 365))}.")
    return out


items = []
for it in S["items"]:
    r_all = json.load(open(f"{FIN}/{it['key']}_2L_all.json"))
    r3 = json.load(open(f"{FIN}/{it['key']}_3L_all.json"))
    daily = [[d["date"], d["net"], d["dte"], d["traded"], d["exit"], d["exit_time"], d["stops"]] for d in r_all["daily"]]
    daily3 = [d["net"] for d in r3["daily"]]
    trades = defaultdict(list)
    for t in r_all["trades"]:
        trades[t["trade_date"]].append(t)
    worst = sorted([d for d in r_all["daily"] if d["traded"]], key=lambda d: d["net"])[:5]
    worst_rows = []
    for d in worst:
        legs = [f"{t['tag'].split(':')[-1]} {t['side'][0]} {t['strike']}{t['right']} {t['entry_time']}@{t['entry_price']:.1f}→{t['exit_time']}@{t['exit_price']:.1f} ({t['exit_reason']})" for t in trades[d["date"]]]
        worst_rows.append({"date": d["date"], "dte": d["dte"], "net": d["net"], "stops": d["stops"], "exit": d["exit"], "exit_time": d["exit_time"], "legs": legs})
    items.append({
        "key": it["key"], "tier": it["tier"], "label": it["label"], "source": it.get("source_id", ""), "stability": it.get("stability"),
        "configs": it["configs"], "rules": [rules(c) for c in it["configs"]], "metrics": it["metrics"],
        "daily": daily, "daily3": daily3, "monthly": r_all["monthly_pnl"], "monthly3": r3["monthly_pnl"],
        "quarterly": r_all["quarterly_pnl"], "quarterly3": r3["quarterly_pnl"], "yearly": r_all["yearly_pnl"], "yearly3": r3["yearly_pnl"],
        "dte": r_all["dte_breakdown"], "weekday": r_all["weekday_pnl"], "dd_episodes": r_all["worst_drawdown_episodes"], "worst": worst_rows,
    })

# discovery stats from the log
log = open(os.path.join(ROOT, "EXPERIMENT_LOG.md")).read()
v1 = open(os.path.join(ROOT, "results/discovery/EXPERIMENT_LOG_v1.md")).read()
import re
runs_total = sum(int(x) for x in re.findall(r"\((\d+) train runs", log + v1))
gens_total = len(re.findall(r"^## Generation", log + v1, re.M))
DATA = {"splits": sp, "items": items, "runs_total": runs_total, "gens_total": gens_total,
        "generated": dt.date.today().isoformat()}

TEMPLATE = open(os.path.join(ROOT, "research/report_template.html")).read()
os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
with open(os.path.join(ROOT, "reports/strategy_report.html"), "w") as f:
    f.write(TEMPLATE.replace("/*__DATA__*/null", json.dumps(DATA, separators=(",", ":"))))

# ------------------------------------------------------------------ WINNING_STRATEGIES.md
def row(name, m):
    return (f"| {name} | {m['traded_days']} | ₹{m['net_pnl_rupees']:,.0f} | {m['roi_annual_pct']:.1f}% | ₹{m['max_drawdown_rupees']:,.0f} ({m['max_drawdown_pct']:.1f}%) | "
            f"{m['calmar_ratio']:.2f} | {m['win_rate_pct']:.1f}% | {m['profit_factor']:.2f} | {m['max_consecutive_losing_days']} | ₹{m['expectancy_per_trade_rupees']:,.0f} | ₹{m['worst_day_rupees']:,.0f} | {m['losing_months_pct']:.0f}% |")

md = ["# WINNING_STRATEGIES — NIFTY intraday non-directional option selling", "",
      f"Generated {DATA['generated']} by `research/finalize.py` + `research/report.py`. Interactive version: `reports/strategy_report.html`.", "",
      "## Data, splits and assumptions", "",
      "- Data: Kaggle `senthilkumarvaithi/historical-nifty-options-2024-all-expiries` (2024, true 1-min OHLC) + `pariminikhil/nifty-option-chain-3-oct-24-to-24-mar-26` (Jan-2025 → Mar-2026, 1-min LTP; bar high/low = envelope of consecutive LTPs). Nearest weekly expiry only, strikes within ±1500 pts of the 09:15 spot. 551 trading days.",
      f"- Chronological splits: **train** {sp['train'][0]}–{sp['train'][1]} (65%), **validation** {sp['valid'][0]}–{sp['valid'][1]} (20%), **holdout** {sp['holdout'][0]}–{sp['holdout'][1]} (15%).",
      "- Costs on every order: ₹20 brokerage, STT 0.1% (sell), NSE txn 0.03503%, SEBI ₹10/cr, stamp 0.003% (buy), GST 18%. Slippage 0.3% per market fill (min ₹0.05), plus 0.5% on stop fills; stops fill at max(trigger, bar open).",
      "- Lot size normalised to **65** for all years. **₹2L capital = 1 lot**, **₹3L capital = 2 lots** (≈₹1.5L margin per hedged lot). Every structure buys far-OTM wings so margin stays inside that budget. Brokerage is flat per order, so 2 lots cost proportionally less.",
      "- Hard gate (all per 1 lot on ₹2L): expectancy ≥ ₹450/trade-day, worst day ≤ 2.5× p90 winning day and ≤ 1.5% of capital (₹3,000), ≤ 15% losing months, max underwater ≤ 25 active trading days. Stability ratio ≥ 0.75 (entry ±1/±2 min, SL ±2.5/±5 pts). Out-of-sample: Calmar ≥ 3.5 and PF ≥ 1.45 on validation **and** holdout.", "",
      "## Verdict", "",
      "- **Tier A (passed every gate): S1, the expiry-day (DTE 0) premium-matched strangle.**",
      "- **Tier B (stable, passed validation, missed one train gate by a small margin under a rule fixed before they saw the holdout): S2 (DTE 2–3) and S3 (DTE 4–6).** S3 then also passed the holdout bar (Calmar 6.44, PF 1.55). S2 has only 2 holdout days, because NIFTY weekly expiry moved from Thursday to Tuesday in Sep-2025 and DTE-2/3 sessions have almost disappeared since. **S2 is not deployable on the current calendar.**",
      "- Baselines (plain straddles) show what the defence mechanics are worth: the plain every-day hedged straddle nets only ₹15k over 2.2 years with a ₹58k drawdown.",
      "- Recommended live set for **₹2L: P1 = S1 + S3** (they trade on different days, so only one hedged lot is ever open). For **₹3L, run the same set with 2 lots.**", ""]
for it in items:
    m = it["metrics"]
    md += [f"## {it['key']} — {it['label']}  (tier: {it['tier']})", ""]
    if it["source"] and it["source"] != "baseline":
        md.append(f"Source candidate `{it['source']}`" + (f", stability ratio **{it['stability']:.2f}**" if it["stability"] else "") + ".")
        md.append("")
    for c, rl in zip(it["configs"], it["rules"]):
        md.append(f"**Rules — `{c['name']}`**")
        md += [f"{i+1}. {r}" for i, r in enumerate(rl)]
        md += ["", "```json", json.dumps(c, indent=1), "```", ""]
    md += ["| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, n in [("2L_train", "In-sample (train) ₹2L"), ("2L_valid", "Validation ₹2L"), ("2L_holdout", "Holdout ₹2L"), ("2L_all", "Full period ₹2L / 1 lot"), ("3L_all", "Full period ₹3L / 2 lots"), ("2L_all_zerobrok", "Full ₹2L, zero brokerage")]:
        md.append(row(n, m[k]))
    md += ["", "**Monthly net P&L (₹, 1 lot)**", "", "| Month | " + " | ".join(f"{i:02d}" for i in range(1, 13)) + " | Year |", "|---" * 14 + "|"]
    years = sorted({k[:4] for k in it["monthly"]})
    for y in years:
        cells = [f"{it['monthly'].get(f'{y}-{i:02d}', 0):,.0f}" if f"{y}-{i:02d}" in it["monthly"] else "" for i in range(1, 13)]
        md.append(f"| {y} | " + " | ".join(cells) + f" | **{it['yearly'].get(y, 0):,.0f}** |")
    md += ["", "**Quarterly (₹):** " + ", ".join(f"{k}: {v:,.0f}" for k, v in it["quarterly"].items()), ""]
    md += ["**Top-5 worst days**", "", "| Date | DTE | Net ₹ | Stops | Final exit | Legs |", "|---|---|---|---|---|---|"]
    for w in it["worst"]:
        md.append(f"| {w['date']} | {w['dte']} | {w['net']:,.0f} | {w['stops']} | {w['exit']} @ {w['exit_time']} | " + "<br>".join(w["legs"]) + " |")
    md.append("")
md += ["## Worst-day analysis (S1 / S3)", "",
       "- S1's five worst days are all the same pattern: a fast move right after the 09:23 entry stops one leg (20% SL), the other leg's SL is pulled to cost +7.4%, the reversal stops it too, and the 18-point portfolio cap closes the day at about −₹1.6k. The tail is **capped by construction**. No day lost more than ₹1,603 on 1 lot.",
       "- S3 (DTE 4–6) loses through slow trend days: one leg stopped, the other decays too slowly to pay for it. Its worst day is −₹2.5k, also inside the ₹3k gate.",
       "- Phase-D diagnostics in the log flagged double-SL whipsaws and gap-and-go mornings as the main loss drivers. That is why move-SL-to-cost and the hard max-loss survive in every finalist.", "",
       "## Honest caveats", "",
       "- 551 days (≈2.2 years) is a short history for tail risk. A 2020-style crash or a budget-day gap is not in the sample.",
       "- 2025–26 data is 1-minute LTP, not true OHLC, so intrabar spikes beyond the LTP envelope are missed. The 0.5% stop slippage only partly compensates.",
       "- Wing prices of ₹2–5 are often stale or illiquid; real fills can be worse.",
       "- ~8,000 configurations were tested. Splits, stability and a holdout were used, but selection bias cannot be fully removed. Paper-trade before going live.",
       "- 2026 Q1 (holdout tail) was flat to slightly negative for S2/S3. Edge decay is possible.",
       ]
open(os.path.join(ROOT, "WINNING_STRATEGIES.md"), "w").write("\n".join(md) + "\n")
print("ok", runs_total, gens_total)
