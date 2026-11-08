#!/usr/bin/env python3
"""Discovery v6 — parsimonious pre-declared grid + plateau selection + anchored walk-forward.

Motivation (from v5's walk-forward): a large GA search re-fits a different structure every quarter
(iron fly -> condor -> strangle) and the out-of-sample result is noise. v6 cuts the degrees of freedom
to a small, economically motivated grid and selects by PLATEAU score (the config AND its grid
neighbours must be good), which is the standard cure for parameter-spike overfitting.

Every grid config is backtested ONCE on the full history (daily P&L kept); the walk-forward then
replays selection on train windows from those daily series — no information from a test quarter is
ever used to choose the config traded in it.
"""
import itertools, json, math, os, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5
from stats import deflated_sharpe

WORK = os.path.join(v5.ROOT, "results/v6")
ENTRIES = [5, 30, 60, 90, 120]          # 09:20, 09:45, 10:15, 10:45, 11:15
SLS = [20, 30, 40, 50]


def structures(bucket):
    d0 = bucket == "tdte0"
    out = [("ironfly", {"w": w}) for w in (4, 8, 12)]
    out += [("prem_strangle", {"prem": p, "hprem": 3}) for p in ((25, 40, 60) if d0 else (50, 80, 120))]
    return out


def grid(bucket):
    for si, (fam, sp) in enumerate(structures(bucket)):
        for ei, e in enumerate(ENTRIES):
            for li, sl in enumerate(SLS):
                for tbe in ("none", "sl_legs"):
                    for re in (None, ("cost", 1)):
                        for osl in (0, 2500):
                            p = {"bucket": bucket, "fam": fam, "und": "cash", "entry": e, "exit": 360, "sl": sl, "trail": None, "re": re,
                                 "mom": None, "w": sp.get("w", 6), "n": 2, "prem": sp.get("prem", 50), "hprem": sp.get("hprem", 3), "apct": 30,
                                 "sq": "partial", "tbe": tbe, "osl": osl, "otgt": 0, "lock": None}
                            yield (si, ei, li, tbe, re is not None, osl), p


def neighbours_key(k, nstruct):
    si, ei, li, tbe, re, osl = k
    out = []
    for d in (-1, 1):
        if 0 <= ei + d < len(ENTRIES):
            out.append((si, ei + d, li, tbe, re, osl))
        if 0 <= li + d < len(SLS):
            out.append((si, ei, li + d, tbe, re, osl))
        sj = si + d  # neighbouring structure parameter within the same family block of 3
        if 0 <= sj < nstruct and sj // 3 == si // 3:
            out.append((sj, ei, li, tbe, re, osl))
    return out


def win_metrics(series, a, b):
    """series: list of (date, net) for all trading days -> metrics on [a, b]."""
    xs = [(d, x) for d, x in series if a <= d <= b]
    if not xs:
        return None
    pnl = [x for _, x in xs]
    traded = [x for x in pnl if x != 0]
    c = p = dd = 0.0
    for x in pnl:
        c += x
        p = max(p, c)
        dd = max(dd, p - c)
    years = len(pnl) / 252
    net = sum(pnl)
    w = sum(x for x in traded if x > 0)
    l = -sum(x for x in traded if x < 0)
    q = defaultdict(float)
    for d, x in xs:
        q[(d // 10000, ((d // 100) % 100 - 1) // 3)] += x
    pos_q = sum(1 for v in q.values() if v > 0) / len(q)
    half = len(xs) // 2
    halves_ok = sum(pnl[:half]) > 0 and sum(pnl[half:]) > 0
    return {"net": net, "dd": dd, "calmar": (net / years / dd) if dd > 0 else (99 if net > 0 else 0), "pf": (w / l) if l > 0 else (99 if w > 0 else 0),
            "n": len(traded), "cons": pos_q * pos_q if halves_ok else 0.0, "worst": min(traded) if traded else 0}


def score(m):
    if not m or m["n"] < 8 or m["net"] <= 0:
        return -1.0
    return min(m["calmar"], 20) * min(m["pf"], 3) * m["cons"]


def select(series_by_key, keys, nstruct, a, b):
    sc = {k: score(win_metrics(series_by_key[k], a, b)) for k in keys}
    best, bk = -1e9, None
    for k in keys:
        nb = [sc[n] for n in neighbours_key(k, nstruct) if n in sc]
        plateau = (sc[k] + sum(nb)) / (1 + len(nb)) if sc[k] > 0 else -1
        # a config whose neighbourhood is mostly losing is a spike: penalise
        if nb and sum(1 for x in nb if x > 0) / len(nb) < 0.6:
            plateau = -1
        if plateau > best:
            best, bk = plateau, k
    return bk, best


def main():
    t0 = time.time()
    os.makedirs(WORK, exist_ok=True)
    v5.WORK = WORK  # keep batch scratch files separate from v5
    ds = v5.dates()
    folds = [d for q, d in v5.quarter_starts(ds) if d >= 20240701]
    out = {"buckets": {}, "folds": folds}
    n_trials = 0
    all_sr = []
    for bucket in v5.BUCKETS:
        g = list(grid(bucket))
        items = [(json.dumps(k), v5.build(p), (ds[0], ds[-1])) for k, p in g]
        res = v5.run_batch(items, with_daily=True)
        series = {}
        params = {}
        for k, p in g:
            r = res.get(json.dumps(k))
            if not r:
                continue
            series[k] = [(int(d[0]), d[1]) for d in r["daily"]]
            params[k] = p
            all_sr.append(r["summary_metrics"]["sharpe_ratio"] / math.sqrt(252))
        n_trials += len(series)
        keys = list(series)
        nstruct = len(structures(bucket))
        wf, picks = [], []
        for i, f0 in enumerate(folds):
            f1 = folds[i + 1] if i + 1 < len(folds) else 99999999
            tr_end = max(d for d in ds if d < f0)
            k, s = select(series, keys, nstruct, ds[0], tr_end)
            picks.append({"fold": f0, "key": list(k) if k else None, "plateau": s, "fam": params[k]["fam"] if k else None})
            if k and s > 0:
                wf += [(d, x) for d, x in series[k] if f0 <= d < f1]
            else:
                wf += [(d, 0.0) for d, x in series[keys[0]] if f0 <= d < f1]
        kf, sf = select(series, keys, nstruct, ds[0], ds[-1])
        out["buckets"][bucket] = {"wf_oos": wf, "wf_picks": picks, "final_key": list(kf), "final_plateau": sf,
                                  "final_params": params[kf], "final_cfg": v5.build(params[kf]), "final_series": series[kf],
                                  "final_full": win_metrics(series[kf], ds[0], ds[-1]), "wf_metrics": win_metrics(wf, folds[0], ds[-1])}
        wm = out["buckets"][bucket]["wf_metrics"]
        print(f"{bucket}: {len(keys)} configs | WF OOS net {wm['net']:,.0f} PF {wm['pf']:.2f} DD {wm['dd']:,.0f} | picks "
              + ", ".join(f"{p['fam']}" for p in picks) + f" | final {params[kf]['fam']} plateau {sf:.2f} [{time.time() - t0:.0f}s]", flush=True)
    mu = sum(all_sr) / len(all_sr)
    out["var_sr"] = sum((s - mu) ** 2 for s in all_sr) / (len(all_sr) - 1)
    out["n_trials_v6"] = n_trials
    json.dump(out, open(os.path.join(WORK, "v6_summary.json"), "w"))
    print("done", n_trials, f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
