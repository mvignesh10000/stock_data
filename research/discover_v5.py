#!/usr/bin/env python3
"""Discovery v5 — AlgoTest-expressible non-directional NIFTY selling, realistic engine.

Changes vs v1-v4 (after external review):
* data: 2024 true 1-min OHLC + 2025-26 LTP with SYNTHETIC intra-minute wicks calibrated on true OHLC
  (validated on Oct-Dec 2024 where both sources overlap);
* engine: 0.5% slippage per fill (min Rs0.10) + 1% extra on stop fills, pessimistic same-bar
  re-check, SPAN-calibrated margin incl. the 2% expiry-day ELM, trading-day DTE (AlgoTest);
* strategy space: only settings that exist in the AlgoTest builder (`kind: "algotest"`);
* protocol: ANCHORED WALK-FORWARD — for every quarter Q from 2024-Q3, the whole optimiser runs only on
  data before Q, picks one stable config per trading-DTE bucket and trades Q blind. The concatenated
  out-of-sample P&L is the honest estimate. A final optimisation on all data gives the configs to deploy,
  and those are graded by Deflated Sharpe, stability, stress tests and Monte-Carlo drawdown.
"""
import argparse, copy, json, math, os, random, subprocess, sys, time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import monte_carlo_dd, deflated_sharpe, moments

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
CACHE = os.path.join(ROOT, "data/cache/nifty_wick.bin")
WORK = os.path.join(ROOT, "results/v5")
LOG = os.environ.get("V5_LOG", os.path.join(ROOT, "EXPERIMENT_LOG.md"))
GATES = {"capital": 200000.0}
BUCKETS = {"tdte0": [0], "tdte1": [1], "tdte2": [2], "tdte3": [3], "tdte4": [4]}
ALL_TRIALS = []  # (bucket, daily sharpe) of every evaluated config, for the Deflated Sharpe


def sh(a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr + r.stdout)
    return r.stdout


def dates():
    return [d[0] for d in json.loads(sh([BIN, "info", "--cache", CACHE]))["dates"]]


_batch_id = [0]


def run_batch(items, with_daily=False, exec_cfg=None, cache=None):
    """items: [(id, cfg, (from, to))] -> {id: result}"""
    os.makedirs(WORK, exist_ok=True)
    _batch_id[0] += 1
    bf = os.path.join(WORK, f"b{_batch_id[0] % 4}.jsonl")
    with open(bf, "w") as f:
        for i, c, (a, b) in items:
            w = {"strategy": c, "gates": GATES}
            if exec_cfg:
                w["exec"] = exec_cfg
            f.write(json.dumps({"id": i, "config": w, "date_from": a, "date_to": b}) + "\n")
    out = os.path.join(WORK, f"r{_batch_id[0] % 4}.json")
    cmd = [BIN, "batch-sweep", "--cache", cache or CACHE, "--batch-file", bf, "--out", out]
    if with_daily:
        cmd.append("--with-daily")
    sh(cmd)
    return {r["id"]: r for r in json.load(open(out))["results"] if r["status"] == "SUCCESS"}


# ----------------------------------------------------------------------------- AlgoTest config space
def t(minutes_after_915):
    m = 9 * 60 + 15 + minutes_after_915
    return f"{m // 60:02d}:{m % 60:02d}"


def tmin(s):
    h, m = map(int, s.split(":"))
    return h * 60 + m - (9 * 60 + 15)


def sell_leg(opt, strike, p):
    l = {"side": "sell", "opt": opt, "strike": strike}
    if p["sl"]:
        l["sl"] = {"kind": "pct", "value": p["sl"]}
    if p["trail"]:
        l["trail"] = {"kind": "pct", "x": p["trail"][0], "y": p["trail"][1]}
    if p["re"]:
        l["re_sl"] = {"kind": p["re"][0], "count": p["re"][1]}
    if p["mom"]:
        l["momentum"] = {"kind": "pct_down", "value": p["mom"]}
    return l


