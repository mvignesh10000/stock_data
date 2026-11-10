import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib, zen
from lib import *
from on2 import ON2
lib.BLOCKS = (("17-18", 20170101, 20181231), ("19", 20190101, 20191231), ("20", 20200101, 20201231))
days = zen.load(); out = {}
for nm, kw in [("up syn t.3", dict(up="syn")), ("up naked t.3", dict(up="naked")), ("up call t.3", dict(up="call")), ("dn syn t.3", dict(up=None, dn="syn")), ("dn naked t.3", dict(up=None, dn="naked")),
               ("both syn/naked t.3", dict(up="syn", dn="naked")), ("both naked/naked t.3", dict(up="naked", dn="naked")), ("both naked/naked t.5", dict(up="naked", dn="naked", thr_up=0.5, thr_dn=0.5)), ("up syn t.5", dict(up="syn", thr_up=0.5))]:
    r = run(ON2(**kw), days, {}); print(lib.line(nm, r)); print("    ", yearly(r), flush=True); out[nm] = r["daily"]
json.dump(out, open("data/r13/on2_zen.json", "w"))
