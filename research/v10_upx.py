#!/usr/bin/env python3
"""v10 — re-optimisation on Upstox TRUE 1-min OHLC for the user's objective:
   * hard cap: max drawdown <= 6 % of capital (Rs 12k on Rs 2L) including the worst single day
   * maximise smoothness: Ulcer Performance Index (UPI = annual return % / ulcer index %), >= 85 % winning months target
   * NIFTY (expiry Tue; Thu before Sep-2025) + SENSEX (expiry Thu; Tue/Fri earlier) expiry-day iron flies, 1 lot each.

Protocol (pre-declared, small grid, plateau selection):
   TRAIN = all expiry days before 2026-01-01, TEST = 2026-01-01 .. latest (NIFTY Apr-Nov 2026 never seen by any earlier round).
   Each config's score on TRAIN = median of (UPI subject to DD cap) over the config and its +/-1 grid neighbours.
   The selected config per index is then reported on TEST without changes; the NIFTY+SENSEX portfolio is the
   daily sum (different expiry weekdays share the same capital; peak margin checked per day).
Writes results/upx/v10.json
"""
import itertools, json, math, os, statistics, subprocess, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "opt_engine/target/release/opt_engine")
OUT = os.path.join(ROOT, "results/upx")
os.makedirs(OUT, exist_ok=True)
CAP = 200000
SPLIT = 20260101
U = {
    "NIFTY": {"cache": f"{ROOT}/data/cache/nifty_true.bin", "lot": 65, "wings": [6, 8, 10, 12]},     # x50 = 300..600 pts
    "SENSEX": {"cache": f"{ROOT}/data/cache/sensex_upx.bin", "lot": 20, "wings": [10, 15, 20, 25]},  # x100 = 1000..2500 pts
}
ENTRY = ["09:17", "09:20", "09:25", "09:30"]
SL = [40, 50, 60, 80]
OSL = [1500, 2000, 3000]
TBE = ["none", "sl_legs"]
EXIT = ["15:00", "15:15"]
DIMS = [ENTRY, SL, None, OSL, TBE, EXIT]  # index 2 = wings (per underlying)


def cfg(name, e, sl, w, osl, tbe, ex):
    return {"kind": "algotest", "name": f"{name}_fly", "entry_time": e, "exit_time": ex, "no_reentry_after": "14:30", "dte": [0],
            "underlying": "cash", "legs": [
                {"side": "sell", "opt": "CE", "strike": {"mode": "atm"}, "sl": {"kind": "pct", "value": sl}},
                {"side": "sell", "opt": "PE", "strike": {"mode": "atm"}, "sl": {"kind": "pct", "value": sl}},
                {"side": "buy", "opt": "CE", "strike": {"mode": "otm", "n": w}},
                {"side": "buy", "opt": "PE", "strike": {"mode": "otm", "n": w}}],
            "square_off": "partial", "trail_to_breakeven": tbe, "overall": {"sl_mtm": osl}, "sizing": {"mode": "fixed", "multiplier": 1}}


def run_grid(name):
    u = U[name]
    keys, lines = [], []
    for k in itertools.product(range(4), range(4), range(4), range(3), range(2), range(2)):
        e, s, w, o, t, x = ENTRY[k[0]], SL[k[1]], u["wings"][k[2]], OSL[k[3]], TBE[k[4]], EXIT[k[5]]
        keys.append(k)
        lines.append({"id": "|".join(map(str, k)), "config": {"strategy": cfg(name, e, s, w, o, t, x), "exec": {"lot_size": u["lot"]},
                                                              "gates": {"capital": CAP}}})
    bf, of = f"{OUT}/v10_{name}_batch.jsonl", f"{OUT}/v10_{name}_res.json"
    with open(bf, "w") as f:
        f.write("\n".join(json.dumps(l) for l in lines))
    subprocess.run([BIN, "batch-sweep", "--cache", u["cache"], "--batch-file", bf, "--out", of, "--with-daily"], check=True, capture_output=True)
    res = {tuple(map(int, r["id"].split("|"))): r for r in json.load(open(of))["results"] if r["status"] == "SUCCESS"}
    return res


