#!/usr/bin/env python3
"""Overfitting audit of the finalised expiry-day iron fly.

1. PBO (Probability of Backtest Overfitting, Bailey/Borwein/Lopez de Prado/Zhu 2015) via CSCV on the
   expiry-day grids actually searched (v6: 960 configs, v7-H1: 432 configs).
2. One-shot split: run the SAME selection procedure on 2024 only, freeze the pick, evaluate ONCE on
   Jan-2025..Mar-2026 (never used for that pick).
3. Bootstrap 95% CIs of mean P&L per trade and profit factor; P(mean <= 0).
4. Trade-count check and sub-period stability (each half-year).
"""
import itertools, json, math, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5, discover_v6 as v6, discover_v7 as v7

ROOT = v5.ROOT
OUT = os.path.join(ROOT, "results/audit_v9"); os.makedirs(OUT, exist_ok=True)
v5.WORK = OUT
ds = v5.dates()
info = json.loads(v5.sh([v5.BIN, "info", "--cache", v5.CACHE])); tdte = {d[0]: d[1] for d in info["dates"]}
exp_days = [d for d in ds if tdte[d] == 0]


def grid_series(gen):
    g = list(gen)
    res = v5.run_batch([(json.dumps(k), v5.build(p), (ds[0], ds[-1])) for k, p in g], with_daily=True)
    S, P = {}, {}
    for k, p in g:
        r = res.get(json.dumps(k))
        if r:
            S[k] = {int(d[0]): d[1] for d in r["daily"]}
            P[k] = p
    return S, P


def sharpe(x):
    n = len(x); m = sum(x) / n
    v = sum((a - m) ** 2 for a in x) / max(1, n - 1)
    return m / math.sqrt(v) if v > 0 else 0.0


def pbo(S, days, n_blocks=10):
    keys = list(S)
    M = [[S[k].get(d, 0.0) for k in keys] for d in days]
    T = len(days); bs = T // n_blocks
    blocks = [list(range(i * bs, (i + 1) * bs if i < n_blocks - 1 else T)) for i in range(n_blocks)]
    lam, deg = [], []
    for comb in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_rows = [r for b in comb for r in blocks[b]]
        oos_rows = [r for b in range(n_blocks) if b not in comb for r in blocks[b]]
        is_sr = [sharpe([M[r][j] for r in is_rows]) for j in range(len(keys))]
        oos_sr = [sharpe([M[r][j] for r in oos_rows]) for j in range(len(keys))]
        best = max(range(len(keys)), key=lambda j: is_sr[j])
        rank = sum(1 for x in oos_sr if x < oos_sr[best]) / (len(keys) - 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        lam.append(math.log(rank / (1 - rank)))
        deg.append(oos_sr[best])
    return {"pbo": sum(1 for l in lam if l <= 0) / len(lam), "n_splits": len(lam), "median_logit": sorted(lam)[len(lam) // 2],
            "oos_sharpe_of_is_best_median": sorted(deg)[len(deg) // 2], "p_oos_sharpe_neg": sum(1 for x in deg if x <= 0) / len(deg)}


def boot(x, n=5000, seed=3):
    rng = random.Random(seed)
    means, pfs = [], []
    for _ in range(n):
        s = [rng.choice(x) for _ in x]
        means.append(sum(s) / len(s))
        w = sum(a for a in s if a > 0); l = -sum(a for a in s if a < 0)
        pfs.append(w / l if l > 0 else 99)
    means.sort(); pfs.sort()
    q = lambda a, p: a[int(p * (len(a) - 1))]
    return {"mean": sum(x) / len(x), "mean_ci95": [q(means, .025), q(means, .975)], "pf_ci95": [q(pfs, .025), q(pfs, .975)], "p_mean_le_0": sum(1 for m in means if m <= 0) / len(means)}


def main():
    out = {}
    S6, P6 = grid_series(v6.grid("tdte0"))
    S7, P7 = grid_series(v7.grid("tdte0", v7.H1))
    out["pbo_v6"] = pbo(S6, exp_days)
    out["pbo_v7"] = pbo(S7, exp_days)
    print("PBO v6 grid:", out["pbo_v6"]); print("PBO v7 grid:", out["pbo_v7"])
    # one-shot split: select on 2024 only with the same plateau procedure, evaluate once on 2025-26
    d24 = [d for d in ds if d < 20250101]
    for name, S, P, dims in (("v6", S6, P6, None), ("v7", S7, P7, v7.H1)):
        ser = {k: [(d, s.get(d, 0.0)) for d in ds] for k, s in S.items()}
        if dims is None:
            k, sc = v6.select(ser, list(ser), len(v6.structures("tdte0")), d24[0], d24[-1])
        else:
            k, sc = v7.select(ser, list(ser), dims, d24[0], d24[-1])
        test = [x for d, x in ser[k] if d >= 20250101 and tdte[d] == 0]
        train = [x for d, x in ser[k] if d < 20250101 and tdte[d] == 0]
        w = sum(a for a in test if a > 0); l = -sum(a for a in test if a < 0)
        c = p = dd = 0
        for x in test:
            c += x; p = max(p, c); dd = max(dd, p - c)
        out[f"oneshot_{name}"] = {"pick": {kk: str(vv) for kk, vv in P[k].items() if kk in ("fam", "entry", "sl", "w", "osl", "lock", "re", "tbe")},
                                  "train_net_2024": sum(train), "test_net_2025_26": sum(test), "test_pf": w / l if l else 99, "test_trades": len(test), "test_dd": dd}
        print("one-shot", name, out[f"oneshot_{name}"])
    # bootstrap + sub-periods for the deployed config
    F = json.load(open(os.path.join(ROOT, "results/final_v7/final.json")))
    x = [r[1] for r in F["runs"]["1lot"]["daily"] if r[5]]
    out["bootstrap"] = boot(x); out["n_trades"] = len(x)
    print("bootstrap", out["bootstrap"], "trades", len(x))
    halves = {}
    for r in F["runs"]["1lot"]["daily"]:
        if r[5]:
            h = f"{r[0] // 10000}-H{1 if (r[0] // 100) % 100 <= 6 else 2}"
            halves.setdefault(h, []).append(r[1])
    out["half_years"] = {h: [len(v), round(sum(v)), round(sum(a for a in v if a > 0) / max(1, -sum(a for a in v if a < 0)), 2)] for h, v in halves.items()}
    print("half-years", out["half_years"])
    # where does the deployed config sit in the full grid distribution (expiry days)?
    nets = sorted(sum(s.get(d, 0.0) for d in exp_days) for s in S7.values())
    out["grid_distribution_v7"] = {"min": nets[0], "p25": nets[len(nets) // 4], "median": nets[len(nets) // 2], "p75": nets[3 * len(nets) // 4], "max": nets[-1],
                                   "share_profitable": sum(1 for n in nets if n > 0) / len(nets)}
    print("v7 grid distribution", {k: round(v, 2) for k, v in out["grid_distribution_v7"].items()})
    json.dump(out, open(os.path.join(OUT, "overfit_audit.json"), "w"), default=str)


if __name__ == "__main__":
    main()
