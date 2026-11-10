#!/usr/bin/env python3
"""Round 13 portfolio: B (expiry-day fly), W (weekly overnight fly), M (overnight momentum premium). 1-lot daily series ->
results/r13/daily.json, then portfolio table (lots, net/yr, DD, winning months, bootstrap DD)."""
import sys, os, json
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, ".."))
from lib import *
ROOT = os.path.dirname(os.path.dirname(H)); P = f"{ROOT}/results/r13/daily.json"
A, Z = 20211115, 20261106

def build():
    from validate import StrategyB
    from v14_positional import Weekly
    from on2 import ON2
    days, f = load(); out = {}
    for nm, st in (("B", StrategyB()), ("W", Weekly(3, "15:15", "fly", ("d", 0.03), None, 8000, None, "open")),
                   ("M", ON2(up="naked", dn="naked")), ("Mw", ON2(up="ps", dn="ps", wing=4.0)), ("Mup", ON2(up="naked", dn=None)), ("Mdn", ON2(up=None, dn="naked"))):
        r = run(st, days, f, A, Z); print(line(nm, r)); print("    ", yearly(r), flush=True)
        out[nm] = [(d, round(p, 1), round(m)) for d, p, m, _ in r["daily"]]
    os.makedirs(os.path.dirname(P), exist_ok=True); json.dump(out, open(P, "w"))

def combo(S, w):
    ds = sorted({d for k in w for d, *_ in S[k]}); ix = {d: i for i, d in enumerate(ds)}
    p = np.zeros(len(ds))
    for k, n in w.items():
        for d, v, _ in S[k]: p[ix[d]] += n * v
    return ds, p

def boot_dd(ds, p, n=2000, seed=1):
    mon = {}
    for d, v in zip(ds, p): mon.setdefault(d // 100, []).append(v)
    blocks = list(mon.values()); rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        x = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))]); eq = np.cumsum(x)
        out.append(np.max(np.maximum.accumulate(np.maximum(eq, 0)) - eq))
    return np.percentile(out, [50, 95, 99])

def report():
    S = json.load(open(P)); CAP = 5e5
    names = ["B", "W", "M", "Mw"]; ds, _ = combo(S, {k: 1 for k in names})
    M = np.array([combo(S, {k: 1, **{j: 0 for j in names if j != k}})[1] for k in names])
    print("daily correlation", names); print(np.round(np.corrcoef(M), 2))
    mon = lambda p: np.array([sum(v for d, v in zip(ds, p) if d // 100 == m) for m in sorted({d // 100 for d in ds})])
    print("monthly correlation"); print(np.round(np.corrcoef(np.array([mon(x) for x in M])), 2))
    print(f"\n{'portfolio (lots)':28s} {'net/yr':>8s} {'%5L':>6s} {'maxDD':>7s} {'DD%':>5s} {'p95DD':>7s} {'WM%':>4s} {'worstM':>8s} {'worstD':>8s} {'Sharpe':>6s} {'losing yrs':>10s}")
    for w in ({"B": 2}, {"B": 2, "W": 1}, {"M": 1}, {"Mw": 1}, {"M": 2}, {"B": 2, "M": 1}, {"B": 2, "M": 2}, {"B": 2, "W": 1, "M": 1}, {"B": 2, "W": 1, "M": 2}, {"B": 2, "Mw": 2}, {"B": 2, "W": 1, "Mw": 2}, {"B": 2, "Mw": 3}):
        ds, p = combo(S, w); a = stats(list(zip(ds, p))); b = boot_dd(ds, p)
        yr = {}
        for d, v in zip(ds, p): yr[d // 10000] = yr.get(d // 10000, 0) + v
        print(f"{'+'.join(f'{k}x{n}' for k, n in w.items()):28s} {a['yr']/1e3:7.1f}k {a['yr']/CAP*100:5.1f}% {a['dd']/1e3:6.1f}k {a['dd']/CAP*100:4.1f}% {b[1]/1e3:6.1f}k {a['wm']:4.0f} {a['worstm']/1e3:7.1f}k {a['worst']/1e3:7.1f}k {a['sharpe']:6.2f} {sum(v < 0 for v in yr.values()):>10d}")
    ds, p = combo(S, {"B": 2, "W": 1, "M": 1}); yr = {}
    for d, v in zip(ds, p): yr[d // 10000] = yr.get(d // 10000, 0) + v
    print("B2+W1+M1 by year:", " ".join(f"{k}:{v/1e3:+.0f}k" for k, v in sorted(yr.items())))

if __name__ == "__main__":
    if "build" in sys.argv: build()
    report()