def metrics(series, a=0, b=99999999):
    """series [(date, net, margin)] -> dict on [a, b] (only days in window)."""
    s = [(d, n, m) for d, n, m in series if a <= d <= b]
    if not s:
        return None
    eq, peak, dd, sq, months = CAP, CAP, 0.0, 0.0, defaultdict(float)
    for d, n, _ in s:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
        sq += ((peak - eq) / peak * 100) ** 2
        months[d // 100] += n
    ui = math.sqrt(sq / len(s))
    yrs = len(s) / 248
    net = eq - CAP
    ann = net / CAP * 100 / yrs
    trades = [n for _, n, _ in s if n != 0]
    gw, gl = sum(x for x in trades if x > 0), -sum(x for x in trades if x < 0)
    mv = list(months.values())
    return {"net": round(net), "ann_pct": round(ann, 2), "dd": round(dd), "dd_pct": round(dd / CAP * 100, 2), "ulcer": round(ui, 3),
            "upi": round(ann / ui, 2) if ui > 0 else 0, "calmar": round(ann / (dd / CAP * 100), 2) if dd > 0 else 0,
            "worst_day": round(min(trades)) if trades else 0, "pf": round(gw / gl, 2) if gl else 0, "trades": len(trades),
            "months": len(mv), "win_months_pct": round(sum(1 for x in mv if x > 0) / len(mv) * 100, 1),
            "worst_month": round(min(mv)), "peak_margin": round(max(m for *_, m in s))}


def series_of(r):
    return [(int(d[0]), d[1], d[5]) for d in r["daily"]]


def score(m):
    if not m or m["dd_pct"] > 6.0 or m["net"] <= 0:
        return -1.0
    return m["upi"]


def neighbours(k):
    out = []
    for i in range(len(k)):
        for d in (-1, 1):
            j = k[i] + d
            n = 4 if i in (0, 1, 2) else (3 if i == 3 else 2)
            if 0 <= j < n:
                kk = list(k)
                kk[i] = j
                out.append(tuple(kk))
    return out


def select(res, a, b):
    m = {k: metrics(series_of(r), a, b) for k, r in res.items()}
    sc = {}
    for k in res:
        vals = [score(m[k])] + [score(m[n]) for n in neighbours(k) if n in m]
        sc[k] = statistics.median(vals) if score(m[k]) > 0 else -1
    best = max(sc, key=lambda k: sc[k])
    return best, sc[best], m


def describe(name, k):
    u = U[name]
    st = 50 if name == "NIFTY" else 100
    return {"entry": ENTRY[k[0]], "sl_pct": SL[k[1]], "wings_pts": u["wings"][k[2]] * st, "overall_sl": OSL[k[3]], "trail_be": TBE[k[4]], "exit": EXIT[k[5]]}


def main():
    names = [n for n in U if os.path.exists(U[n]["cache"])]
    out = {"protocol": __doc__, "per_index": {}, "portfolio": {}}
    chosen = {}
    for name in names:
        res = run_grid(name)
        best, sc, mtr = select(res, 0, SPLIT - 1)
        full = metrics(series_of(res[best]))
        test = metrics(series_of(res[best]), SPLIT)
        allm = {k: metrics(series_of(r)) for k, r in res.items()}
        frac_ok = sum(1 for v in allm.values() if v and v["net"] > 0) / len(allm)
        test_all = sorted((metrics(series_of(r), SPLIT) or {"net": 0})["net"] for r in res.values())
        out["per_index"][name] = {"selected": describe(name, best), "plateau_upi_train": sc, "train": mtr[best], "test_2026": test, "full": full,
                                  "grid_size": len(res), "grid_profitable_full_pct": round(frac_ok * 100, 1),
                                  "grid_test_net_median": test_all[len(test_all) // 2], "grid_test_net_p10_p90": [test_all[len(test_all) // 10], test_all[9 * len(test_all) // 10]]}
        chosen[name] = series_of(res[best])
        print(name, describe(name, best), "\n  TRAIN", mtr[best], "\n  TEST ", test, "\n  FULL ", full, flush=True)
    if len(chosen) == 2:
        comb = defaultdict(lambda: [0.0, 0.0])
        for s in chosen.values():
            for d, n, mg in s:
                comb[d][0] += n
                comb[d][1] += mg
        ser = sorted((d, v[0], v[1]) for d, v in comb.items())
        # days on which both indices expire use both margins on the same day -> report how often capital is exceeded
        over = sum(1 for _, _, mg in ser if mg > CAP)
        out["portfolio"] = {"train": metrics(ser, 0, SPLIT - 1), "test_2026": metrics(ser, SPLIT), "full": metrics(ser), "days_margin_over_cap": over}
        print("PORTFOLIO", out["portfolio"])
    json.dump(out, open(f"{OUT}/v10.json", "w"), indent=1)


if __name__ == "__main__":
    main()
