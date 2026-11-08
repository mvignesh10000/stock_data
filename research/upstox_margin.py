#!/usr/bin/env python3
"""Exact broker margin for structures via Upstox POST /v2/charges/margin (nearest live expiry).
Usage: python research/upstox_margin.py NIFTY|SENSEX  -> data/upstox/margin_{NAME}_{date}.json
Note: the expiry-day 2% ELM is only added by the exchange ON expiry day; add 2% x spot x qty for DTE0 sizing.
"""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/etl")
from upstox_backfill import get, token, B, LAKE, IDX  # noqa: E402
import urllib.request

STEP = {"NIFTY": 50, "SENSEX": 100}


def post(path, body):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode(), method="POST", headers={
        "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "stock-data-backfill/1.0",
        "Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main(name):
    key = IDX[name]
    cons = get("/v2/option/contract", {"instrument_key": key})["data"]
    exp = min(c["expiry"] for c in cons)
    cons = [c for c in cons if c["expiry"] == exp]
    ltp = get("/v2/market-quote/ltp", {"instrument_key": key})["data"]
    spot = float(list(ltp.values())[0]["last_price"])
    lot = int(cons[0]["lot_size"])
    st = STEP[name]
    atm = round(spot / st) * st
    k = {(int(c["strike_price"]), c["instrument_type"]): c["instrument_key"] for c in cons}

    def leg(strike, opt, side):
        return {"instrument_key": k[(strike, opt)], "quantity": lot, "transaction_type": side, "product": "D"}

    w = [4, 8, 12, 16] if name == "NIFTY" else [5, 10, 15, 20]
    S = {f"iron fly ±{n * st}": [leg(atm, "CE", "SELL"), leg(atm, "PE", "SELL"), leg(atm + n * st, "CE", "BUY"), leg(atm - n * st, "PE", "BUY")] for n in w}
    S["naked straddle"] = [leg(atm, "CE", "SELL"), leg(atm, "PE", "SELL")]
    S["bull put spread ATM/-4"] = [leg(atm, "PE", "SELL"), leg(atm - 4 * st, "PE", "BUY")]
    S["bear call spread ATM/+4"] = [leg(atm, "CE", "SELL"), leg(atm + 4 * st, "CE", "BUY")]
    res = {}
    for nm, legs in S.items():
        r = post("/v2/charges/margin", {"instruments": legs})["data"]
        res[nm] = {"final_margin": r.get("final_margin"), "required_margin": r.get("required_margin")}
        print(f"{name} {nm:26s} final ₹{r.get('final_margin'):>10,.0f}  (+expiry ELM 2% ≈ ₹{0.02 * spot * lot:,.0f})")
    out = {"name": name, "expiry": exp, "spot": spot, "lot": lot, "atm": atm, "date": dt.date.today().isoformat(), "margins": res}
    p = f"{LAKE}/margin_{name}_{dt.date.today():%Y%m%d}.json"
    json.dump(out, open(p, "w"), indent=1, ensure_ascii=False)
    print("saved", p)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "SENSEX")
