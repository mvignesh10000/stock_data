"""Round 13 helpers: load store once (cached pickle of loaded dict is too big; just load), stats, blocks."""
import os, sys, math, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import store, features
from engine import IDX, Strategy, run, LOT  # noqa
BLOCKS = (("21-23", 20211101, 20231231), ("24-26Q1", 20240101, 20260324), ("26hold", 20260325, 20261231))

def stats(daily, lo=0, hi=99999999):
    x = [(d, p) for d, p, *_ in daily if lo <= d <= hi]
    if not x: return {}
    p = np.array([v for _, v in x]); t = p[p != 0]
    eq = np.cumsum(p); dd = float(np.max(np.maximum.accumulate(np.maximum(eq, 0)) - eq)) if len(eq) else 0
    mon = {}
    for d, v in x: mon[d // 100] = mon.get(d // 100, 0) + v
    mv = np.array([v for v in mon.values() if v != 0]) if mon else np.array([0.0])
    yrs = max(len(mon) / 12, 1e-9)
    g, l = t[t > 0].sum(), -t[t < 0].sum()
    return dict(net=float(p.sum()), yr=float(p.sum() / yrs), pf=float(g / l) if l > 0 else 9.99, n=int(len(t)), win=float(np.mean(t > 0) * 100) if len(t) else 0,
                dd=dd, worst=float(p.min()), wm=float(np.mean(mv > 0) * 100) if len(mv) else 0, worstm=float(mv.min()) if len(mv) else 0,
                sharpe=float(p.mean() / p.std() * math.sqrt(250)) if p.std() > 0 else 0)

def line(name, r, margin=None):
    a = stats(r["daily"])
    s = f"{name:34s} yr {a['yr']/1e3:6.1f}k PF {a['pf']:4.2f} n {a['n']:4d} win {a['win']:3.0f}% DD {a['dd']/1e3:5.1f}k wd {a['worst']/1e3:6.1f}k WM {a['wm']:3.0f}% wm {a['worstm']/1e3:6.1f}k Sh {a['sharpe']:4.2f} |"
    for nm, lo, hi in BLOCKS:
        b = stats(r["daily"], lo, hi)
        s += f" {nm} {b.get('pf',0):4.2f}/{b.get('yr',0)/1e3:5.1f}k"
    mg = [m for _, _, m, _ in r["daily"] if m > 0]
    if mg: s += f" | mrg med {np.median(mg)/1e3:4.0f}k max {np.max(mg)/1e3:4.0f}k"
    return s

def yearly(r):
    y = {}
    for d, p, *_ in r["daily"]: y[d // 10000] = y.get(d // 10000, 0) + p
    return " ".join(f"{k}:{v/1e3:+.1f}k" for k, v in sorted(y.items()))

_D = {}
def load():
    if not _D:
        _D["days"] = store.load(); _D["f"] = features.load()
    return _D["days"], _D["f"]
