#!/usr/bin/env python3
"""v16b: fewer, bigger intraday NIFTY futures trend trades so the gross edge clears ~19 pts of cost per round trip.

v16 showed a real gross trend edge (ORB PF 1.15-1.29, EMA 20/50 PF 1.29 before costs) that today's costs (~15 pts + ~4 pts
slippage) consume. Here: one trade a day at most, later/stronger triggers, hold to 15:25, plus day filters.
Bases (pre-declared):
  ORBL  opening range to {10:15, 11:15}, buffer {0.1, 0.2} %, entry by 13:00, stop at the opposite side, exit 15:25
  PDB   break of the previous day's high/low (1-min close beyond it, +{0, 0.1} %) between 09:30 and 13:00; stop {opposite
        extreme of the day so far, 0.6 %}; exit 15:25
  EMA15 first 15-min EMA(20, 50) cross after 10:15 (bars end :29/:44/...), held to 15:25 with a 0.6 % stop
Day filters (known before the entry): vix, or_ratio (09:15-10:14 range / VIX-expected 1-hour sigma), gap_abs, prev_range.
Selection on 2015-2020: best tercile per base x feature (>= 150 trades); tested once on 2021-23 and 2024-26.
"""
import itertools, json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import futsim as F
import v16_futures as V

M, EXIT = F.M, F.M("15:25")


def orbl(px, prev, end, buf, **_):
    E = M(end)
    hi, lo = float(px[:E, 1].max()), float(px[:E, 2].min())
    for m in range(E, M("13:00")):
        c = float(px[m, 3])
        d = 1 if c > hi * (1 + buf) else -1 if c < lo * (1 - buf) else 0
        if d:
            p, e, x, _, _ = F.trade(px, m, d, stop=lo if d > 0 else hi, exit_m=EXIT)
            return V.rs(p, e, x, d)
    return 0.0


def pdb(px, prev, ph, pl_, buf, stop, **_):
    for m in range(M("09:30"), M("13:00")):
        c = float(px[m, 3])
        d = 1 if c > ph * (1 + buf) else -1 if c < pl_ * (1 - buf) else 0
        if d:
            st = (float(px[:m + 1, 2].min()) if d > 0 else float(px[:m + 1, 1].max())) if stop == "ext" else c * (1 - d * 0.006)
            p, e, x, _, _ = F.trade(px, m, d, stop=st, exit_m=EXIT)
            return V.rs(p, e, x, d)
    return 0.0


def ema15(px, prev, **_):
    c15 = px[14::15, 3].astype(float)  # bars ending 09:29, 09:44, ...
    af, asl = 2 / 21, 2 / 51
    ef = es = c15[0]
    last = None
    for j in range(1, len(c15)):
        ef, es = af * c15[j] + (1 - af) * ef, asl * c15[j] + (1 - asl) * es
        m = 14 + 15 * j
        side = 1 if ef > es else -1
        if m >= M("10:15") and last is not None and side != last and m < M("14:30"):
            c = float(px[m, 3])
            p, e, x, _, _ = F.trade(px, m, side, stop=c * (1 - side * 0.006), exit_m=EXIT)
            return V.rs(p, e, x, side)
        last = side
    return 0.0


def bases():
    b = [(f"ORBL|{end}|b{buf}", orbl, dict(end=end, buf=buf)) for end, buf in itertools.product(["10:15", "11:15"], [0.001, 0.002])]
    b += [(f"PDB|b{buf}|{st}", pdb, dict(buf=buf, stop=st)) for buf, st in itertools.product([0.0, 0.001], ["ext", "pct"])]
    b += [("EMA15|20/50", ema15, {})]
    return b


def main():
    dates, px, vix = F.load()
    feats = {}
    for i in range(1, len(dates)):
        prev = float(px[i - 1, 374, 3])
        v = float(vix[i])
        o = float(px[i, 0, 0])
        hr = float(px[i, :60, 1].max() - px[i, :60, 2].min())
        exp1h = (v / 100 / math.sqrt(252) * o * math.sqrt(60 / 375)) if not math.isnan(v) else None
        feats[int(dates[i])] = {"vix": None if math.isnan(v) else v, "or_ratio": hr / exp1h if exp1h else None, "gap_abs": abs(o / prev - 1) * 100,
                                "prev_range": float(px[i - 1, :, 1].max() - px[i - 1, :, 2].min()) / prev * 100}
    rows = []
    for name, fn, kw in bases():
        s = []
        for i in range(1, len(dates)):
            prev = float(px[i - 1, 374, 3])
            kw2 = dict(kw, ph=float(px[i - 1, :, 1].max()), pl_=float(px[i - 1, :, 2].min()))
            s.append((int(dates[i]), fn(px[i], prev, **kw2)))
        base = {k: V.met(s, *rng) for k, rng in (("SEL", V.SEL), ("T1", V.T1), ("T2", V.T2))}
        print(f"{name:20s} unfiltered | " + " | ".join(f"{k} pf {m['pf']:.2f} /yr {m['per_year']:>7} n{m['trades']}" for k, m in base.items()), flush=True)
        for fe in ("vix", "or_ratio", "gap_abs", "prev_range"):
            vals = [feats[d][fe] for d, _ in s if V.SEL[0] <= d <= V.SEL[1] and feats.get(d, {}).get(fe) is not None]
            q1, q2 = np.quantile(vals, [1 / 3, 2 / 3])
            best = None
            for lab, fnb in ((f"{fe}<{q1:.3g}", lambda x: x < q1), (f"{q1:.3g}-{q2:.3g}", lambda x: q1 <= x < q2), (f"{fe}>={q2:.3g}", lambda x: x >= q2)):
                fs = [(d, n if feats.get(d, {}).get(fe) is not None and fnb(feats[d][fe]) else 0.0) for d, n in s]
                ms = V.met(fs, *V.SEL)
                if ms["trades"] >= 150 and (best is None or ms["net"] > best[1]["net"]):
                    best = (lab, ms, fs)
            if best:
                lab, ms, fs = best
                t1, t2 = V.met(fs, *V.T1), V.met(fs, *V.T2)
                rows.append({"base": name, "rule": lab, "SEL": ms, "T1": t1, "T2": t2})
                print(f"    filter {lab:22s} SEL pf {ms['pf']:.2f} /yr {ms['per_year']:>7} n{ms['trades']:>4} | T1 pf {t1['pf']:.2f} /yr {t1['per_year']:>7} | T2 pf {t2['pf']:.2f} /yr {t2['per_year']:>7}", flush=True)
    json.dump(rows, open(os.path.join(V.OUT, "trend_filters.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
