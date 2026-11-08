#!/usr/bin/env python3
"""Discovery v7 — two pre-declared hypotheses, judged ONLY by anchored walk-forward with plateau selection.

H1 (refine the expiry-day iron fly that survived v6): AlgoTest-expressible dimensions only —
    wings {4,8,12} x entry {09:20,09:30,09:45} x leg SL {40,50,60,70}% x overall SL {2000,2500,3500}
    x Lock&Trail {off, reach 3000/lock 1000/every 500/by 250} x RE-COST {off, 1}; trail-SL-to-BE on SL legs.
H2 (afternoon theta on non-expiry days, trading DTE 1..4): iron fly wings {4,8,12} x entry {12:15,13:00,13:45}
    x leg SL {20,30,40,50}% x trail-to-BE {off, SL legs} x overall SL {0, 1500}; exit 15:15.
"""
import itertools, json, math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5
import discover_v6 as v6

WORK = os.path.join(v5.ROOT, "results/v7")


def base(bucket):
    return {"bucket": bucket, "fam": "ironfly", "und": "cash", "entry": 5, "exit": 360, "sl": 50, "trail": None, "re": None, "mom": None,
            "w": 12, "n": 2, "prem": 50, "hprem": 3, "apct": 30, "sq": "partial", "tbe": "sl_legs", "osl": 2500, "otgt": 0, "lock": None}


H1 = {"w": [4, 8, 12], "entry": [5, 15, 30], "sl": [40, 50, 60, 70], "osl": [2000, 2500, 3500],
      "lock": [None, (3000, 1 / 3, 500)], "re": [None, ("cost", 1)]}
H2 = {"w": [4, 8, 12], "entry": [180, 225, 270], "sl": [20, 30, 40, 50], "tbe": ["none", "sl_legs"], "osl": [0, 1500]}


def grid(bucket, dims):
    names = list(dims)
    for idx in itertools.product(*[range(len(dims[n])) for n in names]):
        p = base(bucket)
        for n, i in zip(names, idx):
            p[n] = dims[n][i]
        yield idx, p


def neighbours(idx, dims):
    names = list(dims)
    out = []
    for j, n in enumerate(names):
        for d in (-1, 1):
            k = idx[j] + d
            if 0 <= k < len(dims[n]):
                out.append(idx[:j] + (k,) + idx[j + 1:])
    return out


def select(series, keys, dims, a, b):
    sc = {k: v6.score(v6.win_metrics(series[k], a, b)) for k in keys}
    best, bk = -1e9, None
    for k in keys:
        nb = [sc[n] for n in neighbours(k, dims) if n in sc]
        if sc[k] <= 0 or (nb and sum(1 for x in nb if x > 0) / len(nb) < 0.6):
            continue
        pl = (sc[k] + sum(nb)) / (1 + len(nb))
        if pl > best:
            best, bk = pl, k
    return bk, best


def run(bucket, dims, ds, folds, tag):
    g = list(grid(bucket, dims))
    res = v5.run_batch([(json.dumps(k), v5.build(p), (ds[0], ds[-1])) for k, p in g], with_daily=True)
    series, params, srs = {}, {}, []
    for k, p in g:
        r = res.get(json.dumps(k))
        if r:
            series[k] = [(int(d[0]), d[1]) for d in r["daily"]]
            params[k] = p
            srs.append(r["summary_metrics"]["sharpe_ratio"] / math.sqrt(252))
    keys = list(series)
    wf, picks = [], []
    for i, f0 in enumerate(folds):
        f1 = folds[i + 1] if i + 1 < len(folds) else 99999999
        k, s = select(series, keys, dims, ds[0], max(d for d in ds if d < f0))
        picks.append({"fold": f0, "key": list(k) if k else None, "plateau": s})
        src = series[k] if k else [(d, 0.0) for d, _ in series[keys[0]]]
        wf += [(d, x) for d, x in src if f0 <= d < f1]
    kf, sf = select(series, keys, dims, ds[0], ds[-1])
    rec = {"tag": tag, "bucket": bucket, "dims": {n: [str(x) for x in v] for n, v in dims.items()}, "wf_oos": wf, "wf_picks": picks,
           "wf_metrics": v6.win_metrics(wf, folds[0], ds[-1]), "n": len(keys), "srs": srs}
    if kf:
        rec.update({"final_key": list(kf), "final_plateau": sf, "final_params": params[kf], "final_cfg": v5.build(params[kf]),
                    "final_series": series[kf], "final_full": v6.win_metrics(series[kf], ds[0], ds[-1])})
    wm = rec["wf_metrics"]
    print(f"{tag} {bucket}: {len(keys)} cfgs | WF OOS net {wm['net']:,.0f} PF {wm['pf']:.2f} DD {wm['dd']:,.0f} trades {wm['n']} | "
          f"picks {[p['key'] for p in picks]} | final {rec.get('final_key')}", flush=True)
    return rec


def main():
    os.makedirs(WORK, exist_ok=True)
    v5.WORK = WORK
    ds = v5.dates()
    folds = [d for q, d in v5.quarter_starts(ds) if d >= 20240701]
    out = {"folds": folds, "runs": []}
    out["runs"].append(run("tdte0", H1, ds, folds, "H1"))
    for b in ("tdte1", "tdte2", "tdte3", "tdte4"):
        out["runs"].append(run(b, H2, ds, folds, "H2"))
    json.dump(out, open(os.path.join(WORK, "v7_summary.json"), "w"))


if __name__ == "__main__":
    main()
