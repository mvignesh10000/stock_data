#!/usr/bin/env python3
"""v8 — evaluate the VIX regime-switch framework (hedged non-directional selling in low/mid VIX,
ORB intraday buying in high VIX) with a shared-capital portfolio, on the realistic engine.

Pre-declared grids (parameter ranges taken from the user's framework, nothing tuned afterwards):
SELL (126): iron fly wings OTM2/3/4/8/12, iron condor OTM1+w2/w3 x entry 09:20/09:45/10:15 x leg SL 30/40/60%
            x overall SL off/Rs2000; trail-SL-to-BE on SL legs; exit 15:10; slippage 0.5%/fill + 1% stops.
BUY  (108): ORB long straddle (CE on range-high break, PE on range-low break, underlying, range from 09:16)
            range end 09:25/09:30/09:35 x strike ATM/ITM1 x SL 20/30/40% x trail none/10-10/20-10 % x target none/60%;
            exit 15:10; slippage 1.5%/fill + 1.5% stops.
Regime = India VIX previous close (known before the open): low < 13.5, mid 13.5-16.5, high > 16.5.
"""
import itertools, json, math, os, sys
from collections import defaultdict
import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover_v5 as v5
import discover_v6 as v6
from stats import monte_carlo_dd

ROOT = v5.ROOT
WORK = os.path.join(ROOT, "results/v8")
SELL_EXEC = {}
BUY_EXEC = {"entry_slippage_pct": 1.5, "sl_slippage_pct": 1.5}


def t(m):  # minutes after 09:15 -> HH:MM
    return v5.t(m)


SELL_DIMS = {"struct": [("fly", 2), ("fly", 3), ("fly", 4), ("fly", 8), ("fly", 12), ("condor", 2), ("condor", 3)],
             "entry": [5, 30, 60], "sl": [30, 40, 60], "osl": [0, 2000]}
BUY_DIMS = {"rend": [10, 15, 20], "strike": ["atm", "itm1"], "sl": [20, 30, 40], "trail": [None, (10, 10), (20, 10)], "tgt": [None, 60]}


def sell_cfg(p):
    kind, w = p["struct"]
    if kind == "fly":
        s, h = {"mode": "atm"}, {"mode": "otm", "n": w}
    else:
        s, h = {"mode": "otm", "n": 1}, {"mode": "otm", "n": 1 + w}
    leg = lambda o, st: {"side": "sell", "opt": o, "strike": st, "sl": {"kind": "pct", "value": p["sl"]}}
    return {"kind": "algotest", "name": "SELL", "entry_time": t(p["entry"]), "exit_time": "15:10", "no_reentry_after": "14:30",
            "legs": [leg("CE", s), leg("PE", s), {"side": "buy", "opt": "CE", "strike": h}, {"side": "buy", "opt": "PE", "strike": h}],
            "trail_to_breakeven": "sl_legs", "overall": ({"sl_mtm": p["osl"]} if p["osl"] else {}), "sizing": {"mode": "fixed", "multiplier": 1}}


def buy_cfg(p):
    st = {"mode": "atm"} if p["strike"] == "atm" else {"mode": "itm", "n": 1}
    def leg(o, side):
        l = {"side": "buy", "opt": o, "strike": st, "sl": {"kind": "pct", "value": p["sl"]}, "orb": {"end": t(p["rend"] + 1), "side": side}}
        if p["trail"]:
            l["trail"] = {"kind": "pct", "x": p["trail"][0], "y": p["trail"][1]}
        if p["tgt"]:
            l["target"] = {"kind": "pct", "value": p["tgt"]}
        return l
    return {"kind": "algotest", "name": "BUY", "entry_time": "09:16", "exit_time": "15:10", "no_reentry_after": "14:30",
            "legs": [leg("CE", "high"), leg("PE", "low")], "sizing": {"mode": "fixed", "multiplier": 1}}


def run_grid(dims, mk, exec_cfg, ds):
    names = list(dims)
    g = []
    for idx in itertools.product(*[range(len(dims[n])) for n in names]):
        p = {n: dims[n][i] for n, i in zip(names, idx)}
        g.append((idx, p))
    res = v5.run_batch([(json.dumps(idx), mk(p), (ds[0], ds[-1])) for idx, p in g], with_daily=True, exec_cfg=exec_cfg)
    series = {}
    for idx, p in g:
        r = res.get(json.dumps(idx))
        if r:
            series[idx] = {int(d[0]): d[1] for d in r["daily"]}
    return series, dict(g)


def nb(idx, dims):
    out = []
    for j, n in enumerate(dims):
        for d in (-1, 1):
            k = idx[j] + d
            if 0 <= k < len(dims[n]):
                out.append(idx[:j] + (k,) + idx[j + 1:])
    return out


