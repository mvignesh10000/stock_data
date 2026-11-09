#!/usr/bin/env python3
"""Static (JavaScript-free) HTML report for Strategy B -> reports/strategy_b.html
Inputs: results/v12/res.json (5-year daily P&L, id 11 = Strategy B base), results/v12/stress.json, results/v11/all.json.
Hover detail uses native SVG <title> tooltips; every chart has a table view. Light/dark via prefers-color-scheme.
"""
import collections, datetime as dt, html, json, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reports/strategy_b.html")
res = {r["id"]: r for r in json.load(open(f"{ROOT}/results/v12/res.json"))["results"]}
daily = [(int(d[0]), d[1]) for d in res[11]["daily"]]
stress = json.load(open(f"{ROOT}/results/v12/stress.json"))["B"]
v11 = json.load(open(f"{ROOT}/results/v11/all.json"))
blk = next(r for r in v11 if r["fam"] == "F1" and list(r["key"]) == ["09:20", 50, 3, 3000, "sl_legs"])
CAP = 500000
POS, NEG, MID = "#2a78d6", "#e34948", "#f0efec"
POS_D, NEG_D, MID_D = "#3987e5", "#e66767", "#383835"


def rs(x, sign=False):
    s = f"{abs(x):,.0f}"
    # Indian grouping
    n = f"{abs(int(round(x)))}"
    if len(n) > 3:
        head, tail = n[:-3], n[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        s = head + "," + tail
    else:
        s = n
    sg = ("+" if x > 0 else "−" if x < 0 else "") if sign else ("−" if x < 0 else "")
    return f"{sg}₹{s}"


def d2(d):
    return dt.date(d // 10000, d // 100 % 100, d % 100)


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


# ---------------------------------------------------------------- series
eq, peak, cum, dds = 0.0, 0.0, [], []
for d, n in daily:
    eq += n
    peak = max(peak, eq)
    cum.append((d, eq))
    dds.append((d, eq - peak))
months = collections.OrderedDict()
years = collections.OrderedDict()
for d, n in daily:
    months[d // 100] = months.get(d // 100, 0) + n
    years[d // 10000] = years.get(d // 10000, 0) + n
trades = [n for _, n in daily if n]
base = stress["base"]


# ---------------------------------------------------------------- SVG helpers
def line_chart(points, w=920, h=280, area=False, label="", fmt=rs):
    xs = [d2(d).toordinal() for d, _ in points]
    ys = [v for _, v in points]
    x0, x1 = min(xs), max(xs)
    lo, hi = min(0, min(ys)), max(0, max(ys))
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - (pad if area else 0), hi + pad
    L, R, T, B = 70, 16, 14, 30
    X = lambda x: L + (x - x0) / (x1 - x0) * (w - L - R)
    Y = lambda y: T + (hi - y) / (hi - lo) * (h - T - B)
    step = 10 ** math.floor(math.log10((hi - lo) / 4))
    step = next(s * step for s in (1, 2, 2.5, 5, 10) if (hi - lo) / (s * step) <= 6)
    g = []
    v = math.ceil(lo / step) * step
    while v <= hi:
        g.append(f'<line class="grid" x1="{L}" x2="{w - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                 f'<text class="tick" x="{L - 8}" y="{Y(v) + 4:.1f}" text-anchor="end">{fmt(v)}</text>')
        v += step
    for yr in range(d2(points[0][0]).year + 1, d2(points[-1][0]).year + 1):
        xx = X(dt.date(yr, 1, 1).toordinal())
        g.append(f'<line class="grid" x1="{xx:.1f}" x2="{xx:.1f}" y1="{T}" y2="{h - B}"/><text class="tick" x="{xx:.1f}" y="{h - 10}" text-anchor="middle">{yr}</text>')
    pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(xs, ys))
    shape = (f'<polygon class="area" points="{X(xs[0]):.1f},{Y(0):.1f} {pts} {X(xs[-1]):.1f},{Y(0):.1f}"/>' if area else "") + f'<polyline class="ln" points="{pts}"/>'
    # hover targets: one per month (native tooltip)
    hit, bym = [], collections.OrderedDict()
    for (d, v), x in zip(points, xs):
        bym[d // 100] = (d, v, x)
    keys = list(bym)
    for i, k in enumerate(keys):
        d, v, x = bym[k]
        xa = X(bym[keys[i - 1]][2]) if i else L
        xb = X(x)
        hit.append(f'<rect class="hit" x="{xa:.1f}" y="{T}" width="{max(1, xb - xa):.1f}" height="{h - T - B}"><title>{d2(d):%b %Y} · {label}: {fmt(v)}</title></rect>')
    base_l = f'<line class="base" x1="{L}" x2="{w - R}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>'
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(label)}">{"".join(g)}{base_l}{shape}{"".join(hit)}</svg>'


def year_bars(w=920, h=250):
    ks, vs = list(years), list(years.values())
    lo, hi = min(0, min(vs)), max(vs)
    L, R, T, B = 70, 16, 22, 44
    span = hi - lo
    Y = lambda y: T + (hi - y) / span * (h - T - B)
    bw = (w - L - R) / len(ks)
    out = []
    for i, (k, v) in enumerate(zip(ks, vs)):
        x = L + i * bw + bw * 0.25
        y0, y1 = sorted((Y(0), Y(v)))
        cls = "pos" if v >= 0 else "neg"
        note = " (6 weeks)" if k == 2021 else " (to 3 Nov)" if k == 2026 else ""
        out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y0:.1f}" width="{bw * 0.5:.1f}" height="{max(1, y1 - y0):.1f}" rx="4"><title>{k}{note}: {rs(v, True)}</title></rect>')
        ty = (y0 - 6) if v >= 0 else (y1 + 14)
        out.append(f'<text class="val" x="{x + bw * 0.25:.1f}" y="{ty:.1f}" text-anchor="middle">{rs(v, True)}</text>'
                   f'<text class="tick" x="{x + bw * 0.25:.1f}" y="{h - 8}" text-anchor="middle">{k}{"*" if note else ""}</text>')
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Net P&amp;L by year"><line class="base" x1="{L}" x2="{w - R}" y1="{Y(0):.1f}" y2="{Y(0):.1f}"/>{"".join(out)}</svg>'


def month_table():
    mx = max(abs(v) for v in months.values())
    rows = []
    for y in sorted({k // 100 for k in months}):
        cells = []
        for m in range(1, 13):
            k = y * 100 + m
            if k not in months:
                cells.append('<td class="na">·</td>')
                continue
            v = months[k]
            t = min(1, abs(v) / (mx * 0.8))
            lvl = 0 if abs(v) < 1 else 1 + min(2, int(t * 3))
            cls = ("p" if v > 0 else "n") + str(lvl) if lvl else "z"
            cells.append(f'<td class="{cls}" title="{dt.date(y, m, 1):%b %Y}: {rs(v, True)}">{rs(v, True) if abs(v) >= 1 else "0"}</td>')
        rows.append(f"<tr><th>{y}</th>{''.join(cells)}<td class='tot'>{rs(years[y], True)}</td></tr>")
    head = "".join(f"<th>{dt.date(2000, m, 1):%b}</th>" for m in range(1, 13))
    return f'<table class="heat"><thead><tr><th></th>{head}<th>Year</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'


# ---------------------------------------------------------------- tables
def g(k, f):
    return (blk[k] or {}).get(f, 0)


oos = "".join(f"<tr><td>{lab}</td><td>{note}</td><td class='num'>{g(k, 'trades')}</td><td class='num'>{rs(g(k, 'net'), True)}</td><td class='num'>{g(k, 'pf'):.2f}</td>"
              f"<td class='num'>{rs(g(k, 'dd'))}</td><td class='num'>{g(k, 'win_months_pct'):.0f}%</td></tr>"
              for k, lab, note in (("old", "Nov 2021 – Dec 2023", "never looked at before the test"),
                                   ("sel", "Jan 2024 – Mar 2026", "period earlier rounds studied"),
                                   ("new", "Mar 2026 – Nov 2026", "holdout, untouched until the test")))
order = ["base", "slippage x2", "close-based stops", "entry 09:17", "entry 09:25", "wings Rs 2", "wings Rs 5",
         "leg SL 40%", "leg SL 60%", "overall SL 2500", "overall SL 3500"]
lab = {"base": "Strategy B as specified", "slippage x2": "Slippage doubled (1 %/fill, 2 % on stops)", "close-based stops": "Stops on 1-min close (+1.5× hard stop)",
       "entry 09:17": "Entry 09:17", "entry 09:25": "Entry 09:25", "wings Rs 2": "Wings ~₹2", "wings Rs 5": "Wings ~₹5",
       "leg SL 40%": "Leg stop 40 %", "leg SL 60%": "Leg stop 60 %", "overall SL 2500": "Overall stop ₹2,500", "overall SL 3500": "Overall stop ₹3,500"}
st_rows = "".join(f"<tr{' class=hl' if k == 'base' else ''}><td>{lab[k]}</td><td class='num'>{rs(stress[k]['net'], True)}</td><td class='num'>{rs(stress[k]['per_year'], True)}</td>"
                  f"<td class='num'>{stress[k]['pf']:.2f}</td><td class='num'>{rs(stress[k]['max_dd'])}</td><td class='num'>{stress[k]['win_months_pct']:.0f}%</td>"
                  f"<td class='num'>{rs(stress[k]['years'].get('2023', 0), True)}</td></tr>" for k in order)
size_rows = "".join(f"<tr><td>{n} lot{'s' if n > 1 else ''}</td><td class='num'>~₹{1.6 * n:.1f}L</td><td class='num'>{stress[f'{n}lot_on_5L']['ann_pct_on_5L']:.1f}%</td>"
                    f"<td class='num'>{rs(stress[f'{n}lot_on_5L']['max_dd'])} ({stress[f'{n}lot_on_5L']['max_dd_pct_5L']:.1f}%)</td>"
                    f"<td class='num'>{rs(stress[f'{n}lot_mc_dd']['p95'])} ({stress[f'{n}lot_mc_dd']['p95'] / CAP * 100:.1f}%)</td>"
                    f"<td class='num'>{rs(stress[f'{n}lot_on_5L']['worst_day'])}</td></tr>" for n in (1, 2))
eq_table = "".join(f"<tr><td>{dt.date(k // 100, k % 100, 1):%b %Y}</td><td class='num'>{rs(v, True)}</td></tr>" for k, v in months.items())

tiles = [("Net per year (1 lot)", rs(base["per_year"]), f"{rs(base['net'])} over 5 years"),
         ("Profit factor", f"{base['pf']:.2f}", f"{base['trades']} trades, {base['win_rate']:.0f}% winning days"),
         ("Winning months", f"{base['win_months_pct']:.0f}%", f"longest losing run {base['max_losing_month_streak']} months"),
         ("Max drawdown", rs(base["max_dd"]), f"{base['max_dd'] / CAP * 100:.1f}% of ₹5L · bad case {rs(stress['1lot_mc_dd']['p95'])}"),
         ("Worst day / month", rs(base["worst_day"]), f"worst month {rs(base['worst_month'])}")]
tiles_html = "".join(f'<div class="tile"><div class="tl">{a}</div><div class="tv">{b}</div><div class="ts">{c}</div></div>' for a, b, c in tiles)

css = f"""
:root{{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
--s1:{POS};--pos:{POS};--neg:{NEG};--mid:{MID};
--p1:{blend(MID, POS, .35)};--p2:{blend(MID, POS, .65)};--p3:{POS};--n1:{blend(MID, NEG, .35)};--n2:{blend(MID, NEG, .65)};--n3:{NEG};}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--s1:{POS_D};--pos:{POS_D};--neg:{NEG_D};--mid:{MID_D};--p1:{blend(MID_D, POS_D, .35)};--p2:{blend(MID_D, POS_D, .65)};--p3:{POS_D};--n1:{blend(MID_D, NEG_D, .35)};--n2:{blend(MID_D, NEG_D, .65)};--n3:{NEG_D};}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--page);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:28px 16px 64px}}
h1{{font-size:28px;line-height:1.2;margin:0 0 6px}}h2{{font-size:19px;margin:36px 0 10px}}p.lead{{color:var(--ink2);margin:0 0 20px;max-width:760px}}
.card{{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px 18px;margin:12px 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.tile{{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px}}
.tl{{color:var(--ink2);font-size:13px}}.tv{{font-size:26px;font-weight:650;margin:2px 0}}.ts{{color:var(--muted);font-size:12.5px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--grid);vertical-align:top}}
th{{color:var(--ink2);font-weight:600}}td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
tr.hl td{{font-weight:650}}
.scroll{{overflow-x:auto}}
.heat td,.heat th{{text-align:right;font-variant-numeric:tabular-nums;font-size:12.5px;padding:6px 5px;border:2px solid var(--surface);white-space:nowrap}}
.heat td.p1{{background:var(--p1)}}.heat td.p2{{background:var(--p2)}}.heat td.p3{{background:var(--p3);color:#fff}}
.heat td.n1{{background:var(--n1)}}.heat td.n2{{background:var(--n2)}}.heat td.n3{{background:var(--n3);color:#fff}}
.heat td.z{{background:var(--mid)}}.heat td.na{{color:var(--muted);text-align:center}}.heat td.tot{{font-weight:650}}
svg{{width:100%;height:auto;display:block}}
svg .grid{{stroke:var(--grid);stroke-width:1}}svg .base{{stroke:var(--axis);stroke-width:1.5}}
svg .tick{{fill:var(--muted);font-size:11.5px;font-variant-numeric:tabular-nums}}svg .val{{fill:var(--ink2);font-size:12px;font-weight:600}}
svg .ln{{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round}}svg .area{{fill:var(--neg);opacity:.18}}
.dd svg .ln{{stroke:var(--neg)}}svg .pos{{fill:var(--pos)}}svg .neg{{fill:var(--neg)}}
svg .hit{{fill:transparent}}svg .hit:hover{{fill:var(--ink);opacity:.06}}
details{{margin-top:8px}}summary{{cursor:pointer;color:var(--ink2);font-size:13.5px}}
.key{{display:flex;gap:14px;flex-wrap:wrap;color:var(--ink2);font-size:13px;margin:6px 0 0}}.sw{{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:5px}}
ol,ul{{padding-left:20px}}li{{margin:4px 0}}.warn{{border-left:3px solid var(--neg)}}.muted{{color:var(--muted);font-size:13px}}
code{{font-size:13px;background:var(--mid);padding:1px 5px;border-radius:4px}}
"""

body = f"""
<main>
<h1>Strategy B: NIFTY expiry-day iron fly</h1>
<p class="lead">Sell the ATM straddle on NIFTY's weekly expiry day, buy ~₹3 wings, fixed stops, out by 15:15. Five years of true exchange
1-minute data (Nov 2021 – Nov 2026), today's costs, one lot (65 qty). A modest, tested edge, with the limits spelled out below.</p>
<div class="tiles">{tiles_html}</div>

<h2>Rules</h2>
<div class="card scroll"><table>
<tr><th>Day</th><td>NIFTY weekly <b>expiry day only</b> (Tuesday; Thursday before Sep 2025; previous trading day if a holiday)</td></tr>
<tr><th>Entry</th><td><b>09:20</b> IST (AlgoTest: close of the 09:19 candle). Automate it: 3–5 minutes off cost 35–45 % of the profit</td></tr>
<tr><th>Legs</th><td>BUY the CE and PE whose premium is <b>closest to ₹3</b> (wings first) · SELL <b>ATM CE</b> + <b>ATM PE</b></td></tr>
<tr><th>Leg stop</th><td><b>50 %</b> above each short leg's entry (SL-limit at the exchange)</td></tr>
<tr><th>After a stop</th><td>move the other short leg's stop to its entry price (trail to breakeven)</td></tr>
<tr><th>Overall stop</th><td><b>₹3,000 per lot</b> MTM: exit everything</td></tr>
<tr><th>Exit</th><td><b>15:15</b>, shorts first, then wings. No re-entry, no target</td></tr>
<tr><th>Orders</th><td>limit orders with an 8 % buffer, re-priced every 3 s (market orders are not allowed for API algos)</td></tr>
<tr><th>Margin</th><td>about ₹1.6L per lot on expiry day (SPAN + exposure + 2 % expiry ELM)</td></tr>
<tr><th>AlgoTest</th><td>Weekly, DTE 0, 09:20 → 15:15 · Sell CE ATM SL 50 % · Sell PE ATM SL 50 % · Buy CE closest premium 3 · Buy PE closest premium 3 ·
Square-off partial · Trail SL to break-even: SL legs · Overall SL MTM ₹3,000</td></tr>
<tr><th>Executor</th><td><code>python execution/upstox_ironfly.py NIFTY</code> (paper by default; <code>--live</code> with a daily Upstox token on your static-IP machine)</td></tr>
</table></div>

<h2>Equity curve (1 lot, cumulative net ₹)</h2>
<div class="card">{line_chart(cum, label="cumulative net")}
<details><summary>Table view: net P&amp;L by month</summary><div class="scroll"><table><tr><th>Month</th><th class="num">Net</th></tr>{eq_table}</table></div></details></div>

<h2>Drawdown from the running peak</h2>
<div class="card dd">{line_chart(dds, h=200, area=True, label="drawdown")}
<p class="muted">Deepest: {rs(base['max_dd'])} (during 2023). Bootstrap over 5 000 reshuffled histories: median {rs(stress['1lot_mc_dd']['median'])}, 95th percentile {rs(stress['1lot_mc_dd']['p95'])}, 99th {rs(stress['1lot_mc_dd']['p99'])}.</p></div>

<h2>Net P&amp;L by year</h2>
<div class="card">{year_bars()}<div class="key"><span><span class="sw" style="background:var(--pos)"></span>profit</span><span><span class="sw" style="background:var(--neg)"></span>loss</span><span>* partial year</span></div></div>

<h2>Monthly P&amp;L</h2>
<div class="card scroll">{month_table()}
<div class="key"><span><span class="sw" style="background:var(--p3)"></span>larger profit</span><span><span class="sw" style="background:var(--p1)"></span>small profit</span><span><span class="sw" style="background:var(--n1)"></span>small loss</span><span><span class="sw" style="background:var(--n3)"></span>larger loss</span><span>· no data</span></div></div>

<h2>Out-of-sample evidence</h2>
<div class="card scroll"><table><tr><th>Period</th><th>Role</th><th class="num">Trades</th><th class="num">Net</th><th class="num">PF</th><th class="num">Max DD</th><th class="num">Win months</th></tr>{oos}</table>
<p class="muted">The rules were chosen as the region that is positive in every block (see the experiment log), so the blocks are not a
textbook single holdout. The two blocks outside 2024-26 are the cleanest evidence.</p></div>

<h2>Stress tests (5 years, 1 lot)</h2>
<div class="card scroll"><table><tr><th>Variant</th><th class="num">Net</th><th class="num">Per year</th><th class="num">PF</th><th class="num">Max DD</th><th class="num">Win months</th><th class="num">2023</th></tr>{st_rows}</table>
<p class="muted">Every variant stays at PF ≥ 1.29, so there is no cliff next to the chosen settings. Timing is the most sensitive input.</p></div>

<h2>Sizing on ₹5L</h2>
<div class="card scroll"><table><tr><th>Size</th><th class="num">Margin</th><th class="num">Return / yr</th><th class="num">Max DD (5 y)</th><th class="num">Bad-case DD (95 %)</th><th class="num">Worst day</th></tr>{size_rows}</table>
<p class="muted">Start with 1 lot. Move to 2 only after live results track the backtest.</p></div>

<h2>Limits</h2>
<div class="card warn"><ol>
<li><b>Small edge.</b> Expectancy about ₹{base['net'] / base['trades']:.0f} per trade against a worst day of {rs(base['worst_day'])}; with doubled slippage the yearly result falls to about {rs(stress['slippage x2']['per_year'])} per lot.</li>
<li><b>Losing years happen.</b> 2023 (record-low VIX, thin premiums) lost {rs(abs(years[2023]))}; losing runs of 3 months occurred.</li>
<li><b>NIFTY-specific.</b> The same rules lost on SENSEX (PF 1.1 in 2023-24, 0.6-0.8 since Oct 2024). Treat it as a NIFTY effect, not a law.</li>
<li><b>≥ 85 % winning months is not reachable</b> with 4-5 trades a month; nothing tested exceeded about 64 %.</li>
<li><b>Backtest ≠ live.</b> Fills, latency, rule changes (lot size, ELM, expiry day, settlement) can erase a small edge. Paper-trade first.</li>
</ol></div>

<h2>Going live</h2>
<div class="card"><ol>
<li><b>Paper, 8 expiries</b> on your static-IP machine; average entry slippage must stay below ~1 %.</li>
<li><b>1 lot live for 3 months</b> (normal daily Upstox token; check the SEBI algo-ID requirement).</li>
<li><b>2 lots</b> only if live PF ≥ 1.2 over ≥ 12 expiries.</li>
</ol>
<b>Stop and re-evaluate if:</b> drawdown from peak exceeds ₹40,000 per lot · 4 losing months in a row · average slippage above 2 % per fill over 8 expiries · an exchange rule change touches expiry day.</div>

<h2>Data and method</h2>
<div class="card"><ul>
<li>NIFTY weekly options, 1,230 trading days / 259 expiry days, true exchange 1-minute OHLC: Dhan (2021-11 – 2024-09), Breeze (2024-01 – 09), Upstox (2024-10 – 2026-11). Sources agree on overlaps (closes within 1 % on 98 % of minutes, identical expiry dates).</li>
<li>Costs at today's rates: brokerage ₹20/order, STT 0.15 % on sells, exchange, SEBI, stamp, 18 % GST. Slippage 0.5 % per fill (min ₹0.10) plus 1 % on stop fills. Stops checked pessimistically on intrabar highs. Lot held at 65 in every year.</li>
<li>Rejected along the way: other fly settings selected on 2024-26 (failed both tests), short strangles, breakout and momentum buying, pre-expiry straddles, ORB spreads, calendar spreads (PF 0.36-0.88 everywhere), VIX switching, SENSEX.</li>
<li>Scripts: <code>research/v11_discover.py</code>, <code>research/v12_stress.py</code>, <code>research/v13_calendar.py</code>; log: <code>EXPERIMENT_LOG.md</code>; rules: <code>STRATEGY_CARD.md</code>.</li>
</ul><p class="muted">Generated {dt.date.today():%d %b %Y} by research/report_strategy_b.py. Not investment advice; past results do not guarantee future returns.</p></div>
</main>"""

page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Strategy B: NIFTY Iron Fly</title><style>{css}</style></head><body>{body}</body></html>"""
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write(page)
print("wrote", OUT, len(page) // 1024, "KB")
