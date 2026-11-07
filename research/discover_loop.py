#!/usr/bin/env python3
"""Autonomous strategy discovery & evolutionary updater loop for NIFTY intraday
non-directional option selling, driving the Rust `opt_engine` binary.

Protocol (per generation):
  A. Latin-Hypercube + elite-mutation sweep on the TRAIN split (first 65% of dates).
  B. Neighbourhood stability audit of the top-10: entry_minute -2/-1/+1/+2, sl -5/-2.5/+2.5/+5
     (percentage points). Stability_Ratio = mean(neighbour Calmar)/centre Calmar must be >= 0.75.
  C. Walk-forward VALIDATION (next 20%) and HOLDOUT (last 15%): promote only if
     Calmar >= 3.5 and Profit Factor >= 1.45 on BOTH out-of-sample windows, plus the train gate.
  D. Hypothesis updater: inspect the worst 10 days of the generation leader, mutate the
     sampling priors (DTE-0 late exits, double-SL whipsaws, gap-and-go mornings) and append
     findings to EXPERIMENT_LOG.md. Dead regions (family x DTE-bucket with negative median
     train score after enough samples) are down-weighted so they are not re-tested.

Stops when 3 distinct, uncorrelated (|rho| < 0.5 on train daily P&L) strategies are promoted, or
after --generations generations.
"""
import argparse, json, math, os, random, subprocess, sys, time, copy, statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
CACHE = os.path.join(ROOT, "data/cache/nifty.bin")
WORK = os.path.join(ROOT, "results/discovery")
LOG = os.path.join(ROOT, "EXPERIMENT_LOG.md")

DTE_BUCKETS = {"d0": [0], "d1": [1], "d01": [0, 1], "d12": [1, 2], "d23": [2, 3], "d456": [4, 5, 6, 7], "d0123": [0, 1, 2, 3]}
FAMILIES = ["straddle", "strangle_premium", "strangle_offset"]


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr + r.stdout)
    return r.stdout


def splits():
    info = json.loads(sh([BIN, "info", "--cache", CACHE]))
    dates = [d[0] for d in info["dates"]]
    n = len(dates)
    a, b = int(n * 0.65), int(n * 0.85)
    return {"train": (dates[0], dates[a - 1]), "valid": (dates[a], dates[b - 1]), "holdout": (dates[b], dates[-1]), "all": (dates[0], dates[-1])}


def run_batch(items, rng, tag, with_daily=False):
    """items: list of (id, config, (from,to))."""
    os.makedirs(WORK, exist_ok=True)
    bf = os.path.join(WORK, f"batch_{tag}.jsonl")
    with open(bf, "w") as f:
        for i, cfg, (a, b) in items:
            f.write(json.dumps({"id": i, "config": {"strategy": cfg}, "date_from": a, "date_to": b}) + "\n")
    out = os.path.join(WORK, f"res_{tag}.json")
    cmd = [BIN, "batch-sweep", "--cache", CACHE, "--batch-file", bf, "--out", out]
    if with_daily:
        cmd.append("--with-daily")
    sh(cmd)
    res = json.load(open(out))
    return {r["id"]: r for r in res["results"]}, res["execution_time_ms"]


# ----------------------------------------------------------------------------- sampling
class Priors:
    def __init__(self):
        self.bucket_w = {k: 1.0 for k in DTE_BUCKETS}
        self.family_w = {k: 1.0 for k in FAMILIES}
        self.or_filter_bias = 0.35  # prob. of enabling OR filter
        self.mstc_bias = 0.4  # move-sl-to-cost prob.
        self.reentry_bias = 0.35
        self.d0_early_exit = False
        self.later_entry = False
        self.lock_bias = 0.4
        self.maxloss_bias = 0.6
        self.notes = []


