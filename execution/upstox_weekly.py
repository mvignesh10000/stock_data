#!/usr/bin/env python3
"""Strategy W executor: NIFTY weekly iron fly held overnight (see STRATEGY_W_CARD.md). PAPER by default; --live sends orders.

Run once per trading day at 09:12 IST (cron / Task Scheduler / execution/run_b.py-style wrapper); it stays up until 15:31:
  * position open, today is its expiry  -> exit everything at 09:20 (shorts first), write the ledger, clear the state
  * position open, other days           -> watch MTM every minute; if MTM since entry <= -Rs 8,000 x lots -> exit everything
  * no position, today is 3 trading days before the nearest weekly expiry -> enter at 15:15:
        BUY CE and PE 3 % of spot beyond ATM (wings first), SELL ATM CE + ATM PE; product "D" (carry-forward)
State persists in data/upstox/weekly_state_<account>.json between days. Ledger data/upstox/weekly_ledger_<account>.csv;
kill-switch: live drawdown > Rs 1.0L per lot or 6 losing months in a row -> no new entries.
Requirements: a normal daily Upstox token for --live (static IP); the extended token works for paper mode.
Usage: python execution/upstox_weekly.py [--lots 1] [--account acct1] [--live] [--now-entry] (paper test: enter immediately)
"""
import argparse, datetime as dt, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "etl"))
import upstox_ironfly as X  # Broker, fill_limit, log, now, wait_until, fit_lots
from upstox_backfill import get, IDX, LAKE  # noqa: E402

WING_PCT, WEEKLY_STOP, ENTRY, EXIT_EXPIRY = 0.03, 8000.0, "15:15", "09:20"
KILL_DD, KILL_MONTHS = 100000.0, 6


_HOL = None


def nfo_holidays():
    """Set of ISO dates on which NFO is closed (Upstox holiday list for the year, fetched once)."""
    global _HOL
    if _HOL is None:
        hol = (get("/v2/market/holidays") or {}).get("data", [])
        _HOL = {h["date"] for h in hol if "NFO" in (h.get("closed_exchanges") or [])}
    return _HOL


def trading_days_until(expiry):
    """Trading days after today up to and including expiry (weekends and NFO holidays excluded)."""
    d, e, n = X.now().date(), dt.date.fromisoformat(expiry), 0
    hol = nfo_holidays()
    while d < e:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in hol:
            n += 1
    return n