def build(p):
    fam, legs = p["fam"], []
    if fam == "ironfly":
        s = {"mode": "atm"}
        legs = [sell_leg("CE", s, p), sell_leg("PE", s, p)]
        w = {"mode": "otm", "n": p["w"]}
    elif fam == "ironcondor":
        s = {"mode": "otm", "n": p["n"]}
        legs = [sell_leg("CE", s, p), sell_leg("PE", s, p)]
        w = {"mode": "otm", "n": p["n"] + p["w"]}
    elif fam == "prem_strangle":
        s = {"mode": "closest_premium", "value": p["prem"]}
        legs = [sell_leg("CE", s, p), sell_leg("PE", s, p)]
        w = {"mode": "closest_premium", "value": p["hprem"]}
    else:  # atm_pct strangle
        s = {"mode": "atm_premium_pct", "value": p["apct"]}
        legs = [sell_leg("CE", s, p), sell_leg("PE", s, p)]
        w = {"mode": "otm", "n": p["w"]}
    legs += [{"side": "buy", "opt": "CE", "strike": w}, {"side": "buy", "opt": "PE", "strike": w}]
    o = {}
    if p["osl"]:
        o["sl_mtm"] = p["osl"]
    if p["otgt"]:
        o["tgt_mtm"] = p["otgt"]
    if p["lock"]:
        r, frac, ev = p["lock"]
        o.update({"lock_reach": r, "lock_profit": round(r * frac), "trail_every": ev, "trail_by": ev // 2})
    return {"kind": "algotest", "name": f"{fam}_{p['bucket']}", "entry_time": t(p["entry"]), "exit_time": t(p["exit"]),
            "no_reentry_after": t(min(p["exit"] - 30, 315)), "dte": BUCKETS[p["bucket"]], "underlying": p["und"], "legs": legs,
            "square_off": p["sq"], "trail_to_breakeven": p["tbe"], "overall": o, "sizing": {"mode": "fixed", "multiplier": 1}}


def sample(rng, bucket):
    fam = rng.choice(["ironfly", "ironfly", "ironcondor", "prem_strangle", "atm_pct"])
    d0 = bucket == "tdte0"
    p = {"bucket": bucket, "fam": fam, "und": rng.choice(["cash", "cash", "synthetic"]),
         "entry": rng.choice(range(5, 136, 5)), "exit": rng.choice([330, 340, 350, 355, 360, 365]),
         "sl": rng.choice([None, 15, 20, 25, 30, 35, 40, 50, 60, 70]),
         "trail": rng.choice([None, None, None, (10, 5), (20, 10)]),
         "re": rng.choice([None, None, ("cost", 1), ("cost", 2), ("asap", 1)]),
         "mom": rng.choice([None, None, None, 5, 10, 15]),
         "w": rng.choice([3, 4, 6, 8, 10, 14, 20]), "n": rng.choice([1, 2, 3, 4]),
         "prem": rng.choice(range(15, 81, 5)) if d0 else rng.choice(range(25, 151, 5)),
         "hprem": rng.choice([2, 3, 5, 8, 12]), "apct": rng.choice([15, 20, 25, 30, 35, 40, 45]),
         "sq": "complete" if rng.random() < 0.15 else "partial", "tbe": rng.choice(["none", "sl_legs", "sl_legs"]),
         "osl": rng.choice([0, 0, 1500, 2000, 2500, 3000, 4000]), "otgt": rng.choice([0, 0, 0, 2000, 3000, 4500, 6000]),
         "lock": rng.choice([None, None, (1500, 0.4, 250), (2500, 0.4, 500), (3000, 0.5, 500), (4000, 0.5, 0)])}
    if p["sl"] is None:
        p["trail"], p["re"] = None, None
        if not p["osl"]:
            p["osl"] = rng.choice([1500, 2000, 2500, 3000])
    return p


def mutate(p, rng):
    q = copy.deepcopy(p)
    for _ in range(rng.choice([1, 2, 3])):
        k = rng.choice(["entry", "exit", "sl", "w", "prem", "osl", "otgt", "lock", "re", "tbe", "trail", "mom", "und", "n", "apct", "hprem"])
        base = sample(rng, p["bucket"])
        if k == "entry":
            q["entry"] = max(5, min(200, q["entry"] + rng.choice([-15, -10, -5, 5, 10, 15])))
        elif k == "sl" and q["sl"]:
            q["sl"] = max(10, min(80, q["sl"] + rng.choice([-10, -5, 5, 10])))
        else:
            q[k] = base[k]
    if q["sl"] is None:
        q["trail"], q["re"] = None, None
        if not q["osl"]:
            q["osl"] = 2500
    return q


def neighbours(p):
    out = []
    for d in (-2, -1, 1, 2):
        q = copy.deepcopy(p)
        q["entry"] = max(1, q["entry"] + d)
        out.append(q)
    for d in (-5, -2.5, 2.5, 5):
        q = copy.deepcopy(p)
        if q["sl"]:
            q["sl"] = max(5, q["sl"] + d)
        else:
            q["osl"] = max(500, q["osl"] * (1 + d / 25))
        out.append(q)
    return out


def consistency(monthly):
    ks = sorted(monthly)
    if len(ks) < 2:
        return 0.0
    q = defaultdict(float)
    for k in ks:
        y, mo = k.split("-")
        q[(y, (int(mo) - 1) // 3)] += monthly[k]
    pos = sum(1 for v in q.values() if v > 0) / len(q)
    h = len(ks) // 2
    return pos * pos if (sum(monthly[k] for k in ks[:h]) > 0 and sum(monthly[k] for k in ks[h:]) > 0) else 0.0


def score(r):
    m = r["summary_metrics"]
    if m["traded_days"] < 8:
        return -1e9
    c = consistency(r["monthly_pnl"])
    if m["gate_passed"]:
        return (10 + m["fitness"]) * c
    s = m["soft_fitness"]
    return s / (1 + len(m["gate_failures"])) * c if s > 0 else s


def optimise(bucket, window, rng, gens=3, pop=300, topk=10):
    """Returns ranked list of (smoothed_score, params, train_metrics, stability)."""
    seen, elites = set(), []
    for g in range(gens):
        cands = [sample(rng, bucket) for _ in range(pop if g == 0 else pop // 2)]
        while len(cands) < pop and elites:
            cands.append(mutate(rng.choice(elites[:15])[1], rng))
        items = []
        for i, p in enumerate(cands):
            k = json.dumps(p, sort_keys=True)
            if k in seen:
                continue
            seen.add(k)
            items.append((f"{g}_{i}", p))
        res = run_batch([(i, build(p), window) for i, p in items])
        pm = dict(items)
        for i, r in res.items():
            sh_ = r["summary_metrics"]["sharpe_ratio"] / math.sqrt(252)
            ALL_TRIALS.append((bucket, sh_))
            elites.append((score(r), pm[i], r))
        elites.sort(key=lambda x: -x[0])
        # de-duplicate
        uniq, ks = [], set()
        for e in elites:
            k = json.dumps(e[1], sort_keys=True)
            if k not in ks:
                ks.add(k)
                uniq.append(e)
        elites = uniq[:60]
    # stability audit of the top-k
    top = [e for e in elites if e[2]["summary_metrics"]["net_pnl_rupees"] > 0][:topk]
    items = [(f"{i}|{j}", build(q), window) for i, e in enumerate(top) for j, q in enumerate(neighbours(e[1]))]
    nres = run_batch(items) if items else {}
    ranked = []
    for i, (s, p, r) in enumerate(top):
        nb = [nres.get(f"{i}|{j}") for j in range(8)]
        nb = [x for x in nb if x]
        cc = r["summary_metrics"]["calmar_ratio"]
        stab = (sum(x["summary_metrics"]["calmar_ratio"] for x in nb) / len(nb)) / cc if (nb and cc > 0) else 0
        smooth = (s + sum(score(x) for x in nb)) / (1 + len(nb))
        ranked.append((smooth if stab >= 0.75 else -1e6 + smooth, p, r["summary_metrics"], stab))
    ranked.sort(key=lambda x: -x[0])
    return ranked


def quarter_starts(ds):
    qs = []
    for d in ds:
        y, m = d // 10000, (d // 100) % 100
        q = (y, (m - 1) // 3)
        if not qs or qs[-1][0] != q:
            qs.append((q, d))
    return qs


def log(txt):
    with open(LOG, "a") as f:
        f.write(txt + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--wf-gens", type=int, default=3)
    ap.add_argument("--wf-pop", type=int, default=240)
    ap.add_argument("--final-gens", type=int, default=5)
    ap.add_argument("--final-pop", type=int, default=360)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    ds = dates()
    qs = quarter_starts(ds)
    folds = [(q, d0) for q, d0 in qs if d0 >= 20240701]
    t0 = time.time()
    log("\n# Run v5 — realistic engine + AlgoTest-expressible space + anchored walk-forward\n")
    log("Pre-registered protocol (written before running):\n"
        "- Data: 2024 true OHLC + 2025-26 LTP with synthetic wicks (validated vs true OHLC on Oct-Dec 2024).\n"
        "- Costs: Rs20/order, STT 0.1% sell, NSE 0.03503%, SEBI, stamp, GST; slippage 0.5%/fill (min Rs0.10) + 1% on stops.\n"
        "- One strategy per TRADING-DTE bucket (0..4) so every weekday can use the capital; 1 lot, Rs2L gates.\n"
        "- Walk-forward: for each quarter from 2024-Q3 the optimiser (LHS-style sampling + mutation, stability audit:\n"
        "  entry +-1/+-2 min, SL +-2.5/+-5 pts, ratio >= 0.75) sees only earlier data, then trades the quarter blind.\n"
        "- Final configs: same optimiser on all data; deploy only if hard gate passes on the full sample, stability >= 0.75,\n"
        "  walk-forward OOS of that bucket is profitable with PF >= 1.2, and Deflated Sharpe >= 0.90.\n")
    wf = {}
    for fi, ((y, qn), d0) in enumerate(folds):
        nxt = folds[fi + 1][1] if fi + 1 < len(folds) else 99999999
        train = (ds[0], max(x for x in ds if x < d0))
        test = (d0, min(max(ds), max(x for x in ds if x < nxt)))
        picks = {}
        for b in BUCKETS:
            ranked = optimise(b, train, rng, args.wf_gens, args.wf_pop)
            if ranked and ranked[0][0] > -1e5 and ranked[0][2]["net_pnl_rupees"] > 0:
                picks[b] = ranked[0]
        res = run_batch([(b, build(r[1]), test) for b, r in picks.items()], with_daily=True)
        line = f"- WF fold {y}-Q{qn + 1} (train {train[0]}-{train[1]}, test {test[0]}-{test[1]}):"
        for b in BUCKETS:
            if b in res:
                m = res[b]["summary_metrics"]
                wf.setdefault(b, []).extend([(d[0], d[1]) for d in res[b]["daily"]])
                line += f" {b} {picks[b][1]['fam']} OOS Rs{m['net_pnl_rupees']:,.0f};"
            else:
                line += f" {b} no stable config;"
        log(line)
        print(line, f"[{time.time() - t0:.0f}s]", flush=True)
    # final optimisation on all data
    final = {}
    for b in BUCKETS:
        ranked = optimise(b, (ds[0], ds[-1]), rng, args.final_gens, args.final_pop, topk=12)
        final[b] = ranked[:5]
        r0 = ranked[0]
        log(f"- FINAL {b}: {r0[1]['fam']} stab {r0[3]:.2f} | net Rs{r0[2]['net_pnl_rupees']:,.0f} DD Rs{r0[2]['max_drawdown_rupees']:,.0f} "
            f"Calmar {r0[2]['calmar_ratio']:.2f} PF {r0[2]['profit_factor']:.2f} gate {r0[2]['gate_passed']} {'; '.join(r0[2]['gate_failures'])}")
        print("final", b, r0[1]["fam"], round(r0[3], 2), round(r0[2]["net_pnl_rupees"]), flush=True)
    srs = [s for _, s in ALL_TRIALS]
    mu = sum(srs) / len(srs)
    var_sr = sum((s - mu) ** 2 for s in srs) / (len(srs) - 1)
    out = {"folds": [[y, q, d] for (y, q), d in folds], "wf_oos": wf, "n_trials": len(ALL_TRIALS), "var_sr": var_sr,
           "final": {b: [{"score": s, "params": p, "cfg": build(p), "metrics": m, "stability": st} for s, p, m, st in v] for b, v in final.items()}}
    json.dump(out, open(os.path.join(WORK, "v5_summary.json"), "w"), indent=1)
    log(f"- Trials evaluated in v5: {len(ALL_TRIALS)} (var of daily Sharpe across trials {var_sr:.5f}); wall {time.time() - t0:.0f}s")
    print("done", len(ALL_TRIALS), time.time() - t0)


if __name__ == "__main__":
    main()
