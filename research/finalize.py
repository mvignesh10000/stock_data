#!/usr/bin/env python3
"""Final evaluation of discovered strategies -> results/final/*.json, WINNING_STRATEGIES.md.

Tier A  = passed every gate of the spec (train hard gate, stability >= 0.75, validation AND holdout
          Calmar >= 3.5 & PF >= 1.45, uncorrelated).
Tier B  = pre-registered relaxed rule, fixed BEFORE these candidates touched the holdout:
          stability >= 0.75; validation Calmar >= 3.5 & PF >= 1.45; the only train-gate failures allowed are
          'losing months' <= 22.3% (<= 4 of 18 months) and/or expectancy >= ₹300; no tail-risk or underwater
          failure; one per DTE bucket not covered by Tier A, best validation Calmar.
"""
import json, os, re, subprocess, copy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
CACHE = os.path.join(ROOT, "data/cache/nifty.bin")
OUT = os.path.join(ROOT, "results/final")
CFG = os.path.join(ROOT, "configs/final")
DISC = os.path.join(ROOT, "results/discovery")
os.makedirs(OUT, exist_ok=True)
os.makedirs(CFG, exist_ok=True)

summ = {v: json.load(open(f"{DISC}/discovery_summary_{v}.json")) for v in ["v2", "v3", "v4"]}
sp = summ["v2"]["splits"]


def tier_b_ok(r):
    if r["stability"] < 0.75 or r["valid"]["calmar_ratio"] < 3.5 or r["valid"]["profit_factor"] < 1.45:
        return False
    for f in r["train"]["gate_failures"]:
        m = re.match(r"losing months ([0-9.]+)%", f)
        if m and float(m.group(1)) <= 22.3:
            continue
        m = re.match(r"thin edge: expectancy ₹(-?[0-9]+)", f)
        if m and int(m.group(1)) >= 300:
            continue
        return False
    return True


tier_a = [dict(p, tier="A", run=v) for v, s in summ.items() for p in s["promoted"]]
covered = {tuple(p["config"]["dte_allowed"]) for p in tier_a}
best = {}
for v, s in summ.items():
    for r in s["rejected"]:
        b = tuple(r["config"]["dte_allowed"])
        if b in covered or not tier_b_ok(r):
            continue
        if b not in best or r["valid"]["calmar_ratio"] > best[b]["valid"]["calmar_ratio"]:
            best[b] = dict(r, tier="B", run=v)
tier_b = list(best.values())

LABELS = {(0,): "Expiry-day (DTE 0)", (4, 5, 6, 7): "Far-week (DTE 4-6)", (2, 3): "Mid-week (DTE 2-3)"}
strats = []
for i, r in enumerate(tier_a + tier_b, 1):
    c = copy.deepcopy(r["config"])
    c["name"] = f"S{i}_{c['structure']}_dte{''.join(map(str, c['dte_allowed']))}"
    strats.append({"key": f"S{i}", "tier": r["tier"], "label": LABELS.get(tuple(c["dte_allowed"]), str(c["dte_allowed"])),
                   "source_id": f"{r['run']}:{r['id']}", "stability": r["stability"], "config": c})

baselines = [
    {"key": "B1", "tier": "baseline", "label": "Plain hedged ATM straddle, every day", "stability": None, "source_id": "baseline",
     "config": {"name": "B1_plain_straddle_all", "structure": "straddle", "entry_minutes": [10], "sl_pct": 30, "hedge_premium": 3, "exit_minute": 360}},
    {"key": "B2", "tier": "baseline", "label": "Plain hedged ATM straddle, DTE 1 (Mon under the Tue-expiry calendar)", "stability": None, "source_id": "baseline",
     "config": {"name": "B2_plain_straddle_dte1", "structure": "straddle", "dte_allowed": [1], "entry_minutes": [10], "sl_pct": 30, "hedge_premium": 3, "exit_minute": 360}},
]


def backtest(cfg_obj, tag, frm, to):
    p = f"{CFG}/{tag}.json"
    json.dump(cfg_obj, open(p, "w"), indent=1)
    o = f"{OUT}/{tag}.json"
    subprocess.run([BIN, "backtest", "--cache", CACHE, "--strategy-config", p, "--date-from", str(frm), "--date-to", str(to), "--out", o], check=True, capture_output=True)
    return json.load(open(o))


def wrap(strategies, lots=1, capital=200000, brokerage=20.0):
    ss = []
    for s in strategies:
        s = copy.deepcopy(s)
        s["lots"] = lots
        ss.append(s)
    w = {"exec": {"costs": {"brokerage_per_order": brokerage}}, "gates": {"capital": capital}}
    if len(ss) == 1:
        w["strategy"] = ss[0]
    else:
        w["portfolio"] = ss
    return w


SPLITS = {"train": sp["train"], "valid": sp["valid"], "holdout": sp["holdout"], "all": sp["all"]}
summary = {"splits": sp, "items": []}
by_key = {s["key"]: s for s in strats}
by_bucket = {tuple(s["config"]["dte_allowed"]): s["key"] for s in strats}
live = [by_bucket[b] for b in [(0,), (4, 5, 6, 7)] if b in by_bucket]
portfolios = [
    {"key": "P1", "tier": "portfolio", "label": f"Portfolio {'+'.join(live)} (live calendar: expiry day + DTE 4-6)", "members": live},
    {"key": "P2", "tier": "portfolio", "label": f"Portfolio {'+'.join(by_key)} (all discovered, disjoint DTE days)", "members": list(by_key)},
]
for item in strats + baselines + portfolios:
    members = [by_key[k]["config"] for k in item["members"] if k in by_key] if "members" in item else [item["config"]]
    if not members:
        continue
    rec = {k: v for k, v in item.items() if k != "members"}
    rec["members"] = item.get("members")
    rec["configs"] = members
    for size, (lots, cap) in {"2L": (1, 200000), "3L": (2, 300000)}.items():
        for sname, (a, b) in SPLITS.items():
            if size == "3L" and sname != "all":
                continue
            r = backtest(wrap(members, lots, cap), f"{item['key']}_{size}_{sname}", a, b)
            rec.setdefault("runs", {})[f"{size}_{sname}"] = f"{item['key']}_{size}_{sname}.json"
            rec.setdefault("metrics", {})[f"{size}_{sname}"] = r["summary_metrics"]
    r = backtest(wrap(members, 1, 200000, brokerage=0.0), f"{item['key']}_2L_all_zerobrok", *SPLITS["all"])
    rec["metrics"]["2L_all_zerobrok"] = r["summary_metrics"]
    summary["items"].append(rec)
    m = rec["metrics"]
    print(item["key"], item["tier"], "all net ₹%.0f DD ₹%.0f | valid Calmar %.2f | holdout Calmar %.2f PF %.2f" % (
        m["2L_all"]["net_pnl_rupees"], m["2L_all"]["max_drawdown_rupees"], m["2L_valid"]["calmar_ratio"], m["2L_holdout"]["calmar_ratio"], m["2L_holdout"]["profit_factor"]))

# stability ratio for portfolios/baselines is not defined (no single parameter centre)
json.dump(summary, open(f"{OUT}/final_summary.json", "w"), indent=1)
print("wrote", f"{OUT}/final_summary.json")
