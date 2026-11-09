#!/usr/bin/env python3
"""v17: futures trend signals executed with deep ITM NIFTY options (futures STT is 0.05 % of notional since 1-Apr-2026, ~Rs 812
of a ~Rs 960 round trip; ITM options pay 0.15 % STT on the sell-side premium only, ~Rs 50 on a Rs 500 option).

Signals come from spot (as in research/fut, where they show a gross edge: ORB PF 1.15-1.29, EMA 20/50 PF 1.29 before costs):
  ORB    range to {09:45, 10:15}, buffer 0.1 %, first 1-min spot close beyond it by 12:00; stop when spot closes back at the
         opposite side of the range; exit 15:15
  EMA    5-min EMA(20, 50) on spot, always-in after 09:45, flip on cross (each flip closes one option and buys the other); exit 15:15
Execution: buy the CE (long signal) / PE (short signal) {4, 8} strikes in the money (200 / 400 pts), current weekly expiry,
1 lot; Python simulator costs (0.5 % slippage per fill, today's charges incl. 0.15 % STT on option sells).
Protocol: the signals were defined on 2015-2020 index data (research/fut); options data covers 2021-11..2026-11, so every
result here is out of sample for the signal; ITM depth is the only new parameter (2 values, both reported).
"""
import itertools, json, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim"))
import numpy as np
import store, features as F
from engine import IDX, Strategy, run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/v17")
os.makedirs(OUT, exist_ok=True)
EXIT = IDX("15:15")
BLK = {"2021-23": (20211115, 20231231), "2024-26": (20240101, 20261106)}


class ITMTrend(Strategy):
    def __init__(self, kind, itm, end="09:45"):
        self.kind, self.itm, self.end = kind, itm, end
        self.name = f"{kind}{'|' + end if kind == 'ORB' else ''}|ITM{itm}"

    def on_day(self, ctx):
        self.e = ctx.expiries[0] if ctx.expiries else None
        self.dir, self.leg, self.done = 0, None, False
        self.hi = self.lo = None
        self.ef = self.es = None

    def _enter(self, ctx, m, d):
        s = ctx.spot(m)
        k = int(round(s / 50) * 50) + (-1 if d > 0 else 1) * 50 * self.itm
        self.leg = ctx.open(self.e, k, "CE" if d > 0 else "PE", "B", 1, m, self.kind)
        self.dir = d if self.leg else 0

    def _exit(self, ctx, m, why):
        if self.leg and self.leg in ctx.legs:
            ctx.close(self.leg, m, why)
        self.leg, self.dir = None, 0

    def on_minute(self, ctx, m):
        if self.e is None:
            return
        s = ctx.spot(m)
        if s is None:
            return
        if m >= EXIT:
            self._exit(ctx, m, "time")
            return
        if self.kind == "ORB":
            E = IDX(self.end)
            if m < E:
                return
            if self.hi is None:
                sp = ctx.day["spot"]
                self.hi, self.lo = float(np.nanmax(sp[:E, 1])), float(np.nanmin(sp[:E, 2]))
            if self.dir == 0 and not self.done and m < IDX("12:00"):
                d = 1 if s > self.hi * 1.001 else -1 if s < self.lo * 0.999 else 0
                if d:
                    self._enter(ctx, m, d)
                    self.done = True
            elif self.dir and ((self.dir > 0 and s < self.lo) or (self.dir < 0 and s > self.hi)):
                self._exit(ctx, m, "stop")
        else:  # EMA 20/50 on 5-min spot closes, flip system
            if (m + 1) % 5:
                return
            a1, a2 = 2 / 21, 2 / 51
            self.ef = s if self.ef is None else a1 * s + (1 - a1) * self.ef
            self.es = s if self.es is None else a2 * s + (1 - a2) * self.es
            if m < IDX("09:45"):
                return
            want = 1 if self.ef > self.es else -1
            if want != self.dir:
                self._exit(ctx, m, "flip")
                self._enter(ctx, m, want)


def met(s, a, b):
    s = [(d, n) for d, n in s if a <= d <= b]
    eq = peak = dd = 0.0
    mo = collections.defaultdict(float)
    for d, n in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        mo[d // 100] += n
    tr = [n for _, n in s if abs(n) > 0.01]
    gw, gl = sum(x for x in tr if x > 0), -sum(x for x in tr if x < 0)
    mv = list(mo.values())
    return {"days_traded": len(tr), "net": round(eq), "per_year": round(eq / (len(s) / 248)), "pf": round(gw / gl, 2) if gl else 0,
            "dd": round(dd), "win_months": round(sum(x > 0 for x in mv) / len(mv) * 100, 1)}


def main():
    days, feat = store.load(), F.load()
    res = []
    for st in [ITMTrend("ORB", n, e) for e, n in itertools.product(["09:45", "10:15"], [4, 8])] + [ITMTrend("EMA", n) for n in (4, 8)]:
        r = run(st, days, feat, 20211115, 20261106)
        s = [(d, n) for d, n, _, _ in r["daily"]]
        n_tr = sum(1 for l in r["trades"])
        row = {"name": st.name, "fills": n_tr, **{k: met(s, *v) for k, v in BLK.items()}, "all": met(s, 0, 99999999)}
        res.append(row)
        print(f"{st.name:18s} " + " | ".join(f"{k} pf {row[k]['pf']:.2f} /yr {row[k]['per_year']:>7} dd {row[k]['dd']:>6} winM {row[k]['win_months']}%" for k in BLK), f"| option trades {n_tr}", flush=True)
    json.dump(res, open(f"{OUT}/itm_trend.json", "w"), indent=1)


if __name__ == "__main__":
    main()
