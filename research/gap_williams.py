#!/usr/bin/env python3
"""NIFTY Gap-and-Go -> Williams chain (other trader's spec, OptionsBuyer.in), implemented exactly:

1. Opening range = highest/lowest 1-min CLOSE 09:15..09:45 (31 bars). W = high - low. Triggers: high + 0.10W / low - 0.10W.
   Checked on 1-min closes 09:46..12:00. Gap = 09:15 price vs previous day's 15:15 close; after a gap-up only the
   upside break is taken, after a gap-down only the downside. Stand down if: the opposite band breaks first
   ("opposite_first"); NIFTY already touched yesterday's 15:15 close before the break ("filled"); nothing breaks by 12:00.
2. Williams back-up: R = previous day's highest - lowest 1-min close; levels open +/- 0.5R; first 1-min close beyond
   either level from the hand-over minute to 14:29. Only after "opposite_first" or "filled", and only if |gap| < 0.2% or >= 0.5%.
3. Entry next bar after the signal: buy the 150-point ITM weekly option (CE = ATM-150, PE = ATM+150).
   Exits on premium closes, filled next bar: SL at 70% of entry; trailing: once premium has been > 105% of entry,
   exit at 80% of the highest close; time exit 15:15. One position per day.
Costs: 0.1% per side + Rs20/order brokerage + STT/exchange/SEBI/stamp/GST; stress +0.2% per side; and 1.5% per side.
Lot 65 for every year (same convention as the rest of the study).
"""
import json, os, sys
import polars as pl
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/audit_v9")
LOT = 65

