#!/usr/bin/env python3
"""Round 13 overnight momentum (ON) strategy family. Signal at 15:19 close: r = spot/spot(09:20)-1 (%).
 up   (r >  thr_up): bullish structure;  down (r < -thr_dn): bearish structure (optional). Entry 15:20, exit next day 09:20.
Structures (bull; bear is the mirror): syn = long ATM CE + short ATM PE; synw = syn + long PE `wing` % below; call = long ATM CE;
 ps = short ATM PE + long PE wing % below (credit spread); naked = short ATM PE."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *

class ON2(Strategy):
    def __init__(self, up="syn", dn=None, thr_up=0.3, thr_dn=0.3, wing=2.0, entry="15:20", exit_="09:20", lots=1, skip=None):
        self.up, self.dn, self.tu, self.td, self.wing, self.me, self.mx, self.lots, self.skip = up, dn, thr_up, thr_dn, wing, IDX(entry), IDX(exit_), lots, skip
    def on_minute(self, ctx, m):
        if m == self.mx and ctx.legs: ctx.close_all(m, "time")
        if m != self.me: return
        s0, s1 = ctx.spot(4), ctx.spot(m - 1)
        if s0 is None or s1 is None: return
        r = (s1 / s0 - 1) * 100
        if self.up and r > self.tu: st, bull = self.up, True
        elif self.dn and r < -self.td: st, bull = self.dn, False
        else: return
        if self.skip and self.skip(ctx): return
        es = [e for e in ctx.expiries if ctx.tdte(e) >= 1]
        if not es: return
        e, k, s = es[0], ctx.atm(m), ctx.spot(m)
        A, Bo = ("CE", "PE") if bull else ("PE", "CE")   # A = option that gains with the signal, Bo = option sold
        sg = -1 if bull else 1
        def far(opt, pct):
            ch = ctx.day["chains"][e]; t = 0 if opt == "CE" else 1
            ok = ~np.isnan(ch["c"][t, :, m]) & (ch["c"][t, :, m] > 0.3)
            if not ok.any(): return None
            ks = ch["strikes"][ok]; return int(ks[np.argmin(np.abs(ks - s * (1 + sg * pct / 100)))])
        w = far(Bo, self.wing) if st in ("synw", "ps") else None
        legs = {"syn": [(A, k, "B"), (Bo, k, "S")], "synw": [(Bo, w, "B"), (A, k, "B"), (Bo, k, "S")], "call": [(A, k, "B")],
                "ps": [(Bo, w, "B"), (Bo, k, "S")], "naked": [(Bo, k, "S")]}[st]
        if any(kk is None or ctx.px(e, kk, o, m) is None for o, kk, _ in legs): return
        if w is not None and w == k: return
        for o, kk, sd in legs: ctx.open(e, kk, o, sd, self.lots, m, st)

if __name__ == "__main__":
    import json
    days, f = load(); out = {}
    G = [("up synw w2 t.3", dict(up="synw", wing=2.0)), ("up synw w3 t.3", dict(up="synw", wing=3.0)), ("up synw w3 t.5", dict(up="synw", wing=3.0, thr_up=0.5)),
         ("up ps w2 t.6", dict(up="ps", wing=2.0, thr_up=0.6)), ("up ps w3 t.3", dict(up="ps", wing=3.0)), ("up naked t.3", dict(up="naked")), ("up naked t.6", dict(up="naked", thr_up=0.6)),
         ("dn syn t.3", dict(up=None, dn="syn")), ("dn naked t.3", dict(up=None, dn="naked")), ("dn naked t.6", dict(up=None, dn="naked", thr_dn=0.6)),
         ("dn ps w3 t.3", dict(up=None, dn="ps", wing=3.0)), ("dn call t.3", dict(up=None, dn="call")),
         ("both syn/naked t.3", dict(up="syn", dn="naked")), ("both synw3/ps3 t.3", dict(up="synw", dn="ps", wing=3.0))]
    for nm, kw in G:
        r = run(ON2(**kw), days, f); print(line(nm, r)); print("    ", yearly(r), flush=True); out[nm] = r["daily"]
    json.dump(out, open("data/r13/on2.json", "w"))
