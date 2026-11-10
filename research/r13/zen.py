"""Round 13: 2017-2020 monthly-expiry store (out-of-sample era for option execution). data/simzen/nifty_<Y>.pkl"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
import store
ZOUT = os.path.join(store.ROOT, "data/simzen")
def build():
    store.OUT, store.SRC = ZOUT, ["NIFTY_ZEN"]; store.build()
def load():
    o = store.OUT; store.OUT = ZOUT
    try: return store.load()
    finally: store.OUT = o
if __name__ == "__main__": build()
