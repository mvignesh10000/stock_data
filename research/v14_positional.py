#!/usr/bin/env python3
"""v14: positional weekly short-volatility on NIFTY (held overnight to expiry), Python simulator (research/sim).

Motivation (research/sim, VRP table): selling the ATM straddle 2-4 trading days before expiry and holding to expiry earns
~Rs 1.3-1.6k per lot per week before costs (intraday on the same days: ~zero after costs), with fat tails (5 % worst
weeks -Rs 20-25k naked). Goal: keep the premium, cut the tail.

Pre-declared grid (one position per weekly expiry, 1 lot):
  entry day   : tdte in {2, 3, 4}, entry time {09:20, 15:15}
  structure   : "fly" (ATM short straddle) or "strangle" (shorts at premium ~ 0.5 x ATM premium);
                wings {premium Rs 20, 1.5 % of spot beyond the shorts, 3 % beyond}  (premium-priced Rs 5-10 wings are
                ~1,100 pts away at 3 DTE: no real protection, see the 3-Feb-2026 gap in EXPERIMENT_LOG round 9)
  risk        : leg SL {none, 100 % of entry premium}, checked every minute incl. overnight gaps (fill at the open);
                weekly overall stop {Rs 4,000, Rs 8,000} on MTM since entry (checked at minute closes)
  adjustment  : {none, recenter}: if spot moves more than 1 % of the short strike away, close everything and re-open the
                same structure at the new ATM (max 2 recenters a week)
  exit        : expiry day 15:15 (or 09:20 on expiry day: "early" variant, avoids expiry gamma)
Protocol: select on 2024-01-01..2026-03-24, test once on 2021-11-15..2023-12-31 and 2026-03-25..2026-11-06.
Writes results/v14/all.json
"""
import itertools, json, math, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim"))
import store, features as F
from engine import IDX, Strategy, run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/v14")
os.makedirs(OUT, exist_ok=True)
BLOCKS = {"OLD": (20211115, 20231231), "SEL": (20240101, 20260324), "NEW": (20260325, 20261106)}


class Weekly(Strategy):
    def __init__(self, tdte, entry, struct, wing, leg_sl, osl, adjust, exit_):
        self.tdte, self.me, self.struct, self.wing, self.leg_sl, self.osl, self.adjust = tdte, IDX(entry), struct, wing, leg_sl, osl, adjust
        self.mx = IDX("15:15") if exit_ == "close" else IDX("09:20")
        self.pos_e, self.base, self.k0, self.n_adj = None, 0.0, None, 0
        self.name = f"{struct}|T-{tdte}@{entry}|w{wing[0]}{wing[1]}|sl{leg_sl}|osl{osl}|{adjust}|{exit_}"

    def _open(self, ctx, m):
        e = self.pos_e
        k = ctx.atm(m)
        if k is None:
            return False
        if self.struct == "fly":
            kc = kp = k
        else:
            atm_p = ((ctx.px(e, k, "CE", m) or 0) + (ctx.px(e, k, "PE", m) or 0)) / 2
            if atm_p <= 0:
                return False
            kc, kp = ctx.strike_by_premium(e, "CE", 0.5 * atm_p, m), ctx.strike_by_premium(e, "PE", 0.5 * atm_p, m)
        if self.wing[0] == "p":  # wings by premium
            wc, wp = ctx.strike_by_premium(e, "CE", self.wing[1], m), ctx.strike_by_premium(e, "PE", self.wing[1], m)
        else:  # wings by distance (fraction of spot) from the short strikes, on the 50-pt grid
            dist = int(round(ctx.spot(m) * self.wing[1] / 50) * 50)
            wc, wp = kc + dist, kp - dist
        if None in (kc, kp, wc, wp) or wc <= kc or wp >= kp:
            return False
        if None in (ctx.px(e, kc, "CE", m), ctx.px(e, kp, "PE", m), ctx.px(e, wc, "CE", m), ctx.px(e, wp, "PE", m)):
            return False
        ctx.open(e, wc, "CE", "B", 1, m, "wing")
        ctx.open(e, wp, "PE", "B", 1, m, "wing")
        for kk, opt in ((kc, "CE"), (kp, "PE")):
            leg = ctx.open(e, kk, opt, "S", 1, m, "short")
            if self.leg_sl:
                leg.sl = leg.entry * (1 + self.leg_sl / 100)
        self.k0 = k
        return True

    def on_day(self, ctx):
        self.e0 = ctx.expiries[0] if ctx.expiries else None
        if self.pos_e is None and self.e0 is not None and ctx.tdte(self.e0) == self.tdte:
            self.want = True
        else:
            self.want = False

    def on_minute(self, ctx, m):
        if self.want and m == self.me:
            self.pos_e = self.e0
            self.n_adj = 0
            if self._open(ctx, m):
                self.base = ctx.open_pnl(m)  # (~0 apart from slippage) reference for the weekly stop
                self.week_realised = 0.0
                self.closed_before = len(ctx.closed)
            else:
                self.pos_e = None
            self.want = False
            return
        if self.pos_e is None:
            return
        # weekly P&L since entry = realised on this position's legs + open legs
        realised = sum(l.pnl(l.exit) for l in ctx.closed[self.closed_before:])
        wk = realised + ctx.open_pnl(m)
        last_day = ctx.date == self.pos_e
        if wk <= -self.osl or (last_day and m >= self.mx) or not any(l.side == "S" for l in ctx.legs) and last_day:
            ctx.close_all(m, "weekly stop" if wk <= -self.osl else "exit")
            self.pos_e = None
            return
        if self.adjust == "recenter" and self.n_adj < 2 and m % 5 == 0 and not last_day:
            s = ctx.spot(m)
            if s is not None and abs(s - self.k0) > 0.01 * self.k0:
                ctx.close_all(m, "recenter")
                self.n_adj += 1
                self._open(ctx, m)