lake = pl.concat([pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY_OHLC/*/*.parquet"),
                  pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY/*/*.parquet").filter(pl.col("trade_date") >= 20250101)]).filter(pl.col("expiry_rank") == 0)
spot = lake.select("trade_date", "minute_idx", "spot_open", "spot_high", "spot_low", "spot_close").unique(["trade_date", "minute_idx"]).collect().sort("trade_date", "minute_idx")
opts = lake.select("trade_date", "minute_idx", "strike", "is_call", "open", "close", "volume", "dte").collect()
days = sorted(spot["trade_date"].unique().to_list())
SP = {d: g.sort("minute_idx") for (d,), g in spot.group_by(["trade_date"])}
OP = {d: g for (d,), g in opts.group_by(["trade_date"])}


def charges(side, price, qty):
    t = price * qty
    brok = 20.0; stt = t * 0.001 if side == "S" else 0; exch = t * 0.0003503; sebi = t * 1e-6; stamp = t * 0.00003 if side == "B" else 0
    return brok + stt + exch + sebi + stamp + 0.18 * (brok + exch + sebi)


def m2t(m):
    t = 9 * 60 + 15 + m
    return f"{t // 60:02d}:{t % 60:02d}"


def run(slip):
    trades = []
    for i in range(1, len(days)):
        d, pd_ = days[i], days[i - 1]
        s, ps = SP[d], SP[pd_]
        c = s["spot_close"].to_list(); hi = s["spot_high"].to_list(); lo = s["spot_low"].to_list(); n = len(c)
        if n < 360:
            continue
        pclose1515 = ps.filter(pl.col("minute_idx") == 360)["spot_close"]
        pclose1515 = pclose1515[0] if pclose1515.len() else ps["spot_close"][-1]
        prng = max(ps["spot_close"]) - min(ps["spot_close"])
        open915 = s["spot_open"][0]
        gap = (open915 / pclose1515 - 1) * 100
        orh, orl = max(c[0:31]), min(c[0:31]); W = orh - orl
        up, dn = orh + 0.1 * W, orl - 0.1 * W
        sig, kind, status, hand = None, None, "no_break", None
        for m in range(31, 166):
            brk_up, brk_dn = c[m] > up, c[m] < dn
            if not (brk_up or brk_dn):
                continue
            want_up = gap > 0
            if (brk_up and not want_up) or (brk_dn and want_up):
                status, hand = "opposite_first", m
                break
            touched = any(lo[k] <= pclose1515 <= hi[k] for k in range(0, m + 1))
            if touched:
                status, hand = "filled", m
                break
            sig, kind, status = m, ("CE" if brk_up else "PE"), "gap_and_go"
            break
        if sig is None and status in ("opposite_first", "filled") and (abs(gap) < 0.2 or abs(gap) >= 0.5):
            lu, ld = open915 + 0.5 * prng, open915 - 0.5 * prng
            for m in range(hand, 315):  # until 14:29
                if c[m] > lu:
                    sig, kind, status = m, "CE", status + "->williams"; break
                if c[m] < ld:
                    sig, kind, status = m, "PE", status + "->williams"; break
        if sig is None or sig + 1 >= 360:
            continue
        e = sig + 1
        atm = round(c[sig] / 50) * 50
        k = atm - 150 if kind == "CE" else atm + 150
        o = OP[d].filter((pl.col("strike") == k) & (pl.col("is_call") == (kind == "CE"))).sort("minute_idx")
        if o.height < 300:
            continue
        oc = dict(zip(o["minute_idx"].to_list(), o["close"].to_list())); oo = dict(zip(o["minute_idx"].to_list(), o["open"].to_list()))
        ent_ref = oo.get(e, oc.get(sig))
        if not ent_ref:
            continue
        entry = ent_ref * (1 + slip)
        peak, armed, exit_px, reason, xm = entry, False, None, "TIME", 360
        for m in range(e, 360):
            p = oc.get(m)
            if p is None:
                continue
            peak = max(peak, p)
            if p > 1.05 * entry:
                armed = True
            stop = p <= 0.70 * entry
            trail = armed and p <= 0.80 * peak
            if stop or trail:
                nxt = oo.get(m + 1, p)
                exit_px, reason, xm = nxt * (1 - slip), ("SL" if stop else "TRAIL"), m + 1
                break
        if exit_px is None:
            exit_px = oc.get(360, oc.get(359, entry)) * (1 - slip)
        gross = (exit_px - entry) * LOT
        net = gross - charges("B", entry, LOT) - charges("S", exit_px, LOT)
        trades.append({"date": d, "type": status, "opt": kind, "strike": k, "entry_time": m2t(e), "entry": round(entry, 2), "exit_time": m2t(xm), "exit": round(exit_px, 2),
                       "reason": reason, "gap_pct": round(gap, 2), "net": round(net, 2), "dte": int(o["dte"][0])})
    return trades


def summarise(tr, label):
    pnl = [t["net"] for t in tr]
    w = sum(x for x in pnl if x > 0); l = -sum(x for x in pnl if x < 0)
    c = p = dd = 0
    for x in pnl:
        c += x; p = max(p, c); dd = max(dd, p - c)
    by = {}
    for t in tr:
        by.setdefault(t["type"].split("->")[-1], []).append(t["net"])
    yr = {}
    for t in tr:
        yr[str(t["date"] // 10000)] = yr.get(str(t["date"] // 10000), 0) + t["net"]
    s = {"label": label, "trades": len(pnl), "net": sum(pnl), "pf": w / l if l else 99, "win": sum(1 for x in pnl if x > 0) / max(1, len(pnl)) * 100, "dd": dd,
         "avg_win": w / max(1, sum(1 for x in pnl if x > 0)), "avg_loss": -l / max(1, sum(1 for x in pnl if x <= 0)),
         "by_bot": {k: [len(v), round(sum(v))] for k, v in by.items()}, "yearly": {k: round(v) for k, v in yr.items()}}
    print(f"{label:28s} trades {s['trades']:3d} net ₹{s['net']:>9,.0f} PF {s['pf']:.2f} win {s['win']:.0f}% DD ₹{s['dd']:,.0f} avgW {s['avg_win']:,.0f} avgL {s['avg_loss']:,.0f} by-bot {s['by_bot']} yearly {s['yearly']}")
    return s


res = {}
for slip, lab in ((0.001, "spec costs (0.1%/side)"), (0.003, "stress (+0.2%/side)"), (0.015, "realistic buying 1.5%/side")):
    tr = run(slip)
    res[lab] = {"summary": summarise(tr, lab), "trades": tr}
json.dump(res, open(f"{OUT}/gap_williams.json", "w"), default=str)
