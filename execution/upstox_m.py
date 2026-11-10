#!/usr/bin/env python3
"""Strategy M executor: NIFTY overnight momentum premium (see STRATEGY_M_CARD.md). PAPER by default; --live sends orders.

Run once per trading day at 09:12 IST (cron / Task Scheduler); it stays up until about 15:25:
  * position open from the previous day -> exit at 09:20 (short leg first, then the wing), write the ledger, clear the state
  * 09:20  -> record NIFTY spot (the reference for today's signal); a restart later in the day recovers it from 1-min candles
  * 15:19:30 -> r = spot / spot(09:20) - 1
        r > +THR  and (ALIGN off or spot > close 5 trading days ago)  -> BUY PE WING_PCT below ATM, then SELL ATM PE
        r < -THR  and (ALIGN off or spot < close 5 trading days ago)  -> BUY CE WING_PCT above ATM, then SELL ATM CE   (unless --legs up)
     contract: nearest weekly expiry after today; product "D" (carry-forward); orders are limits with a price buffer
  * no stop overnight: the wing is the stop. Never holds a position through the day session.
State: data/upstox/m_state_<account>.json; ledger data/upstox/m_ledger_<account>.csv; log data/upstox/m_<account>.log.
Kill-switch: live drawdown > KILL_DD per lot, or the last 12 months of live trading negative (needs >= 6 months) -> no new entries.
Requirements: a normal daily Upstox token for --live (static IP); the extended read-only token works for paper mode.
Usage: python execution/upstox_m.py [--lots 1] [--account acct1] [--legs both|up] [--no-align] [--live]
       paper tests: --now-entry up|dn (enter immediately)   --exit-now (exit the stored position immediately)
"""
import argparse, datetime as dt, json, os, sys, urllib.parse, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "etl"))
import upstox_ironfly as X  # Broker, fill_limit, log, now, wait_until
from upstox_backfill import get, token, IDX, LAKE  # noqa: E402

THR, WING_PCT, REF, SIGNAL, EXIT = 0.30, 0.03, "09:20", "15:19", "09:20"
KILL_DD = 90000.0
NIFTY = IDX["NIFTY"]


def holidays():
    hol = (get("/v2/market/holidays") or {}).get("data", [])
    return {h["date"] for h in hol if "NFO" in (h.get("closed_exchanges") or [])}


def candle_close(hhmm):
    """Close of today's 1-min NIFTY candle that ends at hhmm (e.g. '09:20' -> the 09:19 candle), or None."""
    r = get(f"/v3/historical-candle/intraday/{urllib.parse.quote(NIFTY, safe='')}/minutes/1") or {}
    t = (dt.datetime.combine(X.now().date(), dt.time(int(hhmm[:2]), int(hhmm[3:]))) - dt.timedelta(minutes=1)).strftime("%H:%M")
    for c in (r.get("data") or {}).get("candles", []):
        if c[0][11:16] == t:
            return float(c[4])
    return None


def close_5d_ago():
    """NIFTY daily close 5 trading days before today (the backtest uses the 15:19 print; the daily close is within a few points)."""
    today = X.now().date()
    r = get(f"/v3/historical-candle/{urllib.parse.quote(NIFTY, safe='')}/days/1/{today - dt.timedelta(days=1)}/{today - dt.timedelta(days=20)}") or {}
    cl = sorted((c[0][:10], float(c[4])) for c in (r.get("data") or {}).get("candles", []) if c[0][:10] < today.isoformat())
    return cl[-5][1] if len(cl) >= 5 else None


