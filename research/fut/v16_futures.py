#!/usr/bin/env python3
"""v16: intraday NIFTY futures strategy discovery, 11 years (2015-01 .. 2026-11), flat by 15:25 every day, 1 lot (65).

Protocol (pre-declared): SELECT on 2015-01-09..2020-12-31 only; TEST once on 2021-01-01..2023-12-31 and 2024-01-01..2026-11-06.
Costs at today's rates (~Rs 960 = ~15 pts per round trip) + 1 pt slippage per fill + 1 pt extra on stops (research/fut/futsim.py).
Families:
  ORB   opening range to {09:30, 09:45, 10:15}; enter on the first 1-min close beyond it (+{0, 0.1} % buffer) before 12:00;
        stop {opposite side, mid-range}; exit {15:25, 2R target, trailing 0.4 % of price}
  MOMC  intraday momentum into the close: sign of the return from the previous close to {09:45, 14:30}; enter at {14:30, 15:00}
        if |return| > {0, 0.3} %; exit 15:25 (no stop)
  EMA   5-min EMA({9,21}, {20,50}) cross after 09:45; always-in after the first cross, flip on opposite cross; flat at 15:25
  MR    fade a move of k = {1.5, 2.0} expected sigmas from the day's open (sigma from the 09:15 VIX), 10:00-14:00 entries;
        target the open, stop at k+1 sigma; exit 15:25
  GAP   |gap| > {0.3, 0.6} %: "fade" (enter 09:20 against the gap, target previous close, stop at 1.5x gap) or
        "go" (at 09:30 if price is beyond the open in the gap direction, stop at the day's opposite extreme, trail 0.4 %)
Writes results/v16/all.json (+ daily series in results/v16/daily.json)
"""
import itertools, json, math, os, sys, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import futsim as F

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "results/v16")
os.makedirs(OUT, exist_ok=True)
SEL, T1, T2 = (20150101, 20201231), (20210101, 20231231), (20240101, 20261231)
M = F.M
EXIT = M("15:25")


def rs(pts, e, x, d):
    return pts * F.LOT - F.cost(e, x, d)


def orb(px, prev, end, buf, stop_mode, exit_mode, **_):
    E = M(end)
    hi, lo = float(px[:E, 1].max()), float(px[:E, 2].min())
    for m in range(E, M("12:00")):
        c = float(px[m, 3])
        d = 1 if c > hi * (1 + buf) else -1 if c < lo * (1 - buf) else 0
        if d:
            st = (lo if d > 0 else hi) if stop_mode == "opp" else (hi + lo) / 2
            e = c + d * F.SLIP
            risk = abs(e - st)
            tgt = e + d * 2 * risk if exit_mode == "2R" else None
            tr = 0.004 * c if exit_mode == "trail" else None
            p, e, x, _, _ = F.trade(px, m, d, stop=st, target=tgt, trail=tr, exit_m=EXIT)
            return rs(p, e, x, d)
    return 0.0


def momc(px, prev, sig_end, entry, thr, **_):
    r = float(px[M(sig_end) - 1, 3]) / prev - 1
    if abs(r) <= thr:
        return 0.0
    d = 1 if r > 0 else -1
    p, e, x, _, _ = F.trade(px, M(entry), d, exit_m=EXIT)
    return rs(p, e, x, d)


def ema_sys(px, prev, fast, slow, **_):
    c5 = px[4::5, 3].astype(float)  # 5-min closes (bar ends 09:19, 09:24, ...)
    af, aslow = 2 / (fast + 1), 2 / (slow + 1)
    ef = es = c5[0]
    pos, e, total = 0, None, 0.0
    start = 6  # first signal after 09:45
    for j in range(1, len(c5)):
        ef = af * c5[j] + (1 - af) * ef
        es = aslow * c5[j] + (1 - aslow) * es
        m = 4 + 5 * j
        if m > EXIT:
            break
        want = 1 if ef > es else -1
        if j >= start and want != pos:
            if pos:
                x = float(px[m, 3]) - pos * F.SLIP
                total += rs(pos * (x - e), e, x, pos)
            pos, e = want, float(px[m, 3]) + want * F.SLIP
    if pos:
        x = float(px[EXIT, 3]) - pos * F.SLIP
        total += rs(pos * (x - e), e, x, pos)
    return total


