import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
from lib import *
import engine
from on2 import ON2
days, f = load(); out = {}
base = dict(up="naked", dn="naked", thr_up=0.3, thr_dn=0.3)
G = [("M base naked/naked t.3", {}), ("thr .2", dict(thr_up=0.2, thr_dn=0.2)), ("thr .4", dict(thr_up=0.4, thr_dn=0.4)), ("thr .5", dict(thr_up=0.5, thr_dn=0.5)), ("thr .0", dict(thr_up=0.0, thr_dn=0.0)),
     ("entry 15:10", dict(entry="15:10")), ("entry 15:25", dict(entry="15:25")), ("exit 09:17", dict(exit_="09:17")), ("exit 09:25", dict(exit_="09:25")), ("exit 09:45", dict(exit_="09:45")),
     ("wing 3% (ps/ps)", dict(up="ps", dn="ps", wing=3.0)), ("wing 4% (ps/ps)", dict(up="ps", dn="ps", wing=4.0)), ("SLIPx2", {}), ("syn/syn t.3", dict(up="syn", dn="syn")), ("syn/naked t.3", dict(up="syn", dn="naked"))]
_s = engine.slip
for nm, kw in G:
    engine.slip = (lambda p: 2 * _s(p)) if nm == "SLIPx2" else _s
    r = run(ON2(**{**base, **kw}), days, f); print(line(nm, r)); print("    ", yearly(r), flush=True); out[nm] = r["daily"]
json.dump(out, open("data/r13/m_robust.json", "w"))