def lhs(n, dims, rng):
    """Latin hypercube in [0,1)^dims."""
    cols = []
    for _ in range(dims):
        p = list(range(n))
        rng.shuffle(p)
        cols.append([(p[i] + rng.random()) / n for i in range(n)])
    return [[cols[d][i] for d in range(dims)] for i in range(n)]


def wchoice(d, u):
    tot = sum(d.values())
    acc = 0
    for k, w in d.items():
        acc += w / tot
        if u <= acc:
            return k
    return list(d)[-1]


def make_config(u, pr: Priors, rng):
    fam = wchoice(pr.family_w, u[0])
    bucket = wchoice(pr.bucket_w, u[1])
    dtes = DTE_BUCKETS[bucket]
    lo_entry = 15 if pr.later_entry else 5
    e = int(lo_entry + u[2] * (105 - lo_entry))  # 09:20..11:00
    tranche = u[3] < 0.3
    entries = [e, min(e + 30, 140)] if tranche else [e]
    sl_mode = "combined" if u[4] < 0.3 else "leg"
    max_prem = 150 if min(dtes) >= 2 else 110
    cfg = {
        "name": f"{fam}_{bucket}",
        "structure": fam,
        "target_premium": round(30 + u[5] * (max_prem - 30)),
        "otm_steps": 1 + int(u[6] * 6),
        "hedge_premium": rng.choice([2.0, 3.0, 5.0]),
        "hedge_min_steps": 4,
        "dte_allowed": dtes,
        "entry_minutes": entries,
        "lots": 1,
        "or_filter_pct": rng.choice([0.4, 0.5, 0.65, 0.8]) if rng.random() < pr.or_filter_bias else 0.0,
        "sl_mode": sl_mode,
        "sl_pct": round(15 + u[7] * 45, 1),
        "combined_sl_pct": round(10 + u[7] * 30, 1),
        "move_sl_to_cost": rng.random() < pr.mstc_bias,
        "cost_offset": round(-0.15 + u[8] * 0.25, 3),
        "max_reentries": (rng.choice([1, 2]) if rng.random() < pr.reentry_bias else 0),
        "reentry_cutoff": 300,
        "wt_drop_pct": rng.choice([0, 0, 0, 5, 10, 15]),
        "wt_window": 60,
        "max_loss_pts": (round(15 + u[9] * 45) if rng.random() < pr.maxloss_bias else 0),
        "target_pts": 0,
        "lock_trigger_pts": (round(8 + u[10] * 32) if rng.random() < pr.lock_bias else 0),
        "lock_pct": round(0.3 + rng.random() * 0.4, 2),
        "trail_step_pts": rng.choice([0, 5, 10]),
        "trail_by_pts": rng.choice([3, 5]),
        "exit_minute": int(300 + u[11] * 68),  # 14:15 .. 15:23
        "roll_ratio": (rng.choice([0.5, 0.6, 0.7]) if rng.random() < 0.2 else 0.0),
        "max_rolls": rng.choice([1, 2]),
        "roll_cutoff": 270,
    }
    if pr.d0_early_exit and 0 in dtes and rng.random() < 0.6:
        cfg["dte_overrides"] = {"0": {"exit_minute": rng.choice([240, 255, 270, 285]), "lock_trigger_pts": rng.choice([8, 12, 16])}}
    return cfg