def kill_switch(ledger):
    if not os.path.exists(ledger):
        return None
    rows = [r.split(",") for r in open(ledger).read().strip().splitlines()[1:]]
    eq = peak = dd = 0.0
    months = {}
    for r in rows:
        if r[1] != "live":
            continue
        per_lot = float(r[5]) / max(int(r[2]), 1)
        eq += per_lot
        peak, dd = max(peak, eq), max(dd, peak - eq)
        months[r[0][:7]] = months.get(r[0][:7], 0.0) + per_lot
    if dd > KILL_DD:
        return f"drawdown {dd:,.0f} per lot"
    run = 0
    for k in sorted(months)[:-1]:
        run = run + 1 if months[k] <= 0 else 0
        if run >= KILL_MONTHS:
            return f"{KILL_MONTHS} losing months in a row"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--account", default="default")
    ap.add_argument("--buffer", type=float, default=8.0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--now-entry", action="store_true", help="paper test: enter now regardless of day/time")
    ap.add_argument("--exit-now", action="store_true", help="paper test: exit an open position now")
    a = ap.parse_args()
    X.LOGF = os.path.join(LAKE, f"weekly_{a.account}.log")
    state_f = os.path.join(LAKE, f"weekly_state_{a.account}.json")
    ledger = os.path.join(LAKE, f"weekly_ledger_{a.account}.csv")
    br = X.Broker(a.live, product="D")
    log = X.log
    log("==== Strategy W start", "LIVE" if a.live else "PAPER", vars(a))
    state = json.load(open(state_f)) if os.path.exists(state_f) else None
    if state and not a.live:
        br.paper.update(state.get("paper_orders", {}))

    def exit_all(why):
        legs, qty = state["legs"], state["qty"]
        exits = {}
        for g in ("sce", "spe", "lce", "lpe"):  # shorts first
            side = "BUY" if legs[g]["side"] == "S" else "SELL"
            exits[g] = X.fill_limit(br, legs[g]["key"], side, qty, a.buffer)
        gross = sum((-1 if legs[g]["side"] == "S" else 1) * (exits[g] - legs[g]["entry"]) * qty for g in legs)
        est_cost = 8 * 20 * 1.18 + sum(legs[g]["entry"] for g in ("sce", "spe")) * qty * 0.0015 + sum(exits[g] for g in ("lce", "lpe")) * qty * 0.0015
        log(f"EXIT ({why}): gross Rs {gross:,.0f}, est. charges Rs {est_cost:,.0f}, exits {exits}")
        new = not os.path.exists(ledger)
        with open(ledger, "a") as f:
            if new:
                f.write("date,mode,lots,gross,est_charges,net,reason\n")
            f.write(f"{X.now().date()},{'live' if a.live else 'paper'},{state['lots']},{gross:.0f},{est_cost:.0f},{gross - est_cost:.0f},{why}\n")
        os.remove(state_f)

    def mtm():
        legs, qty = state["legs"], state["qty"]
        l = br.ltp([legs[g]["key"] for g in legs])
        return sum((-1 if legs[g]["side"] == "S" else 1) * (l.get(legs[g]["key"], legs[g]["entry"]) - legs[g]["entry"]) * qty for g in legs)

    if state:
        if a.exit_now:
            exit_all("manual/test")
            return
        today = X.now().date().isoformat()
        if today == state["expiry"]:
            X.wait_until(EXIT_EXPIRY)
            exit_all("expiry morning")
            return
        close = dt.datetime.combine(X.now().date(), dt.time(15, 30))
        while X.now() < close:
            m = mtm()
            if m <= -WEEKLY_STOP * state["lots"]:
                exit_all(f"weekly stop MTM {m:,.0f}")
                return
            time.sleep(60)
        log(f"day end: position held, MTM since entry Rs {mtm():,.0f}")
        return

    # ---- no position: entry day?
    reason = kill_switch(ledger)
    if reason:
        log("KILL-SWITCH: no new entries:", reason)
        return
    cons = get("/v2/option/contract", {"instrument_key": IDX["NIFTY"]})["data"]
    exps = sorted({c["expiry"] for c in cons if c["expiry"] > X.now().date().isoformat()})
    target = exps[0] if exps and trading_days_until(exps[0]) == 3 else None  # nearest weekly expiry only
    if not target and not a.now_entry:
        log("not an entry day (needs 3 trading days to the next expiry)")
        return
    target = target or exps[0]
    if not a.now_entry:
        X.wait_until(ENTRY)
    cons = {(int(c["strike_price"]), c["instrument_type"]): c for c in cons if c["expiry"] == target}
    lot = int(next(iter(cons.values()))["lot_size"])
    spot = br.ltp([IDX["NIFTY"]])[IDX["NIFTY"]]
    atm = round(spot / 50) * 50
    dist = round(spot * WING_PCT / 50) * 50
    k = {"lce": cons[(atm + dist, "CE")]["instrument_key"], "lpe": cons[(atm - dist, "PE")]["instrument_key"],
         "sce": cons[(atm, "CE")]["instrument_key"], "spe": cons[(atm, "PE")]["instrument_key"]}
    lots = X.fit_lots(k, lot, a.lots)
    if lots == 0:
        log("not enough margin - no entry")
        return
    qty = lot * lots
    log(f"ENTRY expiry {target}: spot {spot}, ATM {atm}, wings {atm + dist} CE / {atm - dist} PE, qty {qty}")
    legs = {}
    for g, side in (("lce", "B"), ("lpe", "B"), ("sce", "S"), ("spe", "S")):
        px = X.fill_limit(br, k[g], "BUY" if side == "B" else "SELL", qty, a.buffer)
        legs[g] = {"key": k[g], "side": side, "entry": px}
    state = {"expiry": target, "entry_date": X.now().date().isoformat(), "lots": lots, "qty": qty, "legs": legs,
             "paper_orders": br.paper if not a.live else {}}
    json.dump(state, open(state_f, "w"), indent=1)
    log("position saved to", state_f)


if __name__ == "__main__":
    main()