def margin_ok(legs, lot, want, log):
    """Largest lot count <= want that fits available funds (x1.10 buffer); keeps `want` if the APIs are unavailable (paper / extended token)."""
    try:
        body = json.dumps({"instruments": [{"instrument_key": k, "quantity": lot, "transaction_type": s, "product": "D"} for k, s in legs]}).encode()
        h = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "stock-data-exec/1.0", "Authorization": "Bearer " + token()}
        per = float(json.loads(urllib.request.urlopen(urllib.request.Request("https://api.upstox.com/v2/charges/margin", data=body, method="POST", headers=h), timeout=15).read())["data"]["final_margin"])
        f = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.upstox.com/v2/user/get-funds-and-margin?segment=SEC", headers=h), timeout=15).read()).get("data", {})
        avail = float((f.get("equity") or f).get("available_margin", 0) or 0)
    except Exception as e:  # noqa: BLE001
        log("margin check unavailable (", e, ") - keeping requested lots; keep ~Rs 0.9L per lot free")
        return want
    fit = int(avail // (per * 1.10)) if per > 0 else want
    log(f"margin per lot Rs {per:,.0f}, available Rs {avail:,.0f}, fits {fit} lot(s)")
    return max(0, min(want, fit))


def kill_switch(ledger):
    if not os.path.exists(ledger):
        return None
    rows = [r.split(",") for r in open(ledger).read().strip().splitlines()[1:]]
    eq = peak = dd = 0.0
    months = {}
    for r in rows:
        if r[1] != "live":
            continue
        per_lot = float(r[6]) / max(int(r[3]), 1)
        eq += per_lot
        peak, dd = max(peak, eq), max(dd, peak - eq)
        months[r[0][:7]] = months.get(r[0][:7], 0.0) + per_lot
    if dd > KILL_DD:
        return f"drawdown Rs {dd:,.0f} per lot"
    last = [months[k] for k in sorted(months)][-12:]
    if len(last) >= 6 and sum(last) < 0:
        return f"last {len(last)} months negative (Rs {sum(last):,.0f} per lot)"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--account", default="default")
    ap.add_argument("--legs", choices=["both", "up"], default="both")
    ap.add_argument("--no-align", action="store_true", help="trade every signal, without the 5-day trend filter")
    ap.add_argument("--buffer", type=float, default=8.0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--now-entry", choices=["up", "dn"], help="paper test: enter now in this direction")
    ap.add_argument("--exit-now", action="store_true", help="paper test: exit the stored position now")
    a = ap.parse_args()
    X.LOGF = os.path.join(LAKE, f"m_{a.account}.log")
    state_f, ledger = os.path.join(LAKE, f"m_state_{a.account}.json"), os.path.join(LAKE, f"m_ledger_{a.account}.csv")
    ref_f = os.path.join(LAKE, f"m_ref_{a.account}.json")
    br, log = X.Broker(a.live, product="D"), X.log
    log("==== Strategy M start", "LIVE" if a.live else "PAPER", vars(a))
    today = X.now().date().isoformat()
    if not (a.now_entry or a.exit_now) and (X.now().weekday() >= 5 or today in holidays()):
        log("market holiday - nothing to do")
        return
    state = json.load(open(state_f)) if os.path.exists(state_f) else None
    if state and not a.live:
        br.paper.update(state.get("paper_orders", {}))

    # ---- 1. exit yesterday's position at 09:20
    if state:
        if state["entry_date"] == today and not a.exit_now:
            log("position was opened today - it exits tomorrow 09:20")
            return
        if not a.exit_now:
            X.wait_until(EXIT)
        legs, qty, ex = state["legs"], state["qty"], {}
        for g in ("short", "wing"):  # short first
            ex[g] = X.fill_limit(br, legs[g]["key"], "BUY" if g == "short" else "SELL", qty, a.buffer)
        gross = (legs["short"]["entry"] - ex["short"]) * qty + (ex["wing"] - legs["wing"]["entry"]) * qty
        cost = 4 * 20 * 1.18 + (legs["short"]["entry"] + ex["wing"]) * qty * 0.0015 + (legs["short"]["entry"] + ex["short"] + legs["wing"]["entry"] + ex["wing"]) * qty * 0.000415
        log(f"EXIT: gross Rs {gross:,.0f}, est. charges Rs {cost:,.0f}, exits {ex}")
        new = not os.path.exists(ledger)
        with open(ledger, "a") as f:
            if new:
                f.write("date,mode,dir,lots,gross,est_charges,net,signal_pct\n")
            f.write(f"{today},{'live' if a.live else 'paper'},{state['dir']},{state['lots']},{gross:.0f},{cost:.0f},{gross - cost:.0f},{state.get('r', 0):.2f}\n")
        os.remove(state_f)
        if a.exit_now:
            return

    # ---- 2. reference spot at 09:20
    ref = json.load(open(ref_f)) if os.path.exists(ref_f) else {}
    if ref.get("date") != today and not a.now_entry:
        if X.now().time() <= dt.time(9, 20, 30):
            X.wait_until(REF)
            s0 = br.ltp([NIFTY])[NIFTY]
        else:
            s0 = candle_close(REF)
        if not s0:
            log("no 09:20 reference price - no trade today")
            return
        ref = {"date": today, "s0": s0}
        json.dump(ref, open(ref_f, "w"))
        log("09:20 reference spot", s0)

    # ---- 3. signal at 15:19:30
    reason = kill_switch(ledger)
    if reason:
        log("KILL-SWITCH: no new entries:", reason)
        return
    if a.now_entry:
        spot = br.ltp([NIFTY])[NIFTY]
        bull, r = a.now_entry == "up", 0.0
    else:
        if X.now().time() > dt.time(15, 24):
            log("started after 15:24 - too late for today's entry")
            return
        X.wait_until(SIGNAL)
        import time
        time.sleep(30)
        spot = br.ltp([NIFTY])[NIFTY]
        r = (spot / ref["s0"] - 1) * 100
        log(f"signal: spot {spot}, 09:20 {ref['s0']}, r {r:+.2f} %")
        if abs(r) <= THR:
            log("flat day - no trade")
            return
        bull = r > 0
        if not bull and a.legs == "up":
            log("down day and --legs up - no trade")
            return
        if not a.no_align:
            c5 = close_5d_ago()
            if c5 is None or (spot > c5) != bull:
                log(f"signal against the 5-day trend (close 5 days ago {c5}) - no trade")
                return
    cons = get("/v2/option/contract", {"instrument_key": NIFTY})["data"]
    exp = min(c["expiry"] for c in cons if c["expiry"] > today)
    cons = {(int(c["strike_price"]), c["instrument_type"]): c for c in cons if c["expiry"] == exp}
    lot = int(next(iter(cons.values()))["lot_size"])
    opt, sg = ("PE", -1) if bull else ("CE", 1)
    atm = round(spot / 50) * 50
    wk = atm + sg * round(spot * WING_PCT / 50) * 50
    if (wk, opt) not in cons or (atm, opt) not in cons:
        log(f"strike missing ({atm} / {wk} {opt}) - no trade")
        return
    k = {"wing": cons[(wk, opt)]["instrument_key"], "short": cons[(atm, opt)]["instrument_key"]}
    lots = margin_ok([(k["wing"], "BUY"), (k["short"], "SELL")], lot, a.lots, log)
    if lots == 0:
        log("not enough margin - no entry")
        return
    qty = lot * lots
    log(f"ENTRY {'UP: sell PE' if bull else 'DOWN: sell CE'} expiry {exp}: spot {spot}, short {atm} {opt}, wing {wk} {opt}, qty {qty}")
    legs = {}
    for g, side in (("wing", "BUY"), ("short", "SELL")):  # wing first
        legs[g] = {"key": k[g], "entry": X.fill_limit(br, k[g], side, qty, a.buffer)}
    state = {"entry_date": today, "expiry": exp, "dir": "up" if bull else "dn", "r": r, "lots": lots, "qty": qty, "legs": legs,
             "paper_orders": br.paper if not a.live else {}}
    json.dump(state, open(state_f, "w"), indent=1)
    log("position saved to", state_f, "- exit tomorrow 09:20")


if __name__ == "__main__":
    main()
