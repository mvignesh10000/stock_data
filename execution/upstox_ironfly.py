#!/usr/bin/env python3
"""Expiry-day iron fly executor for Upstox (OrderApiV3).  PAPER mode by default; --live sends real orders.

Strategy B (research v11/v12, see STRATEGY_CARD.md). Defaults = strategy B:
  * runs only when today is the nearest expiry of the chosen index (NIFTY Tue / SENSEX Thu, holiday-shifted)
  * 09:20 IST: BUY wings first (OTM CE / PE whose premium is closest to Rs 3) then SELL ATM CE + ATM PE, LIMIT orders
  * each short leg gets an exchange-resident SL-LIMIT at entry x (1 + SL%)        (default 50 %)
  * when one short SL fills, the other short's SL is moved to its entry price  (trail to breakeven)
  * whole-position MTM stop (default Rs 3,000 per lot): exits everything
  * 15:15 IST: exit everything (shorts first, then wings)
Requirements / caveats
  * Upstox order APIs only accept calls from your registered STATIC IP -> run this on that machine.
  * SEBI retail-algo framework (from 1-Apr-2026): self-built API strategies under the order-rate threshold are
    allowed through the broker's API but must be tagged; check Upstox's current Algo-ID registration
    process before going live and set ALGO_TAG below accordingly.
  * Token: LIVE orders need a normal daily access token (extended 1-year tokens are read-only); paper mode is fine with the extended token.
Usage:  python execution/upstox_ironfly.py NIFTY [--lots 1] [--wing-prem 3] [--live]
"""
import argparse, datetime as dt, json, os, sys, time, urllib.request, urllib.error
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "etl"))
from upstox_backfill import get, token, IDX, LAKE  # noqa: E402

HFT = "https://api-hft.upstox.com"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
STEP = {"NIFTY": 50, "SENSEX": 100}
ALGO_TAG = "ironfly_v7"
LOGF = os.path.join(LAKE, "exec.log")
LEDGER = os.path.join(LAKE, "b_ledger.csv")
KILL_DD_PER_LOT, KILL_LOSING_MONTHS = 40000.0, 4


def now():
    return dt.datetime.now(IST).replace(tzinfo=None)


def log(*a):
    s = now().strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    os.makedirs(LAKE, exist_ok=True)
    with open(LOGF, "a") as f:
        f.write(s + "\n")


def tick(x):
    return max(0.05, round(round(x / 0.05) * 0.05, 2))


def wait_until(hhmm):
    t = dt.datetime.combine(now().date(), dt.time.fromisoformat(hhmm))
    while now() < t:
        time.sleep(min(5, (t - now()).total_seconds()))