def mutate(cfg, rng, pr):
    c = copy.deepcopy(cfg)
    for _ in range(rng.choice([1, 2, 3])):
        k = rng.choice(["entry", "sl", "prem", "steps", "exit", "ml", "lock", "mstc", "re", "or", "wt", "hedge", "tranche"])
        if k == "entry":
            d = rng.choice([-10, -5, 5, 10])
            c["entry_minutes"] = [max(5, min(140, x + d)) for x in c["entry_minutes"]]
        elif k == "sl":
            c["sl_pct"] = round(min(70, max(10, c["sl_pct"] * rng.uniform(0.8, 1.25))), 1)
            c["combined_sl_pct"] = round(min(50, max(6, c["combined_sl_pct"] * rng.uniform(0.8, 1.25))), 1)
        elif k == "prem":
            c["target_premium"] = round(min(160, max(20, c["target_premium"] * rng.uniform(0.75, 1.3))))
        elif k == "steps":
            c["otm_steps"] = max(1, min(8, c["otm_steps"] + rng.choice([-1, 1])))
        elif k == "exit":
            c["exit_minute"] = max(240, min(368, c["exit_minute"] + rng.choice([-30, -15, 15, 30])))
        elif k == "ml":
            c["max_loss_pts"] = 0 if c["max_loss_pts"] and rng.random() < 0.3 else round(rng.uniform(15, 60))
        elif k == "lock":
            c["lock_trigger_pts"] = 0 if c["lock_trigger_pts"] and rng.random() < 0.3 else round(rng.uniform(8, 40))
            c["lock_pct"] = round(rng.uniform(0.3, 0.7), 2)
        elif k == "mstc":
            c["move_sl_to_cost"] = not c["move_sl_to_cost"]
            c["cost_offset"] = round(rng.uniform(-0.15, 0.10), 3)
        elif k == "re":
            c["max_reentries"] = rng.choice([0, 1, 2])
        elif k == "or":
            c["or_filter_pct"] = rng.choice([0, 0.4, 0.5, 0.65, 0.8])
        elif k == "wt":
            c["wt_drop_pct"] = rng.choice([0, 5, 10, 15])
        elif k == "hedge":
            c["hedge_premium"] = rng.choice([2.0, 3.0, 5.0])
        elif k == "tranche":
            e = c["entry_minutes"][0]
            c["entry_minutes"] = [e] if len(c["entry_minutes"]) > 1 else [e, min(e + 30, 140)]
    return c


def neighbours(cfg):
    out = []
    for d in (-2, -1, 1, 2):
        c = copy.deepcopy(cfg)
        c["entry_minutes"] = [max(0, x + d) for x in c["entry_minutes"]]
        out.append(("entry%+d" % d, c))
    for d in (-5, -2.5, 2.5, 5):
        c = copy.deepcopy(cfg)
        if c["sl_mode"] == "combined":
            c["combined_sl_pct"] = round(max(3, c["combined_sl_pct"] + d), 2)
        else:
            c["sl_pct"] = round(max(3, c["sl_pct"] + d), 2)
        out.append(("sl%+g" % d, c))
    return out


def consistency(monthly):
    """(share of positive calendar quarters)^2, and 0 if either half of the window loses money."""
    ks = sorted(monthly)
    if not ks:
        return 0.0
    q = defaultdict(float)
    for k in ks:
        y, mo = k.split("-")
        q[(y, (int(mo) - 1) // 3)] += monthly[k]
    qs = [v for v in q.values()]
    pos = sum(1 for v in qs if v > 0) / len(qs)
    h = len(ks) // 2
    h1 = sum(monthly[k] for k in ks[:h])
    h2 = sum(monthly[k] for k in ks[h:])
    return pos * pos if (h1 > 0 and h2 > 0) else 0.0


def score(m, monthly=None):
    """Ranking score: real fitness if the hard gate passes, otherwise a penalised soft fitness;
    multiplied by train-window time consistency (v2)."""
    cons = consistency(monthly) if monthly is not None else 1.0
    if m["gate_passed"]:
        return (10.0 + m["fitness"]) * cons
    s = m["soft_fitness"]
    return (s / (1 + len(m["gate_failures"]))) * cons if s > 0 else s


def key_of(cfg):
    return json.dumps(cfg, sort_keys=True)


def corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((x - mb) ** 2 for x in b))
    if va == 0 or vb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb)