def stats(pnl):
    pnl = list(pnl)
    if not pnl:
        return {"n": 0, "net": 0, "pf": 0, "win": 0, "dd": 0, "worst": 0}
    tr = [x for x in pnl if x != 0]
    w = sum(x for x in tr if x > 0); l = -sum(x for x in tr if x < 0)
    c = p = dd = 0.0
    for x in pnl:
        c += x; p = max(p, c); dd = max(dd, p - c)
    return {"n": len(tr), "net": sum(pnl), "pf": (w / l) if l > 0 else 99.0, "win": (sum(1 for x in tr if x > 0) / len(tr) * 100) if tr else 0, "dd": dd, "worst": min(tr) if tr else 0}


def plateau_pick(series, dims, days):
    """best plateau config on a set of days (score = net/dd-ish * pf * consistency via v6.score on the subset)."""
    days = sorted(days)
    if len(days) < 10:
        return None
    sc = {}
    for k, s in series.items():
        sc[k] = v6.score(v6.win_metrics([(d, s.get(d, 0.0)) for d in days], days[0], days[-1]))
    best, bk = -1e9, None
    for k in series:
        ns = [sc[n] for n in nb(k, dims) if n in sc]
        if sc[k] <= 0 or (ns and sum(1 for x in ns if x > 0) / len(ns) < 0.6):
            continue
        pl_ = (sc[k] + sum(ns)) / (1 + len(ns))
        if pl_ > best:
            best, bk = pl_, k
    return bk


