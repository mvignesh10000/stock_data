#!/usr/bin/env python3
"""v13: NIFTY expiry-day calendar straddle vs. plain short straddle, 5 years (2021-11 .. 2026-11).

Calendar: at entry sell current-week (rank 0) ATM CE+PE, buy next-week (rank 1) ATM CE+PE, same strike, 1:1, 1 lot (65).
Control: the same rules without the next-week legs (plain short straddle), to measure what the long legs add.
Pre-declared grid: entry {09:20, 10:30} x overall MTM stop {2000, 3000, none} x front-leg stop {none, 50 %}.
When a front short is stopped, its paired back long is closed at the same minute. Exit 15:15.
Execution model = the Rust engine's: AlgoTest times (HH:MM = close of the bar starting a minute earlier), slippage
0.5 % per fill (min Rs 0.10), stop fills at max(trigger, bar open) + 1 % + slippage, pessimistic intrabar stops on highs,
overall MTM on 1-min closes; costs at today's rates (brokerage Rs 20/order, STT 0.15 % on sells, NSE 0.03503 %,
SEBI 0.0001 %, stamp 0.003 % on buys, GST 18 %).
Caveat: 2021-11..2024-09 next-week data comes from Dhan's ATM+/-3 band; if spot moves > ~150 pts the back leg's price
is forward-filled (stale), which understates the hedge, so those years are conservative for the calendar.
Writes results/v13/calendar.json
"""
import collections, itertools, json, math, os
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/v13")
os.makedirs(OUT, exist_ok=True)
LOT, CAP = 65, 500000
SRC = ["NIFTY_UPX", "NIFTY_OHLC", "NIFTY_DHAN"]  # precedence


