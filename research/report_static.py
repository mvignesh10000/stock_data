#!/usr/bin/env python3
"""Static, JavaScript-free strategy report -> reports/strategy_report.html.

Every table and chart is pre-rendered (HTML tables + inline SVG with native <title> tooltips), so the page
works in any browser, phone file preview, mail attachment or sandboxed viewer that blocks scripts."""
import html, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_v7 as R  # builds R.DATA (also refreshes the base markdown copies)

D = R.DATA
ROOT = R.ROOT
E = html.escape


# ------------------------------------------------------------------ formatting helpers
def rs(v, d=0):
    if v is None:
        return "–"
    s = f"{abs(v):,.{d}f}"
    # Indian grouping
    whole, _, frac = s.partition(".")
    whole = whole.replace(",", "")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("−" if v < 0 else "") + "₹" + whole + ("." + frac if frac else "")


def sg(v):
    return f'<span class="{"neg" if (v or 0) < 0 else ""}">{rs(v)}</span>'


def pc(v, d=1):
    return "–" if v is None else f"{v:.{d}f}%"


def n2(v):
    return "–" if v is None else f"{v:.2f}"


def dstr(d):
    d = str(d)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def table(head, rows, cls="", left_cols=()):
    h = "".join(f"<th>{c}</th>" for c in head)
    body = []
    for r in rows:
        tds = []
        for i, c in enumerate(r):
            tds.append(f'<td class="l">{c}</td>' if i in left_cols else f"<td>{c}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="tscroll"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def card(title, inner, note=None, extra_cls=""):
    t = f"<h3>{title}</h3>" if title else ""
    n = f'<p class="note">{note}</p>' if note else ""
    return f'<section class="card {extra_cls}">{t}{inner}{n}</section>'


# ------------------------------------------------------------------ SVG charts (no JS)
COLS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--neg)"]


