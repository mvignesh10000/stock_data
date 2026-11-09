#!/usr/bin/env python3
"""Paper-trade Strategy B for one expiry day from real 1-minute candles (Upstox intraday API), with exactly the
backtest's semantics, then (optionally) follow live minute by minute until the exit time.

Semantics (= opt_engine / AlgoTest, see STRATEGY_CARD.md):
  * entry "09:20" = close of the 09:19 candle: ATM = round(spot/50)*50; wings = OTM CE / PE whose 09:19 close is closest to Rs 3
  * fills: sells at close - slip, buys at close + slip, slip = max(0.5 % x price, Rs 0.10)
  * leg stops: 50 % above each short's fill, checked on the candle HIGH (pessimistic), fill = max(trigger, open) x 1.01 + slip
  * after the first short stop: other short's stop moves to its entry price (re-checked on the same candle)
  * overall stop: MTM (premium points x 65, before charges) <= -Rs 3,000 at a candle close -> exit all at that close
  * time exit "15:15" = close of the 15:14 candle; charges at today's rates added at the end
Usage: python execution/paper_day.py [--date YYYY-MM-DD] [--follow]
Output: data/paper/<date>.json (+ printed log); a Markdown summary is written to reports/paper/<date>.md
"""
import argparse, datetime as dt, json, os, sys, time, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "etl"))
from upstox_backfill import get, IDX  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
LOT, SL, OSL, WING = 65, 50.0, 3000.0, 3.0


def now():
    return dt.datetime.now(IST).replace(tzinfo=None)


def candles(key):
    """today's 1-min candles {HH:MM (bar start): (o, h, l, c, vol, oi)}"""
    r = get(f"/v3/historical-candle/intraday/{urllib.parse.quote(key, safe='')}/minutes/1") or {}
    out = {}
    for c in (r.get("data") or {}).get("candles", []):
        t = dt.datetime.fromisoformat(c[0]).astimezone(IST)
        out[t.strftime("%H:%M")] = tuple(float(x) for x in c[1:7])
    return out


def hm(t, d):
    x = dt.datetime.strptime(t, "%H:%M") + dt.timedelta(minutes=d)
    return x.strftime("%H:%M")


def slip(p):
    return max(0.005 * p, 0.10)


