#!/usr/bin/env python3
"""Round 13: real Upstox margins for candidate structures (nearest live NIFTY weekly). -> results/r13/margins.json"""
import json, os, sys
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, R + "/etl"); sys.path.insert(0, R + "/research")
from upstox_backfill import get, IDX
from upstox_margin import post
key = IDX["NIFTY"]
cons = get("/v2/option/contract", {"instrument_key": key})["data"]
exp = min(c["expiry"] for c in cons); cons = [c for c in cons if c["expiry"] == exp]
spot = float(list(get("/v2/market-quote/ltp", {"instrument_key": key})["data"].values())[0]["last_price"])
lot = int(cons[0]["lot_size"]); atm = round(spot / 50) * 50
k = {(int(c["strike_price"]), c["instrument_type"]): c["instrument_key"] for c in cons}
L = lambda off, opt, side, prod="D": {"instrument_key": k[(atm + off, opt)], "quantity": lot, "transaction_type": side, "product": prod}
S = {"naked short straddle": [L(0, "CE", "SELL"), L(0, "PE", "SELL")],
     "iron fly +-100": [L(0, "CE", "SELL"), L(0, "PE", "SELL"), L(100, "CE", "BUY"), L(-100, "PE", "BUY")],
     "iron fly +-200": [L(0, "CE", "SELL"), L(0, "PE", "SELL"), L(200, "CE", "BUY"), L(-200, "PE", "BUY")],
     "iron fly +-400": [L(0, "CE", "SELL"), L(0, "PE", "SELL"), L(400, "CE", "BUY"), L(-400, "PE", "BUY")],
     "iron fly +-800": [L(0, "CE", "SELL"), L(0, "PE", "SELL"), L(800, "CE", "BUY"), L(-800, "PE", "BUY")],
     "iron fly +-1200": [L(0, "CE", "SELL"), L(0, "PE", "SELL"), L(1200, "CE", "BUY"), L(-1200, "PE", "BUY")],
     "put credit spread ATM/-200": [L(0, "PE", "SELL"), L(-200, "PE", "BUY")],
     "put credit spread ATM/-500": [L(0, "PE", "SELL"), L(-500, "PE", "BUY")],
     "call credit spread ATM/+200": [L(0, "CE", "SELL"), L(200, "CE", "BUY")],
     "synthetic long (CE buy, PE sell)": [L(0, "CE", "BUY"), L(0, "PE", "SELL")],
     "synthetic long + PE wing -250": [L(0, "CE", "BUY"), L(0, "PE", "SELL"), L(-250, "PE", "BUY")],
     "synthetic long + PE wing -500": [L(0, "CE", "BUY"), L(0, "PE", "SELL"), L(-500, "PE", "BUY")],
     "long ATM call": [L(0, "CE", "BUY")],
     "call debit spread ATM/+200": [L(0, "CE", "BUY"), L(200, "CE", "SELL")],
     "call debit spread -200/ATM (ITM)": [L(-200, "CE", "BUY"), L(0, "CE", "SELL")],
     "long call fly -100/ATM/+100": [L(-100, "CE", "BUY"), L(0, "CE", "SELL"), L(0, "CE", "SELL"), L(100, "CE", "BUY")],
     "short strangle +-300": [L(300, "CE", "SELL"), L(-300, "PE", "SELL")],
     "iron condor +-300/+-500": [L(300, "CE", "SELL"), L(-300, "PE", "SELL"), L(500, "CE", "BUY"), L(-500, "PE", "BUY")]}
res = {}
for nm, legs in S.items():
    try:
        r = post("/v2/charges/margin", {"instruments": legs})["data"]
        res[nm] = r.get("final_margin"); print(f"{nm:36s} Rs {r.get('final_margin'):>10,.0f}   required {r.get('required_margin'):>10,.0f}")
    except Exception as ex:
        print(nm, "ERR", str(ex)[:100])
os.makedirs(R + "/results/r13", exist_ok=True)
json.dump({"expiry": exp, "spot": spot, "lot": lot, "atm": atm, "elm_expiry_day_per_short_lot": 0.02 * spot * lot, "margins": res}, open(R + "/results/r13/margins.json", "w"), indent=1)
print("expiry", exp, "spot", spot, "lot", lot, "| expiry-day ELM per short leg ≈", round(0.02 * spot * lot))
