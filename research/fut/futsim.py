#!/usr/bin/env python3
"""Intraday NIFTY futures simulator (index 1-min as the price proxy; intraday futures moves track the index point for point).

Data: data/sim/spot_1min.npz built from debashis74017 NIFTY 50 minute (2015-01-09 .. 2021-12-31) + Upstox index 1-min
(2022-01-03 ..), bar-start timestamps, 375-minute grid 09:15..15:29 (later bars dropped). VIX daily open from the debashis
INDIA VIX minute file + Upstox VIX.
Execution: signal on a bar close -> market fill at that close +/- SLIP points; stops checked on later bars' high/low, filled at
the stop (or the bar open if it gapped through) +/- (SLIP + STOP_EXTRA); targets at the level; time exit at the EXIT bar close.
No overnight positions: everything is flat by EXIT (default 15:25 bar close).
Costs per round trip at today's rates (from 1-Apr-2026): brokerage Rs 20 x 2, STT 0.05 % on the sell leg, NSE futures
transaction 0.00173 % both legs, SEBI Rs 10/crore, stamp 0.002 % on the buy leg, GST 18 % on brokerage + exchange + SEBI.
1 lot = 65.
"""
import datetime as dt, math, os
import numpy as np
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEB = "/tmp/claude-0/-home-user-stock-data/4d57aa79-ef69-5c3b-9d09-601b4b3f1206/scratchpad/deb"
NPZ = os.path.join(ROOT, "data/sim/spot_1min.npz")
LOT, SLIP, STOP_EXTRA = 65, 1.0, 1.0
M = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:5]) - 555  # bar START index (09:15 -> 0)


def build():
    a = pl.read_csv(f"{DEB}/NIFTY%2050_minute.csv").with_columns(pl.col("date").str.to_datetime("%Y-%m-%d %H:%M:%S").alias("ts")).drop("date")
    a = a.filter(pl.col("ts") < pl.datetime(2022, 1, 1)).select("ts", "open", "high", "low", "close")
    b = pl.read_parquet(f"{ROOT}/data/upstox/index/NIFTY_1min.parquet").select("ts", "open", "high", "low", "close")
    x = pl.concat([a.with_columns(pl.col("ts").cast(pl.Datetime("us"))), b.with_columns(pl.col("ts").cast(pl.Datetime("us")))]).with_columns(
        pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"),
        (pl.col("ts").dt.hour().cast(pl.Int32) * 60 + pl.col("ts").dt.minute().cast(pl.Int32) - 555).alias("m")).filter(pl.col("m").is_between(0, 374))
    cnt = x.group_by("d").len()
    good = cnt.filter(pl.col("len") >= 300)["d"].sort().to_list()  # drop special/short sessions
    x = x.filter(pl.col("d").is_in(good)).sort("d", "m")
    dates = np.array(good, np.int64)
    arr = np.full((len(dates), 375, 4), np.nan, np.float32)
    di = {d: i for i, d in enumerate(dates)}
    arr[np.array([di[d] for d in x["d"].to_list()]), x["m"].to_numpy()] = x.select("open", "high", "low", "close").to_numpy()
    for i in range(len(dates)):  # forward-fill holes
        for m in range(1, 375):
            if np.isnan(arr[i, m, 3]):
                arr[i, m] = arr[i, m - 1, 3]
        if np.isnan(arr[i, 0, 3]):
            j = np.argmax(~np.isnan(arr[i, :, 3]))
            arr[i, :j] = arr[i, j, 0]
    va = pl.read_csv(f"{DEB}/INDIA%20VIX_minute.csv").with_columns(pl.col("date").str.slice(0, 10).str.replace_all("-", "").cast(pl.Int64).alias("d"))
    vb = pl.read_parquet(f"{ROOT}/data/upstox/index/VIX_1min.parquet").with_columns(pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"))
    vix = dict(pl.concat([va.group_by("d").agg(pl.col("open").first()), vb.group_by("d").agg(pl.col("open").first())]).unique("d", keep="last").iter_rows())
    v = np.array([vix.get(int(d), np.nan) for d in dates], np.float32)
    np.savez_compressed(NPZ, dates=dates, px=arr, vix=v)
    print("days", len(dates), dates[0], "->", dates[-1])


def load():
    z = np.load(NPZ)
    return z["dates"], z["px"], z["vix"]


def cost(entry, exit_, direction):
    """Rs per round trip, 1 lot. direction +1 long (buy then sell), -1 short (sell then buy)."""
    buy, sell = (entry, exit_) if direction > 0 else (exit_, entry)
    nb, ns = buy * LOT, sell * LOT
    brok = 40.0
    exch = (nb + ns) * 0.0000173
    sebi = (nb + ns) * 1e-6
    return brok + ns * 0.0005 + exch + sebi + nb * 0.00002 + 0.18 * (brok + exch + sebi)


def trade(px, m_in, direction, stop=None, target=None, trail=None, exit_m=M("15:25")):
    """Execute one intraday trade on a day's (375,4) array. trail = points behind the best close (ratchet, never loosens).
    Returns (pnl_points_after_slippage, entry_fill, exit_fill, exit_m, reason)."""
    e = float(px[m_in, 3]) + direction * SLIP
    best = e
    st = stop
    for m in range(m_in + 1, exit_m + 1):
        o, h, l, c = (float(v) for v in px[m])
        if st is not None:
            if direction > 0 and l <= st:
                f = min(st, o) - SLIP - STOP_EXTRA
                return (f - e), e, f, m, "stop"
            if direction < 0 and h >= st:
                f = max(st, o) + SLIP + STOP_EXTRA
                return (e - f), e, f, m, "stop"
        if target is not None:
            if direction > 0 and h >= target:
                return (max(target, o) - e), e, max(target, o), m, "target"
            if direction < 0 and l <= target:
                return (e - min(target, o)), e, min(target, o), m, "target"
        if trail is not None:
            best = max(best, c) if direction > 0 else min(best, c)
            ts = best - trail if direction > 0 else best + trail
            st = ts if st is None else (max(st, ts) if direction > 0 else min(st, ts))
    f = float(px[exit_m, 3]) - direction * SLIP
    return direction * (f - e), e, f, exit_m, "time"


if __name__ == "__main__":
    build()