def line_svg(sets, label, h=280, area=False, zero_top=False):
    W, L, Rp, T, B = 1000, 70, 60, 12, 28
    allv = [p[1] for s in sets for p in s["pts"]] or [0]
    ymin, ymax = min(0, *allv), max(0, *allv)
    if ymax == ymin:
        ymax = ymin + 1
    pad = (ymax - ymin) * 0.06
    if not zero_top:
        ymin -= pad
        ymax += pad
    dates = sorted({p[0] for s in sets for p in s["pts"]})
    idx = {d: i for i, d in enumerate(dates)}
    N = max(2, len(dates))
    x = lambda i: L + (W - L - Rp) * i / (N - 1)
    y = lambda v: T + (h - T - B) * (ymax - v) / (ymax - ymin)
    g = [f'<svg viewBox="0 0 {W} {h}" width="100%" role="img" aria-label="{E(label)}">']
    for k in range(5):
        v = ymin + (ymax - ymin) * k / 4
        g.append(f'<line x1="{L}" x2="{W - Rp}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/><text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{rs(round(v / 1000))}k</text>')
    g.append(f'<line x1="{L}" x2="{W - Rp}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="zero"/>')
    last_y = None
    for i, d in enumerate(dates):
        yr = str(d)[:4]
        if yr != last_y:
            last_y = yr
            g.append(f'<text x="{x(i):.1f}" y="{h - 8}">{yr}</text>')
    for j, s in enumerate(sets):
        col = s.get("color", COLS[j % 4])
        pts = [(x(idx[p[0]]), y(p[1])) for p in s["pts"]]
        if not pts:
            continue
        path = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
        if area:
            g.append(f'<path d="{path} L{pts[-1][0]:.1f} {y(0):.1f} L{pts[0][0]:.1f} {y(0):.1f} Z" fill="{col}" opacity=".18"/>')
        g.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="{1.5 if area else 2}"><title>{E(s["name"])}</title></path>')
        # hover dots every ~20th point with native tooltip
        step = max(1, len(pts) // 60)
        for k in range(0, len(pts), step):
            dd, vv = s["pts"][k]
            g.append(f'<circle cx="{pts[k][0]:.1f}" cy="{pts[k][1]:.1f}" r="5" fill="transparent"><title>{E(s["name"])} · {dstr(dd)}: {rs(vv)}</title></circle>')
        if s.get("short"):
            g.append(f'<text x="{pts[-1][0] + 4:.1f}" y="{pts[-1][1] + 4:.1f}" class="lbl">{E(s["short"])}</text>')
    g.append("</svg>")
    return "".join(g)


def legend(sets):
    return '<div class="legend">' + "".join(f'<span><i style="background:{s.get("color", COLS[j % 4])}"></i>{E(s["name"])}</span>' for j, s in enumerate(sets)) + "</div>"


def bar_svg(items, label, h=230, rotate=False):
    """items: [(label, value, tooltip)]"""
    W, L, B, T = 1000, 70, 46 if rotate else 30, 10
    vals = [v for _, v, _ in items] or [0]
    mx, mn = max(1, *vals), min(0, *vals)
    y = lambda v: T + (h - T - B) * (mx - v) / (mx - mn)
    bw = (W - L - 6) / max(1, len(items))
    g = [f'<svg viewBox="0 0 {W} {h}" width="100%" role="img" aria-label="{E(label)}">']
    for v in (mn, 0, mx):
        g.append(f'<line x1="{L}" x2="{W - 4}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/><text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{rs(round(v / 1000))}k</text>')
    for i, (lab, v, tip) in enumerate(items):
        x0, w = L + i * bw + 2, max(2, bw - 4)
        top, ht = min(y(v), y(0)), max(1, abs(y(v) - y(0)))
        col = "var(--s1)" if v >= 0 else "var(--neg)"
        g.append(f'<rect x="{x0:.1f}" y="{top:.1f}" width="{w:.1f}" height="{ht:.1f}" rx="3" fill="{col}"><title>{E(tip)}</title></rect>')
        if rotate:
            if i % 2 == 0:
                g.append(f'<text x="{x0 + w / 2:.1f}" y="{h - 30}" text-anchor="end" transform="rotate(-45 {x0 + w / 2:.1f} {h - 30})">{E(lab)}</text>')
        else:
            g.append(f'<text x="{x0 + w / 2:.1f}" y="{h - 10}" text-anchor="middle">{E(lab)}</text>')
    g.append("</svg>")
    return "".join(g)


def heat(monthly, yearly):
    vals = [v for v in monthly.values() if v != 0]
    mx = max([abs(v) for v in vals] or [1])
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    rows = []
    for y_ in sorted({k[:4] for k in monthly}):
        cells = [f"<td><b>{y_}</b></td>"]
        for i in range(1, 13):
            k = f"{y_}-{i:02d}"
            v = monthly.get(k)
            if v is None or v == 0:
                cells.append("<td></td>")
            else:
                a = 0.15 + 0.75 * min(1, abs(v) / mx)
                bg = f"rgba(42,120,214,{a:.2f})" if v >= 0 else f"rgba(208,59,59,{a:.2f})"
                fg = "color:#fff;" if a > 0.55 else ""
                cells.append(f'<td style="background:{bg};{fg}" title="{k}: {rs(v)}">{round(v):,}</td>')
        cells.append(f"<td><b>{sg(yearly.get(y_, 0))}</b></td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    head = "<th>Year</th>" + "".join(f"<th>{m}</th>" for m in months) + "<th>Year</th>"
    return f'<div class="tscroll"><table class="heat"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def tiles(m, r, cap_label):
    t = [("Net P&amp;L (2.2 yrs)", rs(m["net_pnl_rupees"]), f'{m["traded_days"]} expiry days'),
         ("ROI / year", pc(m["roi_annual_pct"]), cap_label),
         ("Max drawdown", rs(m["max_drawdown_rupees"]), pc(m["max_drawdown_pct"]) + " of capital"),
         ("Calmar · PF", f'{n2(m["calmar_ratio"])} · {n2(m["profit_factor"])}', "Sharpe " + n2(m["sharpe_ratio"])),
         ("Win rate", pc(m["win_rate_pct"]), f'max {m["max_consecutive_losing_days"]} losers in a row'),
         ("Worst day", rs(m["worst_day_rupees"]), "best " + rs(m["best_day_rupees"])),
         ("Monte-Carlo DD", rs(r["mc95"]), "95th pct · 99th " + rs(r["mc99"])),
         ("Peak margin", rs(m["peak_margin_max"]), "avg " + rs(m["peak_margin_avg"]) + " on trade days")]
    return '<div class="tiles">' + "".join(f'<div class="tile"><div class="k">{a}</div><div class="v">{b}</div><div class="s">{c}</div></div>' for a, b, c in t) + "</div>"


# ------------------------------------------------------------------ page
r1, r3 = D["runs"]["1lot"], D["runs"]["3L"]
m1 = r1["metrics"]
w6, w7 = D["wf6"], D["wf7"]
c = D["cfg"]
wings = c["legs"][2]["strike"]["n"]
parts = []
parts.append(f'''<header class="row"><div><h1>NIFTY intraday non-directional selling — strategy report</h1>
<p class="sub">Backtest 2024-01-01 → 2026-03-24 · 551 trading days (117 expiry days) · generated {D["generated"]} · all costs, 0.5% slippage per fill + 1% on stops, intra-minute wicks, SPAN-calibrated margin</p></div></header>
<nav class="card toc"><b>Contents</b> <a href="#s1">1 Strategy</a> <a href="#s2">2 Equity</a> <a href="#s3">3 Stress</a> <a href="#s4">4 AlgoTest setup</a> <a href="#s5">5 Rejected</a> <a href="#s7">7 VIX framework</a> <a href="#s8">8 Round 3: overfit · compounding · OI · other strategies</a> <a href="#s6">6 Data validation</a></nav>''')

a9 = D["a9"]
o = a9["overfit"]
parts.append(card("Verdict (latest)", f'''<ul>
<li><b>Core strategy: expiry-day iron fly</b> (trading DTE 0, every Tuesday). Sell ATM CE+PE at 09:20, buy OTM wings, 60% leg SL, trail-to-breakeven, ₹2,000 overall SL, exit 15:15.</li>
<li><b>It is partially overfit.</b> The structure has an edge (62% of 432 variants profitable; bootstrap CI of mean P&amp;L &gt; 0), but our pick sits at the top of that distribution, a one-shot 2024→2025-26 test of the simpler procedure failed, and PBO is {o["pbo_v6"]["pbo"]*100:.0f}–{o["pbo_v7"]["pbo"]*100:.0f}%. <b>Plan on ₹8–25k per lot per year</b>, not the full-sample ₹42k. The edge is shrinking.</li>
<li><b>₹2L:</b> fly with ±400 wings, 1 lot. <b>₹3L:</b> fly ±400 + the <b>ORB directional hedged spread</b> on expiry day (uncorrelated, positive in 2024 and 2025-26). Paper-trade the <b>Gap-and-Go buy</b> as a third book.</li>
<li>Rejected after testing: VIX switching, ORB straddle buying, sideways-day strangles, OI-wall selling, butterflies/Batman/ratios intraday, all non-expiry selling, the Williams back-up, naked straddles.</li></ul>''', extra_cls="verdict"))

# 1 strategy
rules = [f"Trade only on <b>expiry day</b> (trading DTE 0): Thursday before 2-Sep-2025, <b>Tuesday</b> now.",
         f"At <b>{c['entry_time']}</b> (AlgoTest time = close of the 09:19 candle) sell the <b>ATM CE and ATM PE</b>.",
         f"At the same time buy <b>OTM{wings} wings</b> on both sides (±{wings*50} pts); buys first for margin benefit. (₹2L account: OTM8 / ±400.)",
         f"Stop-loss <b>{c['legs'][0]['sl']['value']}%</b> on each sold leg; <b>trail SL to break-even (SL legs)</b> when one leg stops out.",
         f"<b>Overall SL ₹{c['overall']['sl_mtm']:,.0f}</b> per lot (MTM, candle close). No target, no re-entry.",
         f"Exit everything at <b>{c['exit_time']}</b>. Set AlgoTest “Stop monitoring after” 15:14."]
parts.append(f'<h2 id="s1">1 · The deployable strategy: Expiry-Day Iron Fly</h2>')
parts.append(card("₹2 lakh · 1 lot", tiles(m1, r1, "on ₹2,00,000")))
parts.append(card("₹3 lakh · margin-sized (2 lots only before the Nov-2024 ELM rule)", tiles(r3["metrics"], r3, "on ₹3,00,000")))
parts.append(card("Rules", "<ol>" + "".join(f"<li>{x}</li>" for x in rules) + "</ol>" + f'<details><summary>Exact engine config (JSON)</summary><pre>{E(json.dumps(c, indent=1))}</pre></details>'))

# 2 equity
sets = [{"name": "Optimised on all data (in-sample)", "short": "IS", "pts": D["equity"]["full"], "color": "var(--s1)"},
        {"name": "Walk-forward v6 (clean, blind)", "short": "WF", "pts": D["equity"]["wf6"], "color": "var(--s2)"},
        {"name": "Walk-forward v7 (refined grid)", "short": "WF7", "pts": D["equity"]["wf7"], "color": "var(--s3)"}]
pk, dd = 0, []
for d_, v in D["equity"]["full"]:
    pk = max(pk, v); dd.append([d_, v - pk])
parts.append('<h2 id="s2">2 · Equity: optimised vs honest walk-forward</h2>')
parts.append(card("Cumulative net P&amp;L, 1 lot (₹)", legend(sets) + line_svg(sets, "Equity comparison"),
                  "Walk-forward = each quarter's parameters chosen only from earlier data, then traded blind. The gap to the blue line is the optimism to expect to lose. Hover a line for values."))
parts.append(card("Drawdown (full sample, ₹)", line_svg([{"name": "Drawdown", "pts": dd, "color": "var(--neg)"}], "Drawdown", h=170, area=True, zero_top=True)))
parts.append(card("Month-on-month net P&amp;L, 1 lot (₹)", heat(r1["monthly"], r1["yearly"]), "Blue = profit, red = loss; intensity ∝ size."))
qs = r1["quarterly"]
parts.append(f'<div class="row2">{card("Quarterly (₹, 1 lot)", bar_svg([(k[2:4] + k[5:], v, f"{k}: {rs(v)}") for k, v in qs.items()], "Quarterly"))}'
             f'{card("Yearly (₹, 1 lot)", table(["Year", "Net"], [[k, sg(v)] for k, v in r1["yearly"].items()]), "Edge has shrunk after SEBI’s Nov-2024 F&amp;O rules and the Sep-2025 move to Tuesday expiry.")}</div>')

# 3 stress
parts.append('<h2 id="s3">3 · Stress tests &amp; statistical honesty</h2>')
parts.append(card("Scenarios (1 lot)", table(["Scenario", "Net P&amp;L", "Max DD", "PF"], [
    ["Base: wicks + 0.5%/fill + 1% on stops", sg(m1["net_pnl_rupees"]), rs(m1["max_drawdown_rupees"]), n2(m1["profit_factor"])],
    ["No synthetic wicks (optimistic bound)", sg(r1["nowick"]["net_pnl_rupees"]), rs(r1["nowick"]["max_drawdown_rupees"]), n2(r1["nowick"]["profit_factor"])],
    ["Slippage ×2 (1%/fill, 2% on stops, ₹0.20 min)", sg(r1["slip2"]["net_pnl_rupees"]), rs(r1["slip2"]["max_drawdown_rupees"]), n2(r1["slip2"]["profit_factor"])],
    ["Walk-forward OOS v6 (clean)", sg(w6["net"]), rs(w6["dd"]), n2(w6["pf"])],
    ["Walk-forward OOS v7 (refined grid)", sg(w7["net"]), rs(w7["dd"]), n2(w7["pf"])],
    ["Monte-Carlo drawdown 95th / 99th pct", "–", f'{rs(r1["mc95"])} / {rs(r1["mc99"])}', "–"],
    ["AlgoTest live fee (100 credits / 28 days)", "−" + rs(r1["fee"]), "–", "–"],
    ["Deflated Sharpe at 100 / 1,000 / 6,000 trials", f'{n2(D["dsr"]["100"])} / {n2(D["dsr"]["1000"])} / {n2(D["dsr"]["6000"])}', f'Sharpe {n2(D["sharpe"])} (WF {n2(D["wf_sharpe"])})', "–"]], left_cols=(0,))))
forced = sorted(D["forced"].items(), key=lambda x: int(x[0]))
parts.append(f'<div class="row2">{card("Same rules forced onto every day", table(["Trading DTE", "Days", "Net (1 lot)", "Win %"], [["<b>0 (expiry) ✔</b>" if k == "0" else k, v["days"], sg(v["net_rupees"]), pc(v["win_rate"])] for k, v in forced]), "Every non-expiry DTE loses with these rules: the expiry filter is structural.")}'
             f'{card("Biggest shock days (1 lot)", table(["Date", "Range", "Open→close", "DTE", "Strategy (traded)", "If forced"], [[dstr(r[0]), pc(r[1]), pc(r[2]), r[3] if r[3] is not None else "–", "not traded" if r[4] is None else sg(r[4]), "–" if r[5] is None else sg(r[5])] for r in D["shock"]]))}</div>')
parts.append(card("Worst 5 days (1 lot)", table(["Date", "DTE", "Net", "Stops", "Final exit"], [[dstr(w["date"]), w["tdte"], sg(w["net"]), w["stops"], f'{w["exit"]} @ {w["exit_time"]}'] for w in r1["worst"]])))

# 4 setup
sh = D["sheet"]
parts.append('<h2 id="s4">4 · AlgoTest setup (field by field)</h2>')
parts.append(card("Strategy settings", table(["AlgoTest field", "Value"], sh["settings"], left_cols=(0, 1))))
lh = list(sh["legs"][0].keys())
parts.append(card("Legs", table(lh, [[l[k] for k in lh] for l in sh["legs"]])))
parts.append(card("Overall settings", table(["Field", "Value"], sh["overall"] or [["-", "-"]], left_cols=(0, 1))))
parts.append(card("Portfolio, sizing &amp; execution", table(["Field", "Value"], sh["portfolio"], left_cols=(0, 1))))
parts.append(card("Second expiry-day strategy for ₹3L: ORB directional hedged spread", table(["#", "Position", "Type", "Strike", "SL", "Range Breakout (Underlying)"], [
    [1, "Sell", "PE", "ATM", "40%", "High of 09:16–09:31"], [2, "Buy", "PE", "OTM4", "–", "High of 09:16–09:31"],
    [3, "Sell", "CE", "ATM", "40%", "Low of 09:16–09:31"], [4, "Buy", "CE", "OTM4", "–", "Low of 09:16–09:31"]]),
    "Entry 09:16, exit 15:15, DTE 0 only, overall SL ₹2,000. Upside break → bull put spread; downside break → bear call spread."))

# 5 rejected
rej = [["<b>DTE 0</b>", "morning iron fly (v6 / v7)", f'{sg(w6["net"])} / {sg(w7["net"])}', f'{n2(w6["pf"])} / {n2(w7["pf"])}', '<span class="ok">deploy</span>']]
rej += [[b.replace("tdte", "DTE "), "morning entries (v6 grid)", sg(v["net"]) if v["n"] else "–", n2(v["pf"]) if v["n"] else "no stable config", '<span class="bad">rejected</span>'] for b, v in D["wf_other"].items()]
rej += [[b.replace("tdte", "DTE "), "afternoon entries (v7-H2)", sg(v["net"]) if v["n"] else "–", n2(v["pf"]) if v["n"] else "no stable config", '<span class="bad">rejected</span>'] for b, v in D["wf_h2"].items()]
parts.append('<h2 id="s5">5 · What was rejected, and why</h2>')
parts.append(card("Walk-forward out-of-sample by day (1 lot)", table(["Day", "Search", "Walk-forward OOS net", "OOS PF", "Decision"], rej)))
parts.append(card("Re-test of the first report's strategies", table(["Strategy", "Model", "Holdout Calmar", "Holdout PF", "Full-period net", "Full-period DD"], [[r[0], r[1], n2(r[2]), n2(r[3]), sg(r[4]), rs(r[5])] for r in D["audit"]]),
                  "The first report's P1 portfolio (holdout Calmar 11.6) does not survive realistic slippage + intra-minute wicks."))

# 7 VIX framework
fe = D["fe"]
g_ = lambda side, reg: next(x for x in fe["by_regime"] if x[0] == side and x[1] == reg)
parts.append('<h2 id="s7">7 · VIX regime / shared-capital framework, tested</h2>')
parts.append(card("Claim-by-claim", table(["Framework claim", "Evidence", "Verdict"], [
    ["Low VIX (&lt;13.5): keep selling", f'Selling on low-VIX expiry days: grid median {rs(g_("SELL","low/expiry")[3])}, {g_("SELL","low/expiry")[5]}% of configs profitable', '<span class="warn">weakest regime for selling</span>'],
    ["High VIX (&gt;16.5): switch to buying", f'ORB buying on high-VIX non-expiry days: median {rs(g_("BUY","high/non-expiry")[3])}, {g_("BUY","high/non-expiry")[5]}% profitable', '<span class="bad">rejected</span>'],
    ["Buying offsets selling losses", f'corr +{fe["synergy"]["corr_median_configs"]:.2f}; buying on selling’s 40 worst days {rs(fe["synergy"]["buy_on_those_days"])}', '<span class="bad">rejected</span>'],
    ["Wait until 09:45 / 10:15", "Plateau 09:17–09:27 (₹62k–₹106k); 09:45 → ₹7k", '<span class="bad">rejected for expiry day</span>'],
    ["Wings 100–200 pts", f'±200: {rs(fe["wing_exact"]["4"][0])} vs ±600: {rs(fe["wing_exact"]["12"][0])}', '<span class="warn">costly</span>'],
    ["Skip gap days", "₹9.3k vs ₹38.5k walk-forward", '<span class="bad">rejected</span>'],
    ["Portfolio max profit", "₹4k/₹6k cap: net ₹93k → ₹35k/₹59k", '<span class="bad">don’t cap</span>'],
    ["Portfolio max loss / 25% cash buffer / simple rules", "kept", '<span class="ok">keep</span>']], left_cols=(0, 1))))
wfe = fe["wf_eq"]
sets7 = [{"name": k, "short": k[0], "pts": v} for k, v in wfe.items()]
parts.append(card("Walk-forward of each policy (1 lot)", legend(sets7) + line_svg(sets7, "Policies") +
                  table(["Policy", "Net", "PF", "Max DD", "Trades", "Worst day", "MC-DD 95%"], [[k, sg(v["net"]), n2(v["pf"]), rs(v["dd"]), v["n"], rs(v["worst"]), rs(v["mc95"])] for k, v in fe["wf"].items()], left_cols=(0,))))
parts.append(f'<div class="row2">{card("Each side by VIX regime", table(["Side", "Regime / day", "Days", "Grid median", "Best", "% profitable"], [[r[0], r[1], r[2], sg(r[3]), sg(r[4]), f"{r[5]}%"] for r in fe["by_regime"]]))}'
             f'{card("Threshold sensitivity", table(["Policy", "Low &lt;", "High &gt;", "Net", "PF"], [[r[0], r[1], r[2], "no picks" if (r[3] == 0 and r[4] == 99) else sg(r[3]), "–" if (r[3] == 0 and r[4] == 99) else n2(r[4])] for r in fe["thresholds"]]), "A robust rule should not flip sign when the threshold moves 1 VIX point.")}</div>')
parts.append(f'<div class="row2">{card("Entry-time sweep (deployed strategy, 1 lot)", bar_svg([(t, v, f"{t}: {rs(v)} · DD {rs(d_)} · PF {p}") for t, v, d_, p in fe["entry_sweep"]], "Entry sweep", rotate=True), "Broad plateau 09:17–09:27; waiting until 09:45 removes the edge.")}'
             f'{card("Deployed strategy by VIX regime", table(["VIX prev close", "Days", "Net", "PF", "Win %", "Worst"], [[r[0], r[1], sg(r[2]), n2(r[3]), f"{r[4]}%", rs(r[5])] for r in fe["deployed_by_vix"]]))}</div>')
mw = {str(r[0]): r for r in fe["margin_by_wing"]}
parts.append(card("Wing distance vs margin vs return (expiry day, NIFTY ≈ 25,030, lot 65)", table(["Wings", "Net (1 lot)", "Max DD", "PF", "Worst day", "Margin", "% of ₹2L", "% of ₹3L"],
    [[f"±{int(w)*50}", sg(r[0]), rs(r[1]), n2(r[2]), rs(r[3]), rs(mw[w][1]) if w in mw else "–", f"{mw[w][2]}%" if w in mw else "–", f"{mw[w][3]}%" if w in mw else "–"] for w, r in fe["wing_exact"].items()])))

# 8 round 3
b = o["bootstrap"]
parts.append('<h2 id="s8">8 · Review round 3: overfitting, compounding, trend vs sideways, OI, other strategies</h2>')
parts.append(card("Is the finalised strategy overfit?", table(["Test", "Result", "Reading"], [
    ["PBO via CSCV (252 splits), v6 grid 960 configs", f'{o["pbo_v6"]["pbo"]*100:.0f}%', "Chance the in-sample best is below median out of sample"],
    ["PBO via CSCV, v7 grid 432 configs", f'{o["pbo_v7"]["pbo"]*100:.0f}%', "&lt; 50% → selection has some skill"],
    ["One-shot: v6 procedure fit on 2024 → 2025-26 once", f'{rs(o["oneshot_v6"]["test_net_2025_26"])} · PF {n2(o["oneshot_v6"]["test_pf"])} ({o["oneshot_v6"]["test_trades"]} trades)', '<span class="bad">fails</span> (picked ±200 wings)'],
    ["One-shot: v7 grid fit on 2024 → 2025-26", f'{rs(o["oneshot_v7"]["test_net_2025_26"])} · PF {n2(o["oneshot_v7"]["test_pf"])}', '<span class="warn">passes, but grid designed after v6 saw all data</span>'],
    ["Bootstrap of 117 trades", f'mean {rs(b["mean"])} (95% CI {rs(b["mean_ci95"][0])}–{rs(b["mean_ci95"][1])}); PF CI {n2(b["pf_ci95"][0])}–{n2(b["pf_ci95"][1])}', f'P(mean ≤ 0) = {b["p_mean_le_0"]*100:.1f}% (ignores selection)'],
    ["Half-year PF", " · ".join(f"{k}: {v[2]}" for k, v in o["half_years"].items()), '<span class="warn">steady decay</span>'],
    ["All 432 variants on expiry days", f'median {rs(o["grid_distribution_v7"]["median"])}, p75 {rs(o["grid_distribution_v7"]["p75"])}, max {rs(o["grid_distribution_v7"]["max"])}; {o["grid_distribution_v7"]["share_profitable"]*100:.0f}% profitable', "Expect median…p75, not the max"]], left_cols=(0, 1, 2))))
parts.append(card("Capital reuse &amp; compounding (other trader's columns)", table(["Book", "₹/yr (1 lot)", "Simple return", "CAGR 1 lot", "CAGR compounding", "Max DD comp.", "Max DD 1 lot", "Worst year", "Sharpe", "Sortino", "Calmar comp.", "Quarters +"],
    [[k, rs(m["rs_per_year_1lot"]), pc(m["simple_return_pct"]), pc(m["cagr_1lot_pct"]), pc(m["cagr_comp_pct"]), pc(m["maxdd_comp_pct"]), f'{pc(m["maxdd_1lot_pct"])} ({rs(m["maxdd_1lot_rs"])})', pc(m["worst_year_pct"]), n2(m["sharpe"]), n2(m["sortino"]), n2(m["calmar_comp"]), m["quarters_pos"]] for k, m in a9["comp"].items()], left_cols=(0,)),
    "Intraday margin is released at the close, so the same capital is reused every day. Compounding re-sizes lots daily from equity (selling by margin with a 25% buffer; buying by 2.5% risk, 5% for the ₹1L book). Full-sample numbers are optimistic."))
rg = a9["regime"]; pr = rg["predictor"]; w = rg["oi_walls"]; od = rg["oi_direction"]
parts.append(f'<div class="row2">{card("Trend vs sideways: what is known by 09:30", table(["Feature", "Median sideways", "Median trend", "Effect d"], rg["effect_sizes"]), f"Best rule learnt on 2024: <b>{E(pr['rule'])}</b> → 2024 sideways {pr['train_sideways_rate_selected']*100:.0f}% (base {pr['train_base']*100:.0f}%); 2025-26 {pr['test_sideways_rate_selected']*100:.0f}% (base {pr['test_base']*100:.0f}%). Weak.")}'
             f'{card("Does OI decide the move? (intraday)", table(["Claim", "Measured", "Verdict"], [["OI walls contain the day", f"{w['all_days_contained_pct']:.0f}% of days (expiry {w['expiry_contained_pct']:.0f}%)", '<span class="warn">coin-flip on expiry</span>'], ["Expiry pinned to max pain", f"{w['expiry_close_nearer_maxpain_than_0930_pct']:.0f}% of expiries", '<span class="bad">no pinning</span>'], ["Early OI tilt → direction", f"hit {od['oi_tilt_hit_rate_when_strong']:.0f}%, corr {od['corr_oi_tilt_vs_rest_of_day_move']:.2f}", '<span class="bad">no edge</span>'], ["PCR → direction", f"corr {od['corr_pcr_vs_rest_of_day_move']:.2f}", '<span class="bad">no edge</span>']], left_cols=(0, 1)))}</div>')
sd = a9["side"]
parts.append(card("Strangles only on predicted-sideways days (picked on 2024, tested once on 2025-26)", table(["Scope", "Filter", "2024 median", "2025-26 median", "Profitable 2025-26"], [[r["scope"], r["filter"], sg(r["train_median"]), sg(r["test_median"]), f'{r["test_share_profitable"]*100:.0f}%'] for r in sd["by_filter"]] +
    [[f'<b>{p["scope"]}: best on 2024</b>', f'{p["config"]} + {p["filter"]}', sg(p["train_net"]), f'{sg(p["test_net"])} (PF {n2(p["test_pf"])})', f'{p["test_n"]} trades'] for p in sd["picks"]])))
parts.append(card("Varsity structures &amp; the other trader's selling books (1 lot, one setting each)", table(["Strategy", "Expiry net", "PF", "2024", "2025-26", "Non-expiry net", "PF", "2024", "2025-26"],
    [[r["book"], sg(r["expiry"]["net"]), n2(r["expiry"]["pf"]), sg(r["expiry"]["net_2024"]), sg(r["expiry"]["net_2025_26"]), sg(r["non-expiry"]["net"]), n2(r["non-expiry"]["pf"]), sg(r["non-expiry"]["net_2024"]), sg(r["non-expiry"]["net_2025_26"])] for r in a9["books"]], left_cols=(0,)),
    "Calendar spreads not testable (one expiry per day in the data). The other trader's straddle_1015 “₹3.79L/yr, Sharpe 7.6” is labelled “(model)” and does not reproduce with real fills, stops and margin."))
gw, gg = D["gw"], a9["gng"]
parts.append(card("Gap-and-Go → Williams chain (implemented exactly as specified)", table(["Costs", "Trades", "Net", "PF", "Win %", "Max DD", "Gap-and-Go part", "Williams part", "GnG only net / PF / DD", "corr with fly"],
    [[k, s["trades"], sg(s["net"]), n2(s["pf"]), f'{s["win"]:.0f}%', rs(s["dd"]), f'{s["by_bot"]["gap_and_go"][0]} tr · {rs(s["by_bot"]["gap_and_go"][1])}', f'{s["by_bot"]["williams"][0]} tr · {rs(s["by_bot"]["williams"][1])}',
      f'{rs(gg[k]["net"])} / {n2(gg[k]["pf"])} / {rs(gg[k]["dd"])}' if k in gg else "–", n2(gg[k]["corr_with_fly"]) if k in gg else "–"] for k, s in gw.items()], left_cols=(0,)),
    "Not native to AlgoTest (gap filter and stand-downs need TradingView/Signals or a script). The Gap-and-Go part survives this independent test; the Williams back-up does not."))
bk = a9["basket"]
parts.append(card("Basket: iron fly + ORB directional spread (expiry days)", f'<p>Correlation of daily P&amp;L <b>{bk["corr"]:.2f}</b>. On the fly\'s 15 worst days the spread made <b>{rs(bk["spread_on_fly_worst15"])}</b> (fly {rs(bk["fly_worst15"])}). Basket with portfolio SL ₹4,000: net {rs(bk["basket"]["net_pnl_rupees"])}, max DD {rs(bk["basket"]["max_drawdown_rupees"])}, PF {n2(bk["basket"]["profit_factor"])}, worst day {rs(bk["basket"]["worst_day_rupees"])}. By year: {" · ".join(f"{k}: {rs(v)}" for k, v in bk["yearly_basket"].items())}.</p>'))
parts.append(card("Reddit comments → what was done", table(["Comment", "What was done"], [
    ["Start from a reason, not a search", "Kept economically motivated ideas only (expiry-day theta / opening IV premium; trend spreads on breakouts). The 32k-trial mass search is reported as rejected."],
    ["Split data, check once, drop instead of tweaking", "Quarterly walk-forward + one-shot 2024→2025-26. The v6 one-shot failed and is reported as such."],
    ["Judge expectancy &amp; drawdown, not win rate", "Tables lead with net, PF, max DD, Monte-Carlo DD, worst day."],
    ["Real costs &amp; slippage", "₹20/order + STT/exchange/SEBI/stamp/GST; 0.5% selling + 1% stops; buying stressed at 0.1/0.3/1.5% per side."],
    ["40 trades isn't enough", "117 expiry trades; Gap-and-Go 182; bootstrap CIs shown. Still small → paper trade."],
    ["Simple underlying signals first", "Gap-and-Go and ORB spreads use pure underlying breaks; OI/PCR signals failed on the underlying itself."],
    ["Basket should lose less when wrong", "Fly + ORB spread / Gap-and-Go: correlations ≈ 0."],
    ["Expiry-day CAS swings", "Time exit at 15:15; set AlgoTest “Stop monitoring after” to 15:14 so closing-auction prints cannot fire stops."],
    ["Paper trade first", "Forward-test 4–6 expiries on AlgoTest; Gap-and-Go 8–12 weeks."]], left_cols=(0, 1))))

# 6 validation
parts.append('<h2 id="s6">6 · Data &amp; model validation</h2>')
parts.append(f'<div class="row2">{card("Wick model vs true OHLC (Oct–Dec 2024, same days)", table(["Strategy", "True OHLC", "LTP only", "LTP + wicks"], [[r[0], f"{rs(r[1])} · {r[2]} SL", f"{rs(r[3])} · {r[4]} SL", f"{rs(r[5])} · {r[6]} SL"] for r in D["wick_validation"]], left_cols=(0,)))}'
             f'{card("Margin model vs exchange SPAN (lot 65, NIFTY 25,030)", table(["Position", "Exchange", "Model", "Error"], [[r[0], rs(r[1]), rs(r[2]), f"{(r[2]-r[1])/r[1]*100:.1f}%"] for r in D["span"]]))}</div>')
parts.append(card("How this was done", f'''<p><b>Data.</b> Kaggle NIFTY 1-minute option chains: true OHLC for 2024 (verified {D["crosscheck"]["close_exact_match_pct"]:.2f}% identical to an independent ICICI Breeze source on {D["crosscheck"]["crosscheck_rows"]:,} bars), LTP for 2025-26 with intra-minute wicks calibrated on true OHLC. India VIX from NSE. The Mendeley set (daily 2017-21) and rahultr1 (daily) were unusable for intraday; the TradyFlow notebook is a US options-flow study.</p>
<p><b>Engine.</b> Rust, 1-minute bars, AlgoTest candle convention. Leg SL/target on high/low with gap-through fills at the next open; overall SL/lock at candle close; pessimistic same-bar re-check after stops move. Costs: ₹20/order, 0.1% STT, NSE 0.03503%, SEBI, stamp, GST at today's rates and lot 65. Margin: scenario SPAN + exposure + SEBI 2% expiry-day ELM, calibrated to the exchange SPAN file. Trading-day DTE.</p>
<p><b>Search &amp; validation.</b> v1–v4 superseded; v5 32,610-trial search rejected; v6/v7 pre-declared grids with plateau selection and anchored quarterly walk-forward; v8 VIX framework; v9 overfit audit (PBO/CSCV, one-shot split, bootstrap), compounding, regime/OI study, Varsity structures, Gap-and-Go replication. Full log: EXPERIMENT_LOG.md. Research only, not investment advice.</p>'''))

CSS = '''
:root{color-scheme:light;--bg:#f6f6f4;--card:#fcfcfb;--card2:#f0efec;--bd:#e1e0d9;--tx:#0b0b0b;--tx2:#52514e;--tx3:#7a7974;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--neg:#c53a3a;--good:#0b8a0b;--warn:#a56f00}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#121211;--card:#1a1a19;--card2:#232321;--bd:#2c2c2a;--tx:#f0efec;--tx2:#c3c2b7;--tx3:#8f8e86;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--neg:#e66767;--good:#2fbf2f;--warn:#fab219}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 64px}h1{font-size:23px;margin:0 0 4px}h2{font-size:18px;margin:30px 0 8px;scroll-margin-top:12px}h3{font-size:15px;margin:0 0 8px}
.sub{color:var(--tx2);margin:0 0 8px}.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px 16px;margin:12px 0;min-width:0}
.verdict{border-left:4px solid var(--s1)}.toc a{display:inline-block;margin:4px 10px 0 0;color:var(--s1);text-decoration:none}
.row2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}.row2 .card{margin:0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.tile{background:var(--card2);border-radius:8px;padding:10px 12px}
.tile .k{color:var(--tx2);font-size:12px}.tile .v{font-size:21px;font-weight:600;font-variant-numeric:tabular-nums}.tile .s{color:var(--tx3);font-size:12px}
.tscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--bd);text-align:right;white-space:nowrap;vertical-align:top}th{color:var(--tx2);font-weight:600;font-size:12px}
td:first-child,th:first-child{text-align:left}td.l{text-align:left;white-space:normal;min-width:180px}.heat td{font-size:12px;padding:5px 6px;min-width:56px}
.neg{color:var(--neg)}.ok{color:var(--good);font-weight:600}.bad{color:var(--neg);font-weight:600}.warn{color:var(--warn);font-weight:600}
svg{display:block;max-width:100%;height:auto}svg text{fill:var(--tx2);font-size:13px}svg .lbl{fill:var(--tx);font-weight:600}svg .grid{stroke:var(--bd)}svg .zero{stroke:var(--tx3)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--tx2);margin:2px 0 6px}.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:5px}
.note{color:var(--tx2);font-size:13px;margin:8px 0 0}ol,ul{padding-left:20px;margin:6px 0}li{margin:3px 0}pre{background:var(--card2);padding:10px;border-radius:8px;overflow:auto;font-size:12px}
details summary{cursor:pointer;color:var(--tx2)}
@media print{.card{break-inside:avoid}}
'''
page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NIFTY Strategy Report</title><style>{CSS}</style></head>
<body><div class="wrap">{"".join(parts)}</div></body></html>'''
os.makedirs(f"{ROOT}/reports", exist_ok=True)
open(f"{ROOT}/reports/strategy_report.html", "w", encoding="utf-8").write(page)
print("written", len(page))
