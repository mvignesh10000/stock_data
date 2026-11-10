"""Round 13 study 3: synthetic future (K + C - P at ATM) vs spot at 15:20 and next 09:20 -> data/r13/syn.parquet"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *
import polars as pl, datetime as dt
days, f = load(); dates = sorted(days)
def syn(day, e, m):
    ch = day["chains"].get(e)
    if ch is None: return None
    s = float(day["spot"][m, 3])
    if np.isnan(s): return None
    k = int(round(s / 50) * 50); i = np.searchsorted(ch["strikes"], k)
    if i >= len(ch["strikes"]) or ch["strikes"][i] != k: return None
    c, p = ch["c"][0, i, m], ch["c"][1, i, m]
    return None if np.isnan(c) or np.isnan(p) else (s, k + float(c) - float(p), float(c), float(p))
rows = []
for i, d in enumerate(dates[:-1]):
    day, nx = days[d], days[dates[i + 1]]
    es = [e for e in sorted(day["chains"]) if e > d]
    if not es: continue
    e = es[0]
    a, a0, b = syn(day, e, 364), syn(day, e, 4), None
    # next morning: value the SAME strike as entered
    if a is None or np.isnan(nx["spot"][4, 3]): continue
    k = int(round(a[0] / 50) * 50); ch = nx["chains"].get(e)
    if ch is None: continue
    j = np.searchsorted(ch["strikes"], k)
    if j >= len(ch["strikes"]) or ch["strikes"][j] != k: continue
    c, p = ch["c"][0, j, 4], ch["c"][1, j, 4]
    if np.isnan(c) or np.isnan(p): continue
    cal = (dt.date(e // 10000, e // 100 % 100, e % 100) - dt.date(d // 10000, d // 100 % 100, d % 100)).days
    nd = dates[i + 1]; gapd = (dt.date(nd // 10000, nd // 100 % 100, nd % 100) - dt.date(d // 10000, d // 100 % 100, d % 100)).days
    rows.append((d, e, cal, gapd, float(day["spot"][4, 3]), a[0], a[1], a[2] + a[3], float(nx["spot"][4, 3]), k + float(c) - float(p)))
df = pl.DataFrame(rows, schema=["d", "e", "cal", "gapd", "s0920", "s1520", "f1520", "strad", "ns0920", "nf0920"], orient="row")
df.write_parquet("data/r13/syn.parquet")
x = df.with_columns((pl.col("f1520") - pl.col("s1520")).alias("basis_c"), (pl.col("nf0920") - pl.col("ns0920")).alias("basis_o"), (pl.col("ns0920") - pl.col("s1520")).alias("dS"), (pl.col("nf0920") - pl.col("f1520")).alias("dF"),
                    ((pl.col("s1520") / pl.col("s0920") - 1) * 100).alias("intra"), (pl.col("d") // 10000).alias("y"))
print(x.select(pl.len(), pl.col("basis_c").mean().round(2), pl.col("basis_o").mean().round(2), pl.col("dS").mean().round(2), pl.col("dF").mean().round(2), (pl.col("basis_c") / pl.col("cal")).mean().round(2).alias("basis/calday"), pl.col("strad").mean().round(0)).to_dicts())
for nm, c in (("intra>0", pl.col("intra") > 0), ("intra>0.3", pl.col("intra") > 0.3), ("intra<=0", pl.col("intra") <= 0)):
    print(nm, x.filter(c).group_by("y").agg(pl.len().alias("n"), pl.col("dS").mean().round(1), pl.col("dF").mean().round(1), pl.col("dF").sum().round(0).alias("sumF")).sort("y").to_dicts())
print("by gap days", x.group_by("gapd").agg(pl.len(), pl.col("dS").mean().round(1), pl.col("dF").mean().round(1)).sort("gapd").to_dicts())
