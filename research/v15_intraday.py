#!/usr/bin/env python3
"""v15: strictly intraday basket on NIFTY weekly options, every trading day (Python simulator, research/sim).

Base strategies (1 lot, all exits by 15:15):
  SELL  : 09:20 sell ATM CE+PE, wings at +/- W % of spot (W in {1, 2}), leg SL {30, 50} %, trail other short to cost after
          the first stop, overall stop Rs {2000, 3000}, entry {09:20, 10:00}
  ORB   : opening range of spot from 09:15 to {09:30, 09:45}; first 1-min close above the high -> buy ATM CE, below the low ->
          buy ATM PE (one trade a day, until 13:00); leg SL {25, 35} % of premium; trailing: after +{30, 60} % keep 50 % of the gain
  MOM   : from 09:20, buy the ATM CE or PE whose premium first rises {15, 25} % above its 09:20 price (until 13:00);
          SL {20, 30} % below the trigger, same trailing as ORB
Signal layer (pre-declared): features gap_abs, or5_pct, prev_range_pct, vix, iv, iv_rank, iv_rv5, pcr, tdte. For each base
config x feature, days are cut into terciles at SELECTION-period quantiles; the best tercile on SELECTION (by net, needing
>= 60 trades) becomes the filter, then it is reported on OLD and NEW without change.
Protocol: SELECTION 2024-01-01..2026-03-24, TEST once OLD 2021-11-15..2023-12-31 and NEW 2026-03-25..2026-11-06.
Writes results/v15/base.json (daily series) and results/v15/filters.json
"""
import itertools, json, math, os, sys, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim"))
import numpy as np
import store, features as F
from engine import IDX, Strategy, run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results/v15")
os.makedirs(OUT, exist_ok=True)
SEL, OLD, NEW = (20240101, 20260324), (20211115, 20231231), (20260325, 20261106)
EXIT = IDX("15:15")
LAST_ENTRY = IDX("13:00")


class Sell(Strategy):
    def __init__(self, entry, wing_pct, sl, osl):
        self.me, self.w, self.sl, self.osl = IDX(entry), wing_pct, sl, osl
        self.name = f"SELL|{entry}|w{wing_pct}%|sl{sl}|osl{osl}"

    def on_day(self, ctx):
        self.e = ctx.expiries[0] if ctx.expiries else None
        self.active, self.trailed = False, False

    def on_minute(self, ctx, m):
        if self.e is None:
            return
        if m == self.me:
            k, s = ctx.atm(m), ctx.spot(m)
            if k is None or ctx.px(self.e, k, "CE", m) is None or ctx.px(self.e, k, "PE", m) is None:
                return
            d = int(round(s * self.w / 100 / 50) * 50)
            if ctx.px(self.e, k + d, "CE", m) is None or ctx.px(self.e, k - d, "PE", m) is None:
                return
            ctx.open(self.e, k + d, "CE", "B", 1, m, "wing")
            ctx.open(self.e, k - d, "PE", "B", 1, m, "wing")
            for opt in ("CE", "PE"):
                leg = ctx.open(self.e, k, opt, "S", 1, m, "short")
                leg.sl = leg.entry * (1 + self.sl / 100)
            self.active = True
        elif self.active and ctx.legs and (m >= EXIT or ctx.mtm(m) <= -self.osl):
            ctx.close_all(m, "time" if m >= EXIT else "overall SL")
            self.active = False

    def on_stop(self, ctx, legs, m):
        if not self.trailed and any(l.side == "S" for l in legs):
            for l in ctx.legs:
                if l.side == "S":
                    l.sl = l.entry
            self.trailed = True


class Long(Strategy):
    """ORB or momentum entry, one long ATM option a day, SL + ratchet trailing."""

    def __init__(self, kind, param, sl, trail_at):
        self.kind, self.p, self.sl, self.ta = kind, param, sl, trail_at
        self.name = f"{kind}|{param}|sl{sl}|trail{trail_at}"

    def on_day(self, ctx):
        self.e = ctx.expiries[0] if ctx.expiries else None
        self.done, self.leg, self.ref, self.peak = False, None, None, None
        self.hi = self.lo = None

    def on_minute(self, ctx, m):
        if self.e is None:
            return
        if self.leg is not None:
            if self.leg not in ctx.legs:  # stopped
                self.leg = None
                return
            p = ctx.px(self.e, self.leg.strike, self.leg.opt, m)
            if p is not None:
                self.peak = max(self.peak, p)
                gain = self.peak - self.leg.entry
                if gain >= self.ta / 100 * self.leg.entry:  # ratchet: keep 50 % of the best gain
                    self.leg.sl = max(self.leg.sl, self.leg.entry + 0.5 * gain)
            if m >= EXIT:
                ctx.close_all(m, "time")
                self.leg = None
            return
        if self.done or m > LAST_ENTRY:
            return
        side = None
        if self.kind == "ORB":
            end = IDX(self.p)
            s = ctx.day["spot"]
            if m <= end:
                return
            if self.hi is None:
                self.hi, self.lo = float(np.nanmax(s[:end + 1, 1])), float(np.nanmin(s[:end + 1, 2]))
            c = ctx.spot(m)
            if c is None:
                return
            side = "CE" if c > self.hi else "PE" if c < self.lo else None
        else:  # MOM
            m0 = IDX("09:20")
            if m < m0:
                return
            if m == m0:
                k = ctx.atm(m)
                self.ref = (k, ctx.px(self.e, k, "CE", m), ctx.px(self.e, k, "PE", m))
                return
            k, rc, rp = self.ref
            if not rc or not rp:
                self.done = True
                return
            c, p = ctx.px(self.e, k, "CE", m), ctx.px(self.e, k, "PE", m)
            if c and c >= rc * (1 + self.p / 100):
                side = "CE"
            elif p and p >= rp * (1 + self.p / 100):
                side = "PE"
        if side:
            k = ctx.atm(m) if self.kind == "ORB" else self.ref[0]
            leg = ctx.open(self.e, k, side, "B", 1, m, self.kind)
            self.done = True
            if leg:
                leg.sl = leg.entry * (1 - self.sl / 100)
                self.leg, self.peak = leg, leg.entry


