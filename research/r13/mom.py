#!/usr/bin/env python3
"""Round 14: general momentum-premium strategy (overnight M, intraday N).
Signal at `sig` (close of the previous minute): r = spot / spot(09:20) - 1. r > thr -> bullish (sell ATM PE), r < -thr -> bearish
(sell ATM CE). overnight=True: exit next trading day at `exit_`; False: exit the same day at `exit_`.
align="d5": trade only when the 5-day return (15:19 closes, or the signal-time spot today) has the same sign as the signal.
struct: naked | ps (short + long wing `wing` % beyond) | syn. sl = leg stop % on the short leg (intraday only). legs = "both"|"up"|"dn"."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *

class MOM(Strategy):
    def __init__(self, sig="15:20", exit_="09:20", overnight=True, thr=0.3, struct="naked", wing=4.0, align=None, legs="both", sl=None, expiry_day=True, lots=1):
        self.ms, self.mx, self.on, self.thr, self.struct, self.wing, self.align, self.which, self.sl, self.xd, self.lots = IDX(sig), IDX(exit_), overnight, thr, struct, wing, align, legs, sl, expiry_day, lots
        self.hist = []
    def on_minute(self, ctx, m):
        if ctx.legs and m == self.mx and (not self.on or ctx.legs[0].entry_date != ctx.date): ctx.close_all(m, "time")
        if m == 364:
            s = ctx.spot(363)
            if s is not None and (not self.hist or self.hist[-1][0] != ctx.date): self.hist.append((ctx.date, s))
        if m != self.ms or ctx.legs: return
        s0, s1 = ctx.spot(4), ctx.spot(m - 1)
        if s0 is None or s1 is None: return
        r = (s1 / s0 - 1) * 100
        bull = True if r > self.thr else False if r < -self.thr else None
        if bull is None or (bull and self.which == "dn") or (not bull and self.which == "up"): return
        if self.align == "d5":
            h = [v for d, v in self.hist if d < ctx.date]
            if len(h) < 5 or (s1 > h[-5]) != bull: return
        if not self.xd and ctx.expiries and ctx.tdte(ctx.expiries[0]) == 0: return
        es = [e for e in ctx.expiries if ctx.tdte(e) >= (1 if self.on else 0)]
        if not es: return
        e, k, s = es[0], ctx.atm(m), ctx.spot(m)
        A, Bo, sg = ("CE", "PE", -1) if bull else ("PE", "CE", 1)
        w = None
        if self.struct == "ps":
            ch = ctx.day["chains"][e]; t = 0 if Bo == "CE" else 1
            ok = ~np.isnan(ch["c"][t, :, m]) & (ch["c"][t, :, m] > 0.3)
            if not ok.any(): return
            ks = ch["strikes"][ok]; w = int(ks[np.argmin(np.abs(ks - s * (1 + sg * self.wing / 100)))])
            if w == k: return
        legs = {"naked": [(Bo, k, "S")], "ps": [(Bo, w, "B"), (Bo, k, "S")], "syn": [(A, k, "B"), (Bo, k, "S")]}[self.struct]
        if any(ctx.px(e, kk, o, m) is None for o, kk, _ in legs): return
        for o, kk, sd in legs:
            leg = ctx.open(e, kk, o, sd, self.lots, m, self.struct)
            if leg and sd == "S" and self.sl: leg.sl = leg.entry * (1 + self.sl / 100)
    def on_stop(self, ctx, legs, m):
        if not any(l.side == "S" for l in ctx.legs): ctx.close_all(m, "wing out")

if __name__ == "__main__":
    import json, lib, zen
    out = {}
    def go(tag, days, f, G, a=0, z=99999999):
        for nm, kw in G:
            r = run(MOM(**kw), days, f, a, z); print(line(tag + nm, r)); print("    ", yearly(r), flush=True)
            out[tag + nm] = [(d, round(p, 1), round(mg)) for d, p, mg, _ in r["daily"]]
            json.dump(out, open("results/r13/mom.json", "w"))
    days, f = load()
    N = dict(overnight=False, sig="12:00", exit_="15:20", expiry_day=False)
    go("", days, f, [("M both", {}), ("M up", dict(legs="up")), ("M both d5", dict(align="d5")), ("M up d5", dict(align="d5", legs="up")),
                     ("N 12:00", N), ("N 13:00", {**N, "sig": "13:00"}), ("N 12:00 sl50", {**N, "sl": 50}), ("N 12:00 thr.5", {**N, "thr": 0.5}), ("N 12:00 d5", {**N, "align": "d5"}),
                     ("N 12:00 expiry days too", {**N, "expiry_day": True})])
    W = dict(struct="ps", wing=4.0)
    go("24+ ", days, f, [("M both naked", {}), ("M both w4", W), ("M up w4", {**W, "legs": "up"}), ("M both d5 w4", {**W, "align": "d5"}), ("M up d5 w4", {**W, "align": "d5", "legs": "up"}),
                         ("M both d5 w3", {**W, "align": "d5", "wing": 3.0}), ("N 12:00 w3", {**N, "struct": "ps", "wing": 3.0}), ("N 12:00 naked", N)], 20240101)
    days = zen.load(); lib.BLOCKS = (("17-18", 20170101, 20181231), ("19", 20190101, 20191231), ("20", 20200101, 20201231))
    go("ZEN ", days, {}, [("M both d5", dict(align="d5")), ("M up d5", dict(align="d5", legs="up")), ("N 12:00", N), ("N 13:00", {**N, "sig": "13:00"})])
