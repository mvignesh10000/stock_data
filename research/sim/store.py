#!/usr/bin/env python3
"""Day store for the Python simulator: one pickle per year, data/sim/nifty_<YYYY>.pkl

Each trading day -> {
  "date": YYYYMMDD, "spot": float32[375,4] (open, high, low, close per minute, 09:15 = 0),
  "chains": {expiry_date: {"strikes": int32[n], "rank": 0|1,
                            "o","h","l","c": float32[2, n, 375] (0 = CE, 1 = PE; NaN = no price yet), "oi": float32[2, n, 375]}}}
Source precedence per trade date: Upstox full chains > Breeze 2024 full chains > Dhan (ATM+/-10, next week ATM+/-3).
Bars are already forward-filled within the day by the ETLs. Only strikes on the 50-point grid are kept.
Usage: python research/sim/store.py   (rebuilds all years)
"""
import os, pickle, sys
import numpy as np
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data/sim")
SRC = ["NIFTY_UPX", "NIFTY_OHLC", "NIFTY_DHAN"]


def build():
    os.makedirs(OUT, exist_ok=True)
    owner = {}
    for src in SRC:
        ds = pl.scan_parquet(f"{ROOT}/data/parquet/{src}/*/*.parquet").select("trade_date").unique().collect()["trade_date"].to_list()
        for d in ds:
            owner.setdefault(d, src)
    years = sorted({d // 10000 for d in owner})
    for y in years:
        days = {}
        for src in SRC:
            mine = [d for d, s in owner.items() if s == src and d // 10000 == y]
            if not mine:
                continue
            x = (pl.scan_parquet(f"{ROOT}/data/parquet/{src}/*/*.parquet").filter(pl.col("trade_date").is_in(mine) & (pl.col("strike") % 50 == 0))
                 .select("trade_date", "expiry_date", "expiry_rank", "minute_idx", "strike", "is_call", "open", "high", "low", "close", "oi",
                         "spot_open", "spot_high", "spot_low", "spot_close").collect())
            for (d,), g in x.group_by(["trade_date"]):
                sp = g.select("minute_idx", "spot_open", "spot_high", "spot_low", "spot_close").unique("minute_idx").sort("minute_idx")
                spot = np.full((375, 4), np.nan, np.float32)
                spot[sp["minute_idx"].to_numpy()] = sp.select("spot_open", "spot_high", "spot_low", "spot_close").to_numpy()
                chains = {}
                for (e, r), h in g.group_by(["expiry_date", "expiry_rank"]):
                    ks = np.array(sorted(h["strike"].unique().to_list()), np.int32)
                    ki = {k: i for i, k in enumerate(ks)}
                    arr = {f: np.full((2, len(ks), 375), np.nan, np.float32) for f in ("o", "h", "l", "c", "oi")}
                    t = (h["is_call"].not_().cast(pl.Int32).to_numpy(), np.array([ki[k] for k in h["strike"].to_list()]), h["minute_idx"].to_numpy())
                    for f, col in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("oi", "oi")):
                        arr[f][t] = h[col].to_numpy()
                    chains[int(e)] = {"strikes": ks, "rank": int(r), **arr}
                days[int(d)] = {"date": int(d), "spot": spot, "chains": chains}
        pickle.dump(days, open(f"{OUT}/nifty_{y}.pkl", "wb"), protocol=5)
        print(y, "days", len(days), flush=True)


def load(years=None):
    out = {}
    for f in sorted(os.listdir(OUT)):
        if f.startswith("nifty_") and (years is None or int(f[6:10]) in years):
            out.update(pickle.load(open(f"{OUT}/{f}", "rb")))
    return dict(sorted(out.items()))


if __name__ == "__main__":
    build()