def main():
    os.makedirs(WORK, exist_ok=True)
    v5.WORK = WORK
    ds = v5.dates()
    info = json.loads(v5.sh([v5.BIN, "info", "--cache", v5.CACHE]))
    tdte = {d[0]: d[1] for d in info["dates"]}
    vix = {r[0]: r for r in pl.read_csv(os.path.join(ROOT, "data/india_vix_daily.csv")).rows()}
    pv = {d: vix[d][5] for d in ds}  # previous close
    # gap: |09:15 open - previous day's last spot| / prev
    sp = pl.concat([pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY_OHLC/*/*.parquet"), pl.scan_parquet(f"{ROOT}/data/parquet/NIFTY/*/*.parquet")]) \
        .filter(pl.col("expiry_rank") == 0).select("trade_date", "minute_idx", "spot_open", "spot_close").unique(["trade_date", "minute_idx"]) \
        .group_by("trade_date").agg(pl.col("spot_open").sort_by("minute_idx").first().alias("o"), pl.col("spot_close").sort_by("minute_idx").last().alias("c")).sort("trade_date").collect()
    oc = {r[0]: (r[1], r[2]) for r in sp.rows()}
    gap = {}
    for a, b in zip(ds, ds[1:]):
        gap[b] = abs(oc[b][0] / oc[a][1] - 1) * 100
    gap[ds[0]] = 0.0

    def reg(d, lo=13.5, hi=16.5):
        return "low" if pv[d] < lo else ("high" if pv[d] > hi else "mid")

    print("running grids ...", flush=True)
    S, Sp = run_grid(SELL_DIMS, sell_cfg, SELL_EXEC, ds)
    B, Bp = run_grid(BUY_DIMS, buy_cfg, BUY_EXEC, ds)
    out = {"n_sell": len(S), "n_buy": len(B)}

    # ---------------- 1. each side by regime x day-type (grid median and best-plateau)
    def subset(f):
        return [d for d in ds if f(d)]
    groups = {}
    for r_ in ("low", "mid", "high"):
        for dt_ in ("expiry", "non-expiry"):
            groups[f"{r_}/{dt_}"] = subset(lambda d: reg(d) == r_ and ((tdte[d] == 0) == (dt_ == "expiry")))
    tab = []
    for side, ser, dims in (("SELL", S, SELL_DIMS), ("BUY", B, BUY_DIMS)):
        for gname, days in groups.items():
            nets = sorted(sum(s.get(d, 0.0) for d in days) for s in ser.values())
            pos = sum(1 for x in nets if x > 0) / len(nets) * 100
            tab.append([side, gname, len(days), round(nets[len(nets) // 2]), round(nets[-1]), round(pos)])
    out["by_regime"] = tab
    print("side | regime/day | days | grid-median net | best net | % configs profitable")
    for r in tab:
        print(r)

    # ---------------- 2. hedge synergy: on the selling side's worst days, does buying make money?
    s_med = sorted(S, key=lambda k: sum(S[k].values()))[len(S) // 2]
    b_med = sorted(B, key=lambda k: sum(B[k].values()))[len(B) // 2]
    sm, bm = S[s_med], B[b_med]
    xs = [sm.get(d, 0.0) for d in ds]; ys = [bm.get(d, 0.0) for d in ds]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cor = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    worst = sorted(ds, key=lambda d: sm.get(d, 0.0))[:40]
    out["synergy"] = {"corr_median_configs": cor, "sell_worst40_sum": sum(sm.get(d, 0) for d in worst), "buy_on_those_days": sum(bm.get(d, 0) for d in worst),
                      "buy_win_rate_on_those_days": sum(1 for d in worst if bm.get(d, 0) > 0) / 40 * 100}
    print("synergy", {k: round(v, 2) for k, v in out["synergy"].items()})

    # ---------------- 3. walk-forward of the regime-switch procedure vs pure-selling procedure
    folds = [d for q, d in v5.quarter_starts(ds) if d >= 20240701]
    def wf(policy, lo=13.5, hi=16.5):
        pnl = []
        picks = []
        for i, f0 in enumerate(folds):
            f1 = folds[i + 1] if i + 1 < len(folds) else 99999999
            train = [d for d in ds if d < f0]; test = [d for d in ds if f0 <= d < f1]
            sell_days = lambda dd: [d for d in dd if (policy["sell_regimes"] is None or reg(d, lo, hi) in policy["sell_regimes"]) and (not policy["expiry_only"] or tdte[d] == 0) and not (policy["skip_gap"] and gap[d] > 0.7)]
            buy_days = lambda dd: [d for d in dd if policy["buy_regimes"] and reg(d, lo, hi) in policy["buy_regimes"]]
            ks = plateau_pick(S, SELL_DIMS, sell_days(train))
            kb = plateau_pick(B, BUY_DIMS, buy_days(train)) if policy["buy_regimes"] else None
            picks.append([f0, Sp[ks]["struct"] if ks else None, Sp[ks]["entry"] if ks else None, kb is not None])
            for d in test:
                x = 0.0
                if ks and d in set(sell_days([d])):
                    x += S[ks].get(d, 0.0)
                if kb and d in set(buy_days([d])):
                    x += B[kb].get(d, 0.0)
                pnl.append((d, x))
        return pnl, picks
    policies = {
        "A pure selling, expiry-day only (v7 style)": {"sell_regimes": None, "buy_regimes": None, "expiry_only": True, "skip_gap": False},
        "B pure selling, every day": {"sell_regimes": None, "buy_regimes": None, "expiry_only": False, "skip_gap": False},
        "C framework: sell low+mid VIX (every day), buy high VIX": {"sell_regimes": {"low", "mid"}, "buy_regimes": {"high"}, "expiry_only": False, "skip_gap": False},
        "D framework on expiry days: sell low+mid, buy high": {"sell_regimes": {"low", "mid"}, "buy_regimes": {"high"}, "expiry_only": True, "skip_gap": False},
        "E sell low+mid expiry only, no buying": {"sell_regimes": {"low", "mid"}, "buy_regimes": None, "expiry_only": True, "skip_gap": False},
        "F = A + skip gap days > 0.7%": {"sell_regimes": None, "buy_regimes": None, "expiry_only": True, "skip_gap": True},
        "G buy ORB in high VIX only (no selling)": {"sell_regimes": set(), "buy_regimes": {"high"}, "expiry_only": False, "skip_gap": False},
    }
    out["wf"] = {}
    for name, pol in policies.items():
        pnl, picks = wf(pol)
        st = stats([x for _, x in pnl])
        st["mc95"] = monte_carlo_dd([x for _, x in pnl], n=3000)
        out["wf"][name] = {"stats": st, "picks": picks, "pnl": pnl}
        print(f"WF {name:58s} net {st['net']:>9,.0f} PF {st['pf']:.2f} DD {st['dd']:>8,.0f} trades {st['n']} worst {st['worst']:,.0f} MC95 {st['mc95']:,.0f}", flush=True)
    # threshold sensitivity for policy C/D
    out["thresholds"] = []
    for lo, hi in ((12.5, 15.5), (13, 16), (13.5, 16.5), (14, 17), (15, 18)):
        for name in ("C framework: sell low+mid VIX (every day), buy high VIX", "D framework on expiry days: sell low+mid, buy high"):
            pnl, _ = wf(policies[name], lo, hi)
            st = stats([x for _, x in pnl])
            out["thresholds"].append([name[:1], lo, hi, round(st["net"]), round(st["pf"], 2), round(st["dd"])])
            print("threshold", name[:1], lo, hi, round(st["net"]), round(st["pf"], 2), round(st["dd"]))
    # buying side: parameter-proximity for range length (10/15/20 min) on high-VIX days, full sample
    hv = [d for d in ds if reg(d) == "high"]
    prox = defaultdict(list)
    for k, s in B.items():
        prox[Bp[k]["rend"]].append(sum(s.get(d, 0.0) for d in hv))
    out["buy_range_proximity_highvix"] = {str(r): [round(sorted(v)[len(v) // 2]), round(max(v)), round(sum(1 for x in v if x > 0) / len(v) * 100)] for r, v in prox.items()}
    print("buy ORB range proximity (high VIX days): end-min -> [median net, best net, % profitable]", out["buy_range_proximity_highvix"])
    # wing distance test on selling (full sample, expiry days, median over other params)
    wing = defaultdict(list)
    for k, s in S.items():
        wing[str(Sp[k]["struct"])].append(sum(s.get(d, 0.0) for d in ds if tdte[d] == 0))
    out["wing_test_expiry"] = {w: [round(sorted(v)[len(v) // 2]), round(max(v))] for w, v in wing.items()}
    print("wing distance on expiry days: struct -> [median net, best net]", out["wing_test_expiry"])
    json.dump(out, open(os.path.join(WORK, "v8_summary.json"), "w"), default=str)


if __name__ == "__main__":
    main()
