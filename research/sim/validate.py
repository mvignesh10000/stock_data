#!/usr/bin/env python3
"""Validate the Python simulator against opt_engine on Strategy B (2021-11-15 .. 2026-11-03).
Pass criterion: same traded days, 5-year net within 3 %, per-day |difference| median < Rs 50."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
from engine import IDX, Strategy, run

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StrategyB(Strategy):
    name = "B"

    def __init__(self, sl=50, wing=3.0, osl=3000, entry="09:20", exit_="15:15"):
        self.sl, self.wing, self.osl, self.me, self.mx = sl, wing, osl, IDX(entry), IDX(exit_)

    def on_day(self, ctx):
        self.active, self.trailed = False, False
        self.e = ctx.expiries[0] if ctx.expiries else None
        self.today = self.e is not None and ctx.tdte(self.e) == 0

    def on_minute(self, ctx, m):
        if not self.today:
            return
        if m == self.me:
            k = ctx.atm(m)
            kc, kp = ctx.strike_by_premium(self.e, "CE", self.wing, m), ctx.strike_by_premium(self.e, "PE", self.wing, m)
            if None in (k, kc, kp) or None in (ctx.px(self.e, k, "CE", m), ctx.px(self.e, k, "PE", m)):
                self.today = False
                return
            ctx.open(self.e, kc, "CE", "B", 1, m, "wing")
            ctx.open(self.e, kp, "PE", "B", 1, m, "wing")
            for opt in ("CE", "PE"):
                leg = ctx.open(self.e, k, opt, "S", 1, m, "short")
                leg.sl = leg.entry * (1 + self.sl / 100)
            self.active = True
            return
        if self.active and ctx.legs:
            if ctx.mtm(m) <= -self.osl or m >= self.mx:
                ctx.close_all(m, "overall SL" if m < self.mx else "time")
                self.active = False

    def on_stop(self, ctx, legs, m):
        if not self.trailed and any(l.side == "S" for l in legs):
            for l in ctx.legs:
                if l.side == "S":
                    l.sl = l.entry
            self.trailed = True


def main():
    t0 = time.time()
    days = store.load()
    print("loaded", len(days), "days in", round(time.time() - t0, 1), "s")
    t0 = time.time()
    r = run(StrategyB(), days, {}, 20211115, 20261103)
    print("sim run", round(time.time() - t0, 1), "s")
    py = {d: n for d, n, _, _ in r["daily"] if abs(n) > 0.01}
    rs = {x["id"]: x for x in json.load(open(f"{ROOT}/results/v12/res.json"))["results"]}
    eng = {int(d[0]): d[1] for d in rs[11]["daily"] if abs(d[1]) > 0.01 and d[0] <= 20261103}
    common = sorted(set(py) & set(eng))
    diff = sorted(abs(py[d] - eng[d]) for d in common)
    print(f"engine: days {len(eng)} net {sum(eng.values()):,.0f} | sim: days {len(py)} net {sum(py.values()):,.0f}")
    print(f"common {len(common)}; only engine {len(set(eng) - set(py))}; only sim {len(set(py) - set(eng))}; "
          f"|diff| median {diff[len(diff) // 2]:.0f} p90 {diff[int(len(diff) * .9)]:.0f}; same sign {sum((py[d] > 0) == (eng[d] > 0) for d in common) / len(common) * 100:.1f}%")
    worst = sorted(common, key=lambda d: -abs(py[d] - eng[d]))[:5]
    print("largest gaps:", [(d, round(py[d]), round(eng[d])) for d in worst])
    mg = [mm for _, _, mm, _ in r["daily"] if mm > 0]
    print("sim margin per expiry day: median", round(sorted(mg)[len(mg) // 2]), "max", round(max(mg)))


if __name__ == "__main__":
    main()