class Broker:
    """Thin OrderApiV3 wrapper. In paper mode orders are simulated against live LTP."""

    def __init__(self, live, slip_pct=0.5, product="I"):
        self.live, self.slip, self.paper, self.n = live, slip_pct / 100, {}, 0
        self.product = product  # "I" intraday (Strategy B), "D" carry-forward/NRML (Strategy W)

    def _req(self, method, path, body=None):
        req = urllib.request.Request(HFT + path, method=method, data=json.dumps(body).encode() if body else None, headers={
            "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "stock-data-exec/1.0",
            "Authorization": "Bearer " + token()})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            log("ORDER API ERROR", e.code, e.read().decode(errors="ignore")[:300])
            return None

    def ltp(self, keys):
        d = (get("/v2/market-quote/ltp", {"instrument_key": ",".join(keys)}) or {}).get("data", {})
        out = {}
        for v in d.values():
            out[v["instrument_token"]] = float(v["last_price"])
        return out

    def place(self, key, side, qty, otype, price, trigger=0.0):
        body = {"quantity": qty, "product": self.product, "validity": "DAY", "price": tick(price), "tag": ALGO_TAG,
                "instrument_token": key, "order_type": otype, "transaction_type": side, "disclosed_quantity": 0,
                "trigger_price": tick(trigger) if trigger else 0, "is_amo": False, "slice": True}
        if self.live:
            r = self._req("POST", "/v3/order/place", body)
            oid = ((r or {}).get("data") or {}).get("order_ids", [None])[0]
        else:
            self.n += 1
            oid = f"P{self.n}"
            self.paper[oid] = dict(body, status="open", avg=None)
        log("PLACE", side, otype, key, qty, "px", body["price"], "trg", body["trigger_price"], "->", oid)
        return oid

    def modify(self, oid, qty, otype, price, trigger=0.0):
        body = {"order_id": oid, "quantity": qty, "validity": "DAY", "price": tick(price), "order_type": otype,
                "trigger_price": tick(trigger) if trigger else 0, "disclosed_quantity": 0}
        log("MODIFY", oid, otype, "px", body["price"], "trg", body["trigger_price"])
        if self.live:
            return self._req("PUT", "/v3/order/modify", body)
        self.paper[oid].update(price=body["price"], order_type=otype, trigger_price=body["trigger_price"])

    def cancel(self, oid):
        log("CANCEL", oid)
        if self.live:
            return self._req("DELETE", f"/v3/order/cancel?order_id={oid}")
        self.paper[oid]["status"] = "cancelled"

    def status(self, oid):
        """-> (status, avg_price). status in open|complete|rejected|cancelled|trigger pending."""
        if self.live:
            d = ((get("/v2/order/details", {"order_id": oid}) or {}).get("data") or {})
            return d.get("status", "?"), float(d.get("average_price") or 0)
        o = self.paper[oid]
        return o["status"], o["avg"]

    def paper_match(self, ltps):
        for o in self.paper.values():
            if o["status"] != "open":
                continue
            p = ltps.get(o["instrument_token"])
            if p is None:
                continue
            buy = o["transaction_type"] == "BUY"
            if o["order_type"] == "LIMIT" and ((buy and p <= o["price"]) or (not buy and p >= o["price"])):
                o.update(status="complete", avg=p * (1 + self.slip) if buy else p * (1 - self.slip))
            elif o["order_type"] == "SL" and ((buy and p >= o["trigger_price"]) or (not buy and p <= o["trigger_price"])):
                o.update(status="complete", avg=min(o["price"], p * (1 + 2 * self.slip)) if buy else max(o["price"], p * (1 - 2 * self.slip)))


def kill_switch(lots):
    """Reason string if the account's own ledger breaches the Strategy B kill-switch, else None."""
    if not os.path.exists(LEDGER):
        return None
    rows = [r.split(",") for r in open(LEDGER).read().strip().splitlines()[1:]]
    live = [(r[0], int(r[2]), float(r[5])) for r in rows if r[1] == "live"]
    eq = peak = dd = 0.0
    months = {}
    for d, n_lots, net in live:
        per_lot = net / max(n_lots, 1)
        eq += per_lot
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        months[d[:7]] = months.get(d[:7], 0.0) + per_lot
    if dd > KILL_DD_PER_LOT:
        return f"drawdown {dd:,.0f} per lot > {KILL_DD_PER_LOT:,.0f}"
    mv = [months[k] for k in sorted(months)]
    run = 0
    for v in mv[:-1]:  # completed months only
        run = run + 1 if v <= 0 else 0
        if run >= KILL_LOSING_MONTHS:
            return f"{KILL_LOSING_MONTHS} losing months in a row"
    return None


