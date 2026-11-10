#!/usr/bin/env python3
"""Round 13 study 2: overnight drift with real option prices. Enter 15:20 if the day's 09:20->15:19 index return > thr,
exit next day 09:20. Structures: syn (long ATM CE + short ATM PE), synp (syn + long PE wing% below), call (long ATM CE),
bps (short ATM PE + long PE wing% below), itm (long CE itm% in the money), cds (long ATM CE, short CE wing% above)."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *

class ON(Strategy):
    def __init__(self, struct="syn", thr=0.0, wing=2.0, entry="15:20", exit_="09:20", lots=1, side=1, cond=None):
        self.struct, self.thr, self.wing, self.me, self.mx, self.lots, self.side, self.cond = struct, thr, wing, IDX(entry), IDX(exit_), lots, side, cond
    def on_minute(self, ctx, m):
        if m == self.mx and ctx.legs:
            ctx.close_all(m, "time")
        if m != self.me: return
        s0, s1 = ctx.spot(4), ctx.spot(m - 1)
        if s0 is None or s1 is None: return
        r = (s1 / s0 - 1) * 100
        if self.cond is not None:
            if not self.cond(ctx, r): return
        elif self.thr is not None and not (r > self.thr): return
        es = [e for e in ctx.expiries if ctx.tdte(e) >= 1]
        if not es: return
        e, k, s = es[0], ctx.atm(m), ctx.spot(m)
        rk = lambda x: int(round(x / 50) * 50)
        def near(opt, target):  # nearest listed strike with a price
            ch = ctx.day["chains"][e]; t = 0 if opt == "CE" else 1
            ok = ~np.isnan(ch["c"][t, :, m])
            if not ok.any(): return None
            ks = ch["strikes"][ok]; return int(ks[np.argmin(np.abs(ks - target))])
        legs = {"syn": [("CE", k, "B"), ("PE", k, "S")],
                "synp": [("PE", near("PE", rk(s * (1 - self.wing / 100))), "B"), ("CE", k, "B"), ("PE", k, "S")],
                "call": [("CE", k, "B")],
                "bps": [("PE", near("PE", rk(s * (1 - self.wing / 100))), "B"), ("PE", k, "S")],
                "itm": [("CE", near("CE", rk(s * (1 - self.wing / 100))), "B")],
                "cds": [("CE", k, "B"), ("CE", near("CE", rk(s * (1 + self.wing / 100))), "S")]}[self.struct]
        if any(kk is None or ctx.px(e, kk, o, m) is None for o, kk, _ in legs): return
        if len({(o, kk) for o, kk, _ in legs}) < len(legs): return
        for o, kk, sd in legs: ctx.open(e, kk, o, sd, self.lots, m, self.struct)

if __name__ == "__main__":
    days, f = load()
    out = {}
    for struct, thr, wing in [("syn", None, 0), ("syn", 0.0, 0), ("syn", 0.3, 0), ("synp", 0.0, 2.0), ("synp", 0.0, 1.0), ("synp", 0.3, 2.0),
                              ("call", 0.0, 0), ("itm", 0.0, 1.0), ("bps", 0.0, 2.0), ("bps", 0.0, 1.0), ("cds", 0.0, 1.0), ("cds", 0.0, 2.0)]:
        r = run(ON(struct, thr, wing), days, f)
        nm = f"{struct} thr{thr} w{wing}"
        print(line(nm, r)); print("    ", yearly(r), flush=True)
        out[nm] = r["daily"]
    os.makedirs("data/r13", exist_ok=True); json.dump(out, open("data/r13/s2.json", "w"))