def charges(side, price, qty=LOT):
    t = price * qty
    brok, exch, sebi = 20.0, t * 0.0003503, t * 1e-6
    return brok + (t * 0.0015 if side == "S" else 0) + exch + sebi + (t * 0.00003 if side == "B" else 0) + 0.18 * (brok + exch + sebi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=now().date().isoformat())
    ap.add_argument("--follow", action="store_true")
    a = ap.parse_args()
    log = []

    def say(*x):
        s = " ".join(str(v) for v in x)
        print(s, flush=True)
        log.append(s)

    cons = get("/v2/option/contract", {"instrument_key": IDX["NIFTY"], "expiry_date": a.date})["data"]
    if not cons:
        say("no NIFTY contracts expiring", a.date)
        return
    ck = {(int(c["strike_price"]), c["instrument_type"]): c["instrument_key"] for c in cons}
    entry_bar, exit_bar = "09:19", "15:14"  # AlgoTest 09:20 / 15:15
    spot_c = candles(IDX["NIFTY"])
    if entry_bar not in spot_c:
        say("no 09:19 spot candle yet")
        return
    spot = spot_c[entry_bar][3]
    atm = int(round(spot / 50) * 50)
    # wings: closest premium to Rs 3 at the 09:19 close, among OTM strikes up to 60 strikes away
    best = {}
    for opt, rng in (("CE", range(atm + 50, atm + 3050, 50)), ("PE", range(atm - 50, atm - 3050, -50))):
        cands = []
        for k in rng:
            if (k, opt) not in ck:
                continue
            c = candles(ck[(k, opt)]).get(entry_bar)
            if c:
                cands.append((abs(c[3] - WING), k, c[3]))
                if c[3] < WING * 0.5:  # far enough
                    break
        best[opt] = min(cands)[1:]
    legs = {"sce": (atm, "CE", "S"), "spe": (atm, "PE", "S"), "lce": (best["CE"][0], "CE", "B"), "lpe": (best["PE"][0], "PE", "B")}
    say(f"== Strategy B paper trade, NIFTY expiry {a.date}")
    say(f"09:20 entry: spot {spot:.2f} -> ATM {atm}; wings {best['CE'][0]} CE (Rs {best['CE'][1]}) / {best['PE'][0]} PE (Rs {best['PE'][1]})")

    def run(data):
        pos = {}
        for g, (k, opt, side) in legs.items():
            p = data[g][entry_bar][3]
            fill = p - slip(p) if side == "S" else p + slip(p)
            pos[g] = {"strike": k, "opt": opt, "side": side, "entry": round(max(fill, 0.05), 2), "exit": None, "exit_t": None, "why": None}
        for g in ("sce", "spe"):
            pos[g]["stop"] = pos[g]["entry"] * (1 + SL / 100)
        trailed, events, last_t, mtm = False, [], entry_bar, 0.0
        t = hm(entry_bar, 1)
        while t <= exit_bar and all(t in data[g] for g in legs):
            last_t = t
            for g in ("sce", "spe"):
                p = pos[g]
                if p["exit"] is None and data[g][t][1] >= p["stop"]:
                    fill = max(p["stop"], data[g][t][0]) * 1.01 + slip(p["stop"])
                    p.update(exit=round(fill, 2), exit_t=hm(t, 1), why="leg SL")
                    events.append(f"{hm(t, 1)} leg SL {p['strike']} {p['opt']} filled {fill:.2f}")
                    o = "spe" if g == "sce" else "sce"
                    if not trailed and pos[o]["exit"] is None:
                        pos[o]["stop"] = pos[o]["entry"]
                        trailed = True
                        events.append(f"{hm(t, 1)} trail: {pos[o]['strike']} {pos[o]['opt']} stop -> {pos[o]['entry']:.2f}")
                        if data[o][t][1] >= pos[o]["stop"]:  # pessimistic same-bar re-check
                            f2 = max(pos[o]["stop"], data[o][t][0]) * 1.01 + slip(pos[o]["stop"])
                            pos[o].update(exit=round(f2, 2), exit_t=hm(t, 1), why="trailed SL")
                            events.append(f"{hm(t, 1)} trailed SL {pos[o]['strike']} {pos[o]['opt']} filled {f2:.2f}")
            mtm = sum(((p["exit"] if p["exit"] is not None else data[g][t][3]) - p["entry"]) * (-1 if p["side"] == "S" else 1) * LOT for g, p in pos.items())
            done = all(p["exit"] is not None for g, p in pos.items() if p["side"] == "S")
            if mtm <= -OSL or t == exit_bar or done:
                why = "overall SL" if mtm <= -OSL else ("time exit" if t == exit_bar else "both shorts stopped")
                for g, p in pos.items():
                    if p["exit"] is None:
                        c = data[g][t][3]
                        f = c + slip(c) if p["side"] == "S" else max(c - slip(c), 0.05)
                        p.update(exit=round(f, 2), exit_t=hm(t, 1), why=why)
                events.append(f"{hm(t, 1)} {why}: all legs closed")
                break
            t = hm(t, 1)
        gross = sum(((p["exit"] if p["exit"] is not None else data[g][last_t][3]) - p["entry"]) * (-1 if p["side"] == "S" else 1) * LOT for g, p in pos.items())
        cost = sum(charges(p["side"], p["entry"]) for p in pos.values()) + sum(charges("B" if p["side"] == "S" else "S", p["exit"]) for p in pos.values() if p["exit"] is not None)
        closed = all(p["exit"] is not None for p in pos.values())
        return pos, events, last_t, gross, cost, closed

    seen = 0
    while True:
        data = {g: candles(ck[(k, opt)]) for g, (k, opt, _) in legs.items()}
        pos, events, last_t, gross, cost, closed = run(data)
        for e in events[seen:]:
            say(e)
        seen = len(events)
        say(f"[{now():%H:%M}] through candle {last_t}: MTM Rs {gross:,.0f} gross, charges so far ~Rs {cost:,.0f}" + (" (closed)" if closed else ""))
        if closed or not a.follow or now().strftime("%H:%M") > "15:20":
            break
        time.sleep(max(5, 62 - now().second))
    net = gross - cost
    res = {"date": a.date, "spot_0920": spot, "atm": atm, "wings": best, "positions": pos, "events": events, "gross": round(gross, 2),
           "charges": round(cost, 2), "net": round(net, 2), "closed": closed, "through": last_t, "log": log}
    os.makedirs(f"{ROOT}/data/paper", exist_ok=True)
    json.dump(res, open(f"{ROOT}/data/paper/{a.date}.json", "w"), indent=1)
    os.makedirs(f"{ROOT}/reports/paper", exist_ok=True)
    rows = "\n".join(f"| {p['side'] == 'S' and 'SELL' or 'BUY'} {p['strike']} {p['opt']} | {p['entry']:.2f} | {p['exit'] if p['exit'] is not None else '-'} | {p['exit_t'] or '-'} | {p['why'] or 'open'} |" for p in pos.values())
    md = (f"# Paper trade, Strategy B, NIFTY expiry {a.date}\n\nReplay of real 1-minute candles with the backtest's fill model (not live orders).\n\n"
          f"Entry 09:20: spot {spot:.2f}, ATM {atm}, wings {best['CE'][0]} CE / {best['PE'][0]} PE (premium closest to Rs 3).\n\n"
          f"| Leg | Entry | Exit | Exit time | Reason |\n|---|---|---|---|---|\n{rows}\n\n"
          f"Events:\n" + "\n".join(f"- {e}" for e in events) +
          f"\n\nGross Rs {gross:,.0f} · charges Rs {cost:,.0f} · **net Rs {net:,.0f}** for 1 lot (65){'' if closed else f' (open, through candle {last_t})'}.\n")
    open(f"{ROOT}/reports/paper/{a.date}.md", "w").write(md)
    say(f"NET Rs {net:,.0f} (1 lot) -> reports/paper/{a.date}.md")


if __name__ == "__main__":
    main()