def met(s, a, b):
    s = [(d, n) for d, n in s if a <= d <= b]
    if not s:
        return {}
    eq = peak = dd = 0.0
    m = collections.defaultdict(float)
    for d, n in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        m[d // 100] += n
    tr = [n for _, n in s if abs(n) > 0.01]
    gw, gl = sum(x for x in tr if x > 0), -sum(x for x in tr if x < 0)
    mv = list(m.values())
    return {"net": round(eq), "pf": round(gw / gl, 2) if gl else 0, "dd": round(dd), "worst_day": round(min(tr)) if tr else 0,
            "win_months": round(sum(x > 0 for x in mv) / len(mv) * 100, 1), "per_year": round(eq / (len(s) / 248))}


def main():
    days, feat = store.load(), F.load()
    grid = list(itertools.product([2, 3, 4], ["09:20", "15:15"], ["fly", "strangle"], [("p", 20), ("d", 0.015), ("d", 0.03)], [0, 100], [4000, 8000], ["none", "recenter"], ["close", "early"]))
    print("configs", len(grid), flush=True)
    out = json.load(open(f"{OUT}/all.json")) if os.path.exists(f"{OUT}/all.json") else []
    done = {r["name"] for r in out}
    for i, g in enumerate(grid):
        st = Weekly(*g)
        if st.name in done:
            continue
        r = run(st, days, feat, 20211115, 20261106)
        s = [(d, n) for d, n, _, _ in r["daily"]]
        mg = sorted(mm for _, _, mm, _ in r["daily"] if mm > 0)
        row = {"name": st.name, "key": g, **{k: met(s, a, b) for k, (a, b) in BLOCKS.items()}, "all": met(s, 0, 99999999),
               "margin_p50": round(mg[len(mg) // 2]) if mg else 0, "margin_max": round(mg[-1]) if mg else 0}
        out.append(row)
        if i % 12 == 0:
            print(i, st.name, row["all"], flush=True)
            json.dump(out, open(f"{OUT}/all.json", "w"), default=list)
    json.dump(out, open(f"{OUT}/all.json", "w"), default=list)
    print("DONE", len(out))


if __name__ == "__main__":
    main()
