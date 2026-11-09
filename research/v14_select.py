#!/usr/bin/env python3
"""Pre-declared selection for the v14 positional weekly grid (written before the grid finished).

Rule: among configs with SELECTION (2024-01..2026-03) net > 0 and SELECTION max DD <= Rs 60k per lot, score = median SELECTION
PF over the config and all its one-parameter neighbours (plateau); pick the top score. Report the top 10 with their untouched
results on OLD (2021-11..2023-12) and NEW (2026-03-25..2026-11-06), plus the share of the whole grid that is profitable in each block.
"""
import json, os, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = json.load(open(f"{ROOT}/results/v14/all.json"))
key = {tuple(map(str, r["key"])): r for r in rows}
g = lambda r, b, f: (r.get(b) or {}).get(f, 0)


def neighbours(k):
    out = []
    for k2, r in key.items():
        if sum(a != b for a, b in zip(k, k2)) == 1:
            out.append(r)
    return out


cands = []
for k, r in key.items():
    if g(r, "SEL", "net") > 0 and g(r, "SEL", "dd") <= 60000:
        sc = statistics.median([g(r, "SEL", "pf")] + [g(n, "SEL", "pf") for n in neighbours(k)])
        cands.append((sc, r))
cands.sort(key=lambda t: -t[0])
print(f"grid {len(rows)} configs; profitable share  OLD {sum(g(r,'OLD','net')>0 for r in rows)/len(rows)*100:.0f}%  "
      f"SEL {sum(g(r,'SEL','net')>0 for r in rows)/len(rows)*100:.0f}%  NEW {sum(g(r,'NEW','net')>0 for r in rows)/len(rows)*100:.0f}%")
print(f"eligible on SELECTION: {len(cands)}")
for i, (sc, r) in enumerate(cands[:10]):
    print(f"{'PICK' if i == 0 else '    '} {r['name']:52s} plateau {sc:.2f} | " + " | ".join(
        f"{b} pf {g(r,b,'pf'):.2f} /yr {g(r,b,'per_year'):>7} dd {g(r,b,'dd'):>6}" for b in ("SEL", "OLD", "NEW")) + f" | margin~{r['margin_p50']}")
json.dump({"rule": __doc__, "pick": cands[0][1] if cands else None, "top10": [r for _, r in cands[:10]]},
          open(f"{ROOT}/results/v14/selection.json", "w"), indent=1, default=list)