def mr(px, prev, k, vix, **_):
    if not vix or math.isnan(vix):
        return 0.0
    o = float(px[0, 0])
    sd_day = vix / 100 / math.sqrt(252) * o
    for m in range(M("10:00"), M("14:00")):
        c = float(px[m, 3])
        z = (c - o) / (sd_day * math.sqrt((m + 1) / 375))
        if abs(z) > k:
            d = -1 if z > 0 else 1
            st = o + (-d) * (k + 1) * sd_day * math.sqrt((m + 1) / 375)
            p, e, x, _, _ = F.trade(px, m, d, stop=st, target=o, exit_m=EXIT)
            return rs(p, e, x, d)
    return 0.0


def gap(px, prev, thr, mode, **_):
    o = float(px[0, 0])
    g = o / prev - 1
    if abs(g) <= thr:
        return 0.0
    if mode == "fade":
        d = -1 if g > 0 else 1
        st = prev * (1 + 1.5 * g)
        p, e, x, _, _ = F.trade(px, M("09:20"), d, stop=st, target=prev, exit_m=EXIT)
        return rs(p, e, x, d)
    m = M("09:30")
    c = float(px[m, 3])
    d = 1 if g > 0 else -1
    if d * (c - o) <= 0:
        return 0.0
    st = float(px[:m + 1, 2].min()) if d > 0 else float(px[:m + 1, 1].max())
    p, e, x, _, _ = F.trade(px, m, d, stop=st, trail=0.004 * c, exit_m=EXIT)
    return rs(p, e, x, d)


def grid():
    g = []
    for end, buf, sm, em in itertools.product(["09:30", "09:45", "10:15"], [0.0, 0.001], ["opp", "mid"], ["time", "2R", "trail"]):
        g.append((f"ORB|{end}|b{buf}|{sm}|{em}", orb, dict(end=end, buf=buf, stop_mode=sm, exit_mode=em)))
    for se, en, th in itertools.product(["09:45", "14:30"], ["14:30", "15:00"], [0.0, 0.003]):
        if M(en) >= M(se):
            g.append((f"MOMC|sig{se}|in{en}|thr{th}", momc, dict(sig_end=se, entry=en, thr=th)))
    for fa, sl in ((9, 21), (20, 50)):
        g.append((f"EMA|{fa}/{sl}", ema_sys, dict(fast=fa, slow=sl)))
    for k in (1.5, 2.0):
        g.append((f"MR|k{k}", mr, dict(k=k)))
    for th, mo in itertools.product([0.003, 0.006], ["fade", "go"]):
        g.append((f"GAP|{th}|{mo}", gap, dict(thr=th, mode=mo)))
    return g


def met(s, a, b):
    s = [(d, n) for d, n in s if a <= d <= b]
    eq = peak = dd = 0.0
    mo = collections.defaultdict(float)
    for d, n in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        mo[d // 100] += n
    tr = [n for _, n in s if n != 0]
    gw, gl = sum(x for x in tr if x > 0), -sum(x for x in tr if x < 0)
    mv = list(mo.values())
    yrs = len(s) / 248 if s else 1
    return {"trades": len(tr), "net": round(eq), "per_year": round(eq / yrs), "pf": round(gw / gl, 2) if gl else 0, "dd": round(dd),
            "win_rate": round(sum(x > 0 for x in tr) / len(tr) * 100, 1) if tr else 0,
            "win_months": round(sum(x > 0 for x in mv) / len(mv) * 100, 1) if mv else 0}


def main():
    dates, px, vix = F.load()
    out, daily = [], {}
    for name, fn, kw in grid():
        s = []
        for i in range(1, len(dates)):
            prev = float(px[i - 1, 374, 3])
            s.append((int(dates[i]), fn(px[i], prev, vix=float(vix[i]), **kw)))
        r = {"name": name, "SEL": met(s, *SEL), "T1": met(s, *T1), "T2": met(s, *T2), "ALL": met(s, 0, 99999999)}
        out.append(r)
        daily[name] = s
        print(f"{name:32s} SEL pf {r['SEL']['pf']:.2f} n{r['SEL']['trades']:>4} /yr {r['SEL']['per_year']:>7} | T1 pf {r['T1']['pf']:.2f} /yr {r['T1']['per_year']:>7} | T2 pf {r['T2']['pf']:.2f} /yr {r['T2']['per_year']:>7}", flush=True)
    json.dump(out, open(f"{OUT}/all.json", "w"), indent=1)
    json.dump(daily, open(f"{OUT}/daily.json", "w"))


if __name__ == "__main__":
    main()