def fit_lots(k, lot, want):
    """Largest lot count <= want whose broker margin (Upstox /v2/charges/margin, x1.10 buffer) fits the available funds."""
    try:
        legs = lambda n: [{"instrument_key": k[g], "quantity": lot * n, "transaction_type": t, "product": "I"}
                          for g, t in (("lce", "BUY"), ("lpe", "BUY"), ("sce", "SELL"), ("spe", "SELL"))]
        body = json.dumps({"instruments": legs(1)}).encode()
        req = urllib.request.Request("https://api.upstox.com/v2/charges/margin", data=body, method="POST", headers={
            "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "stock-data-exec/1.0", "Authorization": "Bearer " + token()})
        per_lot = float(json.loads(urllib.request.urlopen(req, timeout=15).read())["data"]["final_margin"])
        freq = urllib.request.Request("https://api.upstox.com/v2/user/get-funds-and-margin?segment=SEC", headers={
            "Accept": "application/json", "User-Agent": "stock-data-exec/1.0", "Authorization": "Bearer " + token()})
        funds = json.loads(urllib.request.urlopen(freq, timeout=15).read()).get("data", {})  # one attempt, no retry loop
        avail = float((funds.get("equity") or funds).get("available_margin", 0) or 0)
    except Exception as e:  # noqa: BLE001
        log("margin check unavailable (", e, ") - keeping requested lots; make sure funds cover ~Rs 1.7L per lot")
        return want
    fit = int(avail // (per_lot * 1.10)) if per_lot > 0 else want
    log(f"margin per lot Rs {per_lot:,.0f}, available Rs {avail:,.0f}, fits {fit} lot(s)")
    return max(0, min(want, fit))


def fill_limit(br, key, side, qty, buffer_pct, timeout=60):
    """Marketable LIMIT with buffer, re-priced every 3 s until filled. Returns avg fill price."""
    p = br.ltp([key])[key]
    px = p * (1 + buffer_pct / 100) if side == "BUY" else p * (1 - buffer_pct / 100)
    oid = br.place(key, side, qty, "LIMIT", px)
    t0 = time.time()
    while True:
        if not br.live:
            br.paper_match(br.ltp([key]))
        st, avg = br.status(oid)
        if st == "complete":
            log("FILLED", side, key, qty, "@", round(avg, 2))
            return avg
        if st in ("rejected", "cancelled"):
            raise RuntimeError(f"order {oid} {st}")
        if time.time() - t0 > timeout:
            raise RuntimeError(f"order {oid} not filled in {timeout}s")
        time.sleep(3)
        p = br.ltp([key])[key]
        br.modify(oid, qty, "LIMIT", p * (1 + buffer_pct / 100) if side == "BUY" else p * (1 - buffer_pct / 100))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=["NIFTY", "SENSEX"])
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--wing", type=int, default=None, help="fixed wing distance in points (overrides --wing-prem)")
    ap.add_argument("--wing-prem", type=float, default=3.0, help="wings = OTM strike whose LTP is closest to this premium (strategy B: Rs 3)")
    ap.add_argument("--sl", type=float, default=50.0, help="short-leg SL %% of entry (strategy B: 50)")
    ap.add_argument("--mtm-sl", type=float, default=3000.0, help="overall MTM stop, Rs per lot (strategy B: 3000)")
    ap.add_argument("--entry", default="09:20")
    ap.add_argument("--exit", default="15:15")
    ap.add_argument("--buffer", type=float, default=8.0, help="limit price buffer %% (market orders not allowed)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even if today is not expiry (paper testing)")
    ap.add_argument("--account", default="default", help="account label: separate log and ledger per account")
    ap.add_argument("--ignore-kill-switch", action="store_true")
    a = ap.parse_args()
    global LOGF, LEDGER
    LOGF = os.path.join(LAKE, f"exec_{a.account}.log")
    LEDGER = os.path.join(LAKE, f"b_ledger_{a.account}.csv")
    name, st = a.name, STEP[a.name]
    reason = kill_switch(a.lots)
    if reason and not a.ignore_kill_switch:
        log("KILL-SWITCH ACTIVE, not trading:", reason, "(review, then remove the ledger rows or pass --ignore-kill-switch)")
        return
    br = Broker(a.live)
    log("==== start", name, "LIVE" if a.live else "PAPER", vars(a))

    cons = get("/v2/option/contract", {"instrument_key": IDX[name]})["data"]
    exp = min(c["expiry"] for c in cons)
    if exp != now().date().isoformat() and not a.force:
        log("today is not", name, "expiry (next:", exp, ") - nothing to do")
        return
    cons = {(int(c["strike_price"]), c["instrument_type"]): c for c in cons if c["expiry"] == exp}
    lot = int(next(iter(cons.values()))["lot_size"])
    qty = lot * a.lots

    wait_until(a.entry)
    spot = br.ltp([IDX[name]])[IDX[name]]
    atm = round(spot / st) * st
    if a.wing:
        kc, kp = atm + a.wing, atm - a.wing
    else:  # closest-premium wings (same rule as the backtest: OTM strike whose LTP is closest to --wing-prem)
        ce = {s_: c["instrument_key"] for (s_, t), c in cons.items() if t == "CE" and atm < s_ <= atm + 60 * st}
        pe = {s_: c["instrument_key"] for (s_, t), c in cons.items() if t == "PE" and atm - 60 * st <= s_ < atm}
        q = {}
        keys = list(ce.values()) + list(pe.values())
        for i in range(0, len(keys), 450):
            q.update(br.ltp(keys[i:i + 450]))
        kc = min(ce, key=lambda s_: abs(q.get(ce[s_], 1e9) - a.wing_prem))
        kp = min(pe, key=lambda s_: abs(q.get(pe[s_], 1e9) - a.wing_prem))
    k = {"sce": cons[(atm, "CE")]["instrument_key"], "spe": cons[(atm, "PE")]["instrument_key"],
         "lce": cons[(kc, "CE")]["instrument_key"], "lpe": cons[(kp, "PE")]["instrument_key"]}
    log("spot", spot, "ATM", atm, "wings", kc, "CE /", kp, "PE", "qty", qty, k)
    lots = fit_lots(k, lot, a.lots)
    if lots == 0:
        log("not enough margin for even 1 lot - skipping today")
        return
    if lots != a.lots:
        log(f"margin check: reducing lots {a.lots} -> {lots}")
    qty = lot * lots
    a.lots = lots

    entry = {}
    entry["lce"] = fill_limit(br, k["lce"], "BUY", qty, a.buffer)  # wings first: margin benefit + no naked exposure
    entry["lpe"] = fill_limit(br, k["lpe"], "BUY", qty, a.buffer)
    entry["sce"] = fill_limit(br, k["sce"], "SELL", qty, a.buffer)
    entry["spe"] = fill_limit(br, k["spe"], "SELL", qty, a.buffer)
    sl = {}
    for leg in ("sce", "spe"):
        trg = entry[leg] * (1 + a.sl / 100)
        sl[leg] = br.place(k[leg], "BUY", qty, "SL", trg * 1.10, trg)  # SL-LIMIT, 10 % limit buffer above trigger
    open_legs = {"sce", "spe", "lce", "lpe"}
    sign = {"sce": -1, "spe": -1, "lce": 1, "lpe": 1}
    exit_px, trailed = {}, False
    t_exit = dt.datetime.combine(now().date(), dt.time.fromisoformat(a.exit))

    def mtm(l):
        pts = sum(sign[g] * ((exit_px[g] if g in exit_px else l[k[g]]) - entry[g]) for g in entry)
        return pts * qty

    def flatten(reason):
        log("FLATTEN:", reason)
        for g in ("sce", "spe"):
            if g in open_legs:
                br.cancel(sl[g])
                exit_px[g] = fill_limit(br, k[g], "BUY", qty, a.buffer)
                open_legs.discard(g)
        for g in ("lce", "lpe"):
            if g in open_legs:
                exit_px[g] = fill_limit(br, k[g], "SELL", qty, a.buffer)
                open_legs.discard(g)

    while open_legs:
        l = br.ltp(list(k.values()))
        if not br.live:
            br.paper_match(l)
        for g in ("sce", "spe"):
            if g in open_legs:
                stt, avg = br.status(sl[g])
                if stt == "complete":
                    exit_px[g] = avg
                    open_legs.discard(g)
                    log("SL HIT", g, "@", round(avg, 2))
                    o = "spe" if g == "sce" else "sce"
                    if o in open_legs and not trailed:  # trail other short to breakeven
                        br.modify(sl[o], qty, "SL", entry[o] * 1.10, entry[o])
                        trailed = True
        m = mtm(l)
        if m <= -a.mtm_sl * a.lots:
            flatten(f"MTM {m:.0f} <= -{a.mtm_sl * a.lots:.0f}")
            break
        if now() >= t_exit:
            flatten("time exit")
            break
        # both shorts stopped: KEEP the wings until the time exit (backtest = AlgoTest partial square-off;
        # on strong trend days a wing can run from ~Rs 3 to Rs 100+)
        time.sleep(1)
    l = br.ltp(list(k.values()))
    gross = mtm(l)
    est_cost = 8 * 20 * 1.18 + sum(entry[g] for g in ("sce", "spe")) * qty * 0.0015 + sum(exit_px.get(g, 0) for g in ("lce", "lpe")) * qty * 0.0015
    log("==== done", name, "gross P&L Rs", round(gross, 0), "est. charges Rs", round(est_cost, 0), "entries", {g: round(v, 2) for g, v in entry.items()},
        "exits", {g: round(v, 2) for g, v in exit_px.items()})
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a") as f:
        if new:
            f.write("date,mode,lots,gross,est_charges,net\n")
        f.write(f"{now().date()},{'live' if a.live else 'paper'},{a.lots},{gross:.0f},{est_cost:.0f},{gross - est_cost:.0f}\n")


if __name__ == "__main__":
    main()