def idx(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m - 555 - 1


def charges(side, price, qty=LOT):
    t = price * qty
    brok, exch, sebi = 20.0, t * 0.0003503, t * 1e-6
    stt = t * 0.0015 if side == "S" else 0.0
    stamp = t * 0.00003 if side == "B" else 0.0
    return brok + stt + exch + sebi + stamp + 0.18 * (brok + exch + sebi)


def slip(p):
    return max(0.005 * p, 0.10)


def load_days():
    """{trade_date: {(rank, strike, is_call): {minute: (open, high, close)}}, spot{minute}} for expiry days, one source per day."""
    seen, days = set(), {}
    for src in SRC:
        lf = pl.scan_parquet(f"{ROOT}/data/parquet/{src}/*/*.parquet")
        exp = lf.filter((pl.col("expiry_rank") == 0) & (pl.col("trade_date") == pl.col("expiry_date"))).select("trade_date").unique().collect()["trade_date"].to_list()
        exp = [d for d in exp if d not in seen]
        if not exp:
            continue
        x = lf.filter(pl.col("trade_date").is_in(exp) & (pl.col("expiry_rank") <= 1)).select(
            "trade_date", "expiry_rank", "minute_idx", "strike", "is_call", "open", "high", "close", "spot_close").collect()
        have1 = set(x.filter(pl.col("expiry_rank") == 1)["trade_date"].unique().to_list())
        for (d,), g in x.group_by(["trade_date"]):
            if d not in have1:
                continue
            bars = collections.defaultdict(dict)
            for r, m, k, c, o, h, cl in g.select("expiry_rank", "minute_idx", "strike", "is_call", "open", "high", "close").iter_rows():
                bars[(r, k, c)][m] = (o, h, cl)
            sp = dict(g.select("minute_idx", "spot_close").unique("minute_idx").iter_rows())
            days[d] = (bars, sp)
            seen.add(d)
        print(src, "expiry days with next-week data:", sum(1 for d in exp if d in days), flush=True)
    return days


_FILLED = {}


def bar(bars, key, m):
    """bar at minute m, else the last earlier bar's close (forward fill within the day) as (c, c, c)."""
    ck = (id(bars), key)
    arr = _FILLED.get(ck)
    if arr is None:
        b = bars.get(key)
        if not b:
            return None
        arr, last = [None] * 375, None
        for mm in range(375):
            if mm in b:
                arr[mm] = b[mm]
                last = b[mm][2]
            elif last is not None:
                arr[mm] = (last, last, last)
        _FILLED[ck] = arr
    return arr[m] if 0 <= m < 375 else None


def sim(bars, sp, entry, osl, fsl, calendar):
    me, mx = idx(entry), idx("15:15")
    s = sp.get(me)
    if s is None:
        return None
    k = int(round(s / 50) * 50)
    legs = {("F", c): (0, k, c) for c in (True, False)}
    if calendar:
        legs.update({("B", c): (1, k, c) for c in (True, False)})
    pos, cost = {}, 0.0
    for lg, key in legs.items():
        b = bar(bars, key, me)
        if b is None or b[2] <= 0:
            return None
        p = b[2]
        if lg[0] == "F":
            fill = max(p - slip(p), 0.05)
            cost += charges("S", fill)
        else:
            fill = p + slip(p)
            cost += charges("B", fill)
        pos[lg] = {"key": key, "entry": fill, "exit": None}
    sign = {"F": -1, "B": 1}

    def close_leg(lg, price):
        nonlocal cost
        p = pos[lg]
        if lg[0] == "F":
            fill = price + slip(price)
            cost += charges("B", fill)
        else:
            fill = max(price - slip(price), 0.05)
            cost += charges("S", fill)
        p["exit"] = fill

    for m in range(me + 1, mx + 1):
        # front-leg stops (pessimistic: intrabar high)
        if fsl:
            for c in (True, False):
                lg = ("F", c)
                if pos[lg]["exit"] is None:
                    b = bar(bars, pos[lg]["key"], m)
                    trg = pos[lg]["entry"] * (1 + fsl / 100)
                    if b and b[1] >= trg:
                        base = max(trg, b[0]) * 1.01
                        close_leg(lg, base)
                        if ("B", c) in pos and pos[("B", c)]["exit"] is None:
                            bb = bar(bars, pos[("B", c)]["key"], m)
                            close_leg(("B", c), bb[2] if bb else pos[("B", c)]["entry"])
        mtm = 0.0
        for lg, p in pos.items():
            if p["exit"] is not None:
                mtm += sign[lg[0]] * (p["exit"] - p["entry"]) * LOT
            else:
                b = bar(bars, p["key"], m)
                mtm += sign[lg[0]] * ((b[2] if b else p["entry"]) - p["entry"]) * LOT
        if all(p["exit"] is not None for p in pos.values()):
            break
        if (osl and mtm <= -osl) or m == mx:
            for lg, p in pos.items():
                if p["exit"] is None:
                    b = bar(bars, p["key"], m)
                    close_leg(lg, b[2] if b else p["entry"])
            break
    gross = sum(sign[lg[0]] * (p["exit"] - p["entry"]) * LOT for lg, p in pos.items())
    return gross - cost


def stats(s):
    s = sorted(s)
    eq = peak = CAP
    dd = 0.0
    m, y = collections.defaultdict(float), collections.defaultdict(float)
    for d, n in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        m[d // 100] += n
        y[d // 10000] += n
    tr = [n for _, n in s]
    gw, gl = sum(x for x in tr if x > 0), -sum(x for x in tr if x < 0)
    mv = list(m.values())
    return {"trades": len(tr), "net": round(eq - CAP), "pf": round(gw / gl, 2) if gl else 0, "dd": round(dd), "worst": round(min(tr)),
            "win_months": round(sum(v > 0 for v in mv) / len(mv) * 100, 1), "years": {k: round(v) for k, v in sorted(y.items())}}


BLOCKS = {"OLD 21-23": (20211115, 20231231), "SEL 24-26": (20240101, 20260324), "NEW 26": (20260325, 20991231)}


def main():
    days = load_days()
    print("expiry days loaded:", len(days))
    res = {}
    for cal, entry, osl, fsl in itertools.product([True, False], ["09:20", "10:30"], [2000, 3000, 0], [0, 50]):
        s = [(d, r) for d, (b, sp) in sorted(days.items()) if (r := sim(b, sp, entry, osl, fsl, cal)) is not None]
        name = f"{'calendar' if cal else 'straddle'} {entry} osl{osl or '-'} fsl{fsl or '-'}"
        st = {"all": stats(s), **{k: stats([t for t in s if a <= t[0] <= b]) for k, (a, b) in BLOCKS.items()}}
        res[name] = {"stats": st, "daily": s}
        a = st["all"]
        print(f"{name:34s} n{a['trades']:>4} net {a['net']:>8} pf {a['pf']:.2f} dd {a['dd']:>6} worst {a['worst']:>6} winM {a['win_months']:>5}% | "
              + " | ".join(f"{k} pf {st[k]['pf']:.2f}" for k in BLOCKS), flush=True)
    json.dump({k: v["stats"] for k, v in res.items()}, open(f"{OUT}/calendar.json", "w"), indent=1)
    json.dump({k: v["daily"] for k, v in res.items()}, open(f"{OUT}/calendar_daily.json", "w"))


if __name__ == "__main__":
    main()