def configs():
    out = [Sell(e, w, sl, osl) for e, w, sl, osl in itertools.product(["09:20", "10:00"], [1, 2], [30, 50], [2000, 3000])]
    out += [Long("ORB", end, sl, ta) for end, sl, ta in itertools.product(["09:30", "09:45"], [25, 35], [30, 60])]
    out += [Long("MOM", mom, sl, ta) for mom, sl, ta in itertools.product([15, 25], [20, 30], [30, 60])]
    return out


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
    return {"trades": len(tr), "net": round(eq), "pf": round(gw / gl, 2) if gl else 0, "dd": round(dd),
            "win_months": round(sum(x > 0 for x in mv) / len(mv) * 100, 1) if mv else 0, "per_year": round(eq / max(len(s) / 248, 1e-9))}


FEATS = ["gap_abs", "or5_pct", "prev_range_pct", "vix", "iv", "iv_rank", "iv_rv5", "pcr", "tdte"]


def main():
    days, feat = store.load(), F.load()
    for d, f in feat.items():
        f["gap_abs"] = abs(f["gap_pct"]) if f.get("gap_pct") is not None else None
    base = {}
    for st in configs():
        r = run(st, days, feat, OLD[0], NEW[1])
        base[st.name] = [(d, n) for d, n, _, _ in r["daily"]]
        print(f"{st.name:34s}", " | ".join(f"{k} {met(base[st.name], *v).get('pf', 0):.2f}/{met(base[st.name], *v).get('net', 0):>7}" for k, v in (("OLD", OLD), ("SEL", SEL), ("NEW", NEW))), flush=True)
    json.dump(base, open(f"{OUT}/base.json", "w"))
    # signal layer
    res = []
    for name, s in base.items():
        for fe in FEATS:
            sel_vals = [feat[d].get(fe) for d, n in s if SEL[0] <= d <= SEL[1] and d in feat and feat[d].get(fe) is not None]
            if len(sel_vals) < 150:
                continue
            q1, q2 = np.quantile(sel_vals, [1 / 3, 2 / 3])
            if fe == "tdte":
                bins = [("tdte=0", lambda v: v == 0), ("tdte=1-2", lambda v: 1 <= v <= 2), ("tdte>=3", lambda v: v >= 3)]
            else:
                bins = [(f"{fe}<{q1:.3g}", lambda v, q1=q1: v < q1), (f"{q1:.3g}<={fe}<{q2:.3g}", lambda v, q1=q1, q2=q2: q1 <= v < q2), (f"{fe}>={q2:.3g}", lambda v, q2=q2: v >= q2)]
            best = None
            for lab, fn in bins:
                fs = [(d, n if (d in feat and feat[d].get(fe) is not None and fn(feat[d][fe])) else 0.0) for d, n in s]
                ms = met(fs, *SEL)
                if ms.get("trades", 0) >= 60 and (best is None or ms["net"] > best[1]["net"]):
                    best = (lab, ms, fs)
            if best:
                lab, ms, fs = best
                res.append({"base": name, "feature": fe, "rule": lab, "SEL": ms, "OLD": met(fs, *OLD), "NEW": met(fs, *NEW)})
    json.dump(res, open(f"{OUT}/filters.json", "w"), indent=1)
    good = [r for r in res if r["SEL"]["pf"] >= 1.2]
    print(f"\nfilters: {len(res)} tested, {len(good)} with SELECTION PF >= 1.2; their test results:")
    for r in sorted(good, key=lambda r: -r["SEL"]["pf"])[:25]:
        print(f"  {r['base']:34s} {r['rule']:28s} SEL pf {r['SEL']['pf']:.2f} n{r['SEL']['trades']:>4} net {r['SEL']['net']:>7} | "
              f"OLD pf {r['OLD'].get('pf', 0):.2f} net {r['OLD'].get('net', 0):>7} | NEW pf {r['NEW'].get('pf', 0):.2f} net {r['NEW'].get('net', 0):>7}")


if __name__ == "__main__":
    main()
