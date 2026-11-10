import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import *
from s2_overnight import ON
days, f = load(); out = {}
for struct, wing in [("syn", 0), ("itm", 1.0), ("itm", 1.5), ("itm", 2.0), ("call", 0)]:
    for thr in (0.2, 0.3, 0.5):
        r = run(ON(struct, thr, wing), days, f); nm = f"{struct}{wing} thr{thr}"
        print(line(nm, r)); print("    ", yearly(r), flush=True); out[nm] = r["daily"]
json.dump(out, open("data/r13/s4.json", "w"))