def fmt_m(m):
    return (f"net ₹{m['net_pnl_rupees']:,.0f} | DD ₹{m['max_drawdown_rupees']:,.0f} | Calmar {m['calmar_ratio']:.2f} | PF {m['profit_factor']:.2f} "
            f"| win {m['win_rate_pct']:.1f}% | exp ₹{m['expectancy_per_trade_rupees']:.0f} | worst ₹{m['worst_day_rupees']:,.0f} "
            f"| losing-months {m['losing_months_pct']:.0f}% | UW {m['max_dd_duration_active_days']}d")


def diagnose(daily, exits):
    """Phase D: inspect the 10 worst days of the leader. daily rows: [date, net, dte, stops, last_exit_minute]."""
    rows = [(r, e) for r, e in zip(daily, exits) if r[1] < 0]
    rows.sort(key=lambda x: x[0][1])
    worst = rows[:10]
    if not worst:
        return {}, []
    d0_late = sum(1 for r, e in worst if r[2] == 0 and r[4] >= 255)
    double_sl = sum(1 for r, e in worst if r[3] >= 2)
    morning = sum(1 for r, e in worst if r[4] <= 75)
    maxloss = sum(1 for r, e in worst if "MAXLOSS" in e)
    return {"d0_late": d0_late, "double_sl": double_sl, "morning": morning, "maxloss": maxloss, "n": len(worst)}, worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=8)
    ap.add_argument("--pop", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--want", type=int, default=3)
    ap.add_argument("--label", default="v2")
    ap.add_argument("--buckets", default=",".join(DTE_BUCKETS), help="comma list of DTE buckets to search")
    ap.add_argument("--seed-elites", default=None, help="discovery_summary json whose elites seed generation 1")
    ap.add_argument("--prior", action="append", default=[], help="earlier discovery_summary_*.json whose winners stay in force")
    ap.add_argument("--append", action="store_true")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    sp = splits()
    pr = Priors()
    seen = {}
    elites = []  # (score, cfg)
    if args.seed_elites:
        elites = [(0.01, c) for c in json.load(open(args.seed_elites))["elites"]
                  if any(tuple(c["dte_allowed"]) == tuple(DTE_BUCKETS[b]) for b in args.buckets.split(","))]
    region_scores = defaultdict(list)
    dead_regions = set()
    promoted = []  # dicts
    for pf in args.prior:
        promoted.extend(json.load(open(pf))["promoted"])
    n_prior = len(promoted)
    allowed = set(args.buckets.split(","))
    pr.bucket_w = {k: v for k, v in pr.bucket_w.items() if k in allowed}
    rejected_log = []
    os.makedirs(WORK, exist_ok=True)
    with open(LOG, "a" if args.append else "w") as f:
        f.write(f"\n# Run {args.label} (seed {args.seed}, pop {args.pop})\n\n" if args.append else "# EXPERIMENT_LOG — autonomous discovery of NIFTY intraday non-directional selling strategies\n\n")
        f.write(f"Splits (chronological): train {sp['train']}, validation {sp['valid']}, holdout {sp['holdout']}.\n\n")
        f.write("Costs: ₹20/order brokerage, STT 0.1% sell, NSE txn 0.03503%, SEBI 0.0001%, stamp 0.003% buy, GST 18%; "
                "slippage 0.3% per market fill (min 0.05), +0.5% on stop fills; lot 65 constant; capital ₹2,00,000 per lot.\n\n")

    for gen in range(1, args.generations + 1):
        t0 = time.time()
        n_new = args.pop if not elites else args.pop // 2
        U = lhs(n_new, 12, rng)
        cands = [make_config(u, pr, rng) for u in U]
        if elites:
            top = [c for _, c in sorted(elites, key=lambda x: -x[0])[:25]]
            while len(cands) < args.pop:
                cands.append(mutate(rng.choice(top), rng, pr))
        # dead-region skip (avoid re-testing dead ends)
        cands = [c for c in cands if (c["structure"], tuple(c["dte_allowed"])) not in dead_regions or rng.random() < 0.1]
        items, idmap = [], {}
        for i, c in enumerate(cands):
            k = key_of(c)
            if k in seen:
                continue
            cid = f"g{gen}_{i}"
            idmap[cid] = c
            items.append((cid, c, sp["train"]))
        res, ms = run_batch(items, rng, f"g{gen}_train")
        scored = []
        for cid, r in res.items():
            if r["status"] != "SUCCESS":
                continue
            m = r["summary_metrics"]
            s = score(m, r["monthly_pnl"])
            c = idmap[cid]
            seen[key_of(c)] = s
            region_scores[(c["structure"], tuple(c["dte_allowed"]))].append(s)
            scored.append((s, cid, c, m))
        scored.sort(key=lambda x: -x[0])
        n_pass = sum(1 for x in scored if x[3]["gate_passed"])
        # v2: smoothed fitness — neighbours of the top-30; only stable configs breed
        pre = [x for x in scored if x[3]["net_pnl_rupees"] > 0][:30]
        sm_items = [(f"{cid}|{t}", nc, sp["train"]) for s, cid, c, m in pre for t, nc in neighbours(c)]
        smres, _ = run_batch(sm_items, rng, f"g{gen}_smooth") if sm_items else ({}, 0)
        smoothed = []
        for s, cid, c, m in pre:
            nb = [smres[f"{cid}|{t}"] for t, _ in neighbours(c)]
            ns = [score(x["summary_metrics"], x["monthly_pnl"]) for x in nb]
            ncal = [x["summary_metrics"]["calmar_ratio"] for x in nb]
            stab = (sum(ncal) / len(ncal)) / m["calmar_ratio"] if m["calmar_ratio"] > 0 else 0
            sm = (s + sum(ns)) / (1 + len(ns))
            if stab >= 0.75:
                smoothed.append((sm, c))
        niche = defaultdict(list)
        for sm, c in sorted(elites + smoothed, key=lambda x: -x[0]):
            r = (c["structure"], tuple(c["dte_allowed"]))
            if len(niche[r]) < 5 and all(key_of(c) != key_of(o) for _, o in niche[r]):
                niche[r].append((sm, c))
        elites = sorted([x for v in niche.values() for x in v], key=lambda x: -x[0])[:60]

        # ---- Phase B: stability audit on top-10 (distinct)
        top10 = []
        per_region = defaultdict(int)
        for s, cid, c, m in scored:
            if len(top10) >= 10:
                break
            r = (c["structure"], tuple(c["dte_allowed"]))
            if m["net_pnl_rupees"] <= 0 or per_region[r] >= 3:
                continue
            per_region[r] += 1
            top10.append((s, cid, c, m))
        nb_items = []
        for s, cid, c, m in top10:
            for tag, nc in neighbours(c):
                nb_items.append((f"{cid}|{tag}", nc, sp["train"]))
        nres, _ = run_batch(nb_items, rng, f"g{gen}_nb") if nb_items else ({}, 0)
        stable = []
        stab_lines = []
        for s, cid, c, m in top10:
            ncal = [nres[f"{cid}|{t}"]["summary_metrics"]["calmar_ratio"] for t, _ in neighbours(c)]
            cc = m["calmar_ratio"]
            ratio = (sum(ncal) / len(ncal)) / cc if cc > 0 else 0
            ok = ratio >= 0.75
            stab_lines.append(f"  - `{cid}` {c['name']} Calmar {cc:.2f} → neighbour mean {sum(ncal)/len(ncal):.2f}, Stability {ratio:.2f} {'✅' if ok else '❌ discarded (lucky spike)'}")
            if ok:
                stable.append((s, cid, c, m, ratio))

        # ---- Phase C: walk-forward + holdout
        oos_items = []
        for s, cid, c, m, ratio in stable:
            oos_items.append((f"{cid}|valid", c, sp["valid"]))
            oos_items.append((f"{cid}|trainD", c, sp["train"]))
        ores, _ = run_batch(oos_items, rng, f"g{gen}_oos", with_daily=True) if oos_items else ({}, 0)
        # the holdout is only touched by candidates that passed the train gate AND validation
        ho_items = []
        for s, cid, c, m, ratio in stable:
            v = ores[f"{cid}|valid"]["summary_metrics"]
            if m["gate_passed"] and v["calmar_ratio"] >= 3.5 and v["profit_factor"] >= 1.45:
                ho_items.append((f"{cid}|holdout", c, sp["holdout"]))
        hres, _ = run_batch(ho_items, rng, f"g{gen}_ho") if ho_items else ({}, 0)
        oos_lines = []
        blank = {"calmar_ratio": float("nan"), "profit_factor": float("nan"), "net_pnl_rupees": float("nan")}
        for s, cid, c, m, ratio in stable:
            v = ores[f"{cid}|valid"]["summary_metrics"]
            h = hres.get(f"{cid}|holdout", {}).get("summary_metrics", blank)
            ok_v = v["calmar_ratio"] >= 3.5 and v["profit_factor"] >= 1.45
            ok_h = h["calmar_ratio"] >= 3.5 and h["profit_factor"] >= 1.45
            daily = [r[1] for r in ores[f"{cid}|trainD"]["daily"]]
            corr_ok = all(abs(corr(daily, p["train_daily"])) < 0.5 for p in promoted)
            distinct = all(p["config"]["name"] != c["name"] or p["config"]["structure"] != c["structure"] for p in promoted)
            verdict = []
            if not m["gate_passed"]:
                verdict.append("train hard-gate: " + "; ".join(m["gate_failures"]))
            if not ok_v:
                verdict.append(f"validation Calmar {v['calmar_ratio']:.2f}/PF {v['profit_factor']:.2f}")
            if not ok_h and f"{cid}|holdout" in hres:
                verdict.append(f"holdout Calmar {h['calmar_ratio']:.2f}/PF {h['profit_factor']:.2f}")
            if not corr_ok:
                verdict.append("correlated with an existing winner")
            if not distinct:
                verdict.append("duplicate of an existing winner's family/bucket")
            promote = not verdict and f"{cid}|holdout" in hres
            oos_lines.append(f"  - `{cid}` {c['name']}: valid Calmar {v['calmar_ratio']:.2f} PF {v['profit_factor']:.2f} net ₹{v['net_pnl_rupees']:,.0f}; "
                             + (f"holdout Calmar {h['calmar_ratio']:.2f} PF {h['profit_factor']:.2f} net ₹{h['net_pnl_rupees']:,.0f} → " if f"{cid}|holdout" in hres else "holdout not touched → ")
                             + ("**PROMOTED**" if promote else "rejected (" + "; ".join(verdict) + ")"))
            rec = {"id": cid, "gen": gen, "config": c, "train": m, "valid": v, "holdout": h, "stability": ratio, "train_daily": daily, "promoted": promote, "why": verdict}
            if promote:
                promoted.append(rec)
            else:
                rejected_log.append(rec)

        # ---- Phase D: hypothesis updater on the generation leader
        hyp = []
        if scored:
            s, cid, c, m = scored[0]
            lr, _ = run_batch([(cid, c, sp["train"])], rng, f"g{gen}_leader", with_daily=True)
            diag, worst = diagnose(lr[cid]["daily"], lr[cid]["daily_exit"])
            if diag:
                n = diag["n"]
                if diag["d0_late"] >= max(3, n * 0.3):
                    pr.d0_early_exit = True
                    pr.lock_bias = min(0.8, pr.lock_bias + 0.15)
                    hyp.append(f"{diag['d0_late']}/{n} worst days were DTE-0 losses closed after 13:30 → enabling DTE-0 early-exit overrides + tighter profit lock.")
                if diag["double_sl"] >= max(3, n * 0.3):
                    pr.mstc_bias = min(0.85, pr.mstc_bias + 0.2)
                    pr.reentry_bias = min(0.7, pr.reentry_bias + 0.15)
                    hyp.append(f"{diag['double_sl']}/{n} worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.")
                if diag["morning"] >= max(3, n * 0.3):
                    pr.or_filter_bias = min(0.8, pr.or_filter_bias + 0.2)
                    pr.later_entry = True
                    hyp.append(f"{diag['morning']}/{n} worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.")
                if diag["maxloss"] >= max(3, n * 0.3):
                    pr.maxloss_bias = min(0.9, pr.maxloss_bias + 0.1)
                    hyp.append(f"{diag['maxloss']}/{n} worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.")
                if not hyp:
                    hyp.append("Worst days spread across causes — no single structural fix; keep priors.")
                worst_txt = ", ".join(f"{int(r[0])}(dte{int(r[2])},₹{r[1]:,.0f},{int(r[3])}SL,{e})" for r, e in worst[:5])
                hyp.append(f"Leader worst days: {worst_txt}")
        # dead-region update + re-weighting
        for reg, ss in region_scores.items():
            if len(ss) >= 25 and statistics.median(ss) < 0 and max(ss) < 0.5:
                if reg not in dead_regions:
                    dead_regions.add(reg)
        bucket_best = defaultdict(list)
        fam_best = defaultdict(list)
        for (fam, dt), ss in region_scores.items():
            b = next((k for k, v in DTE_BUCKETS.items() if tuple(v) == dt), None)
            if b:
                bucket_best[b].append(max(ss))
            fam_best[fam].append(max(ss))
        for b in list(pr.bucket_w):
            if bucket_best.get(b):
                pr.bucket_w[b] = 0.4 + max(0.0, min(3.0, max(bucket_best[b])))
        for f_ in pr.family_w:
            if fam_best.get(f_):
                pr.family_w[f_] = 0.5 + max(0.0, min(3.0, max(fam_best[f_])))

        dt = time.time() - t0
        with open(LOG, "a") as f:
            f.write(f"## Generation {gen}  ({len(items)} train runs in {ms/1000:.1f}s engine time, {dt:.1f}s wall)\n\n")
            f.write(f"- Hard-gate passes on train: **{n_pass}/{len(scored)}**\n")
            for s, cid, c, m in scored[:3]:
                f.write(f"- Top `{cid}` {c['name']} (score {s:.2f}): {fmt_m(m)}\n")
                if m["gate_failures"]:
                    f.write(f"  - gate failures: {'; '.join(m['gate_failures'])}\n")
            f.write("- Phase B stability audit:\n" + ("\n".join(stab_lines) or "  - (no candidates)") + "\n")
            f.write("- Phase C walk-forward/holdout:\n" + ("\n".join(oos_lines) or "  - (no stable candidates)") + "\n")
            f.write("- Phase D hypotheses:\n" + "\n".join("  - " + h for h in hyp) + "\n")
            if dead_regions:
                f.write("- Dead regions (not re-sampled): " + ", ".join(f"{a}/DTE{list(b)}" for a, b in sorted(dead_regions)) + "\n")
            f.write("- Next-gen bucket weights: " + ", ".join(f"{k}={v:.2f}" for k, v in pr.bucket_w.items()) + "\n\n")
        print(f"gen {gen}: {len(items)} runs, pass {n_pass}, stable {len(stable)}, promoted total {len(promoted)}, {dt:.1f}s", flush=True)
        if len(promoted) >= args.want:
            break

    promoted_new = promoted[n_prior:]

    json.dump({"splits": sp, "promoted": promoted_new, "rejected": rejected_log[-60:],
               "elites": [c for _, c in sorted(elites, key=lambda x: -x[0])[:30]]},
              open(os.path.join(WORK, f"discovery_summary_{args.label}.json"), "w"), indent=1)
    print(json.dumps({"promoted": [p["id"] for p in promoted_new], "total": len(promoted)}))


if __name__ == "__main__":
    main()
