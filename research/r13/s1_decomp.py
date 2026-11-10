#!/usr/bin/env python3
"""Round 13 study 1: where is the option premium? Per-leg gross P&L of SHORT options (points, per unit) by segment:
overnight (15:20 -> next 09:20) and intraday (09:20 -> 15:20), by moneyness, side, tdte. No costs. -> data/r13/decomp.parquet"""
import os, sys
import numpy as np, polars as pl
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import store
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A, B = 4, 364  # 09:20, 15:20 (close of bar)
OFFS = [0, 0.5, 1.0, 1.5, 2.0, 3.0]

def px(day, e, k, t, m):
    ch = day["chains"].get(e)
    if ch is None: return np.nan
    i = np.searchsorted(ch["strikes"], k)
    if i >= len(ch["strikes"]) or ch["strikes"][i] != k: return np.nan
    return float(ch["c"][t, i, m])

days = store.load()
dates = sorted(days)
rows = []
for i, d in enumerate(dates):
    day = days[d]
    exps = sorted(e for e in day["chains"] if e >= d)
    if not exps: continue
    nxt = days[dates[i + 1]] if i + 1 < len(dates) else None
    for rank, e in enumerate(exps[:2]):
        tdte = sum(1 for x in dates if d < x <= e) if e <= dates[-1] else -1
        for seg, m0, d1, m1 in (("intra", A, day, B), ("night", B, nxt, A)):
            if d1 is None or (seg == "night" and e <= d): continue
            s0, s1 = float(day["spot"][m0, 3]), float(d1["spot"][m1, 3])
            if np.isnan(s0) or np.isnan(s1): continue
            for off in OFFS:
                for t, sgn in ((0, 1), (1, -1)):
                    k = int(round(s0 * (1 + sgn * off / 100) / 50) * 50)
                    p0, p1 = px(day, e, k, t, m0), px(d1, e, k, t, m1)
                    if np.isnan(p0) or np.isnan(p1): continue
                    rows.append((d, e, rank, tdte, seg, off, "CE" if t == 0 else "PE", s0, s1, p0, p1))
df = pl.DataFrame(rows, schema=["date", "expiry", "rank", "tdte", "seg", "off", "opt", "s0", "s1", "p0", "p1"], orient="row")
os.makedirs(f"{ROOT}/data/r13", exist_ok=True)
df.write_parquet(f"{ROOT}/data/r13/decomp.parquet")
print(df.shape)
