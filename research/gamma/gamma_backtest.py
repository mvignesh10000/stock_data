#!/usr/bin/env python3
"""Gamma Move (short-covering breakout) option-buying backtest on NSE stock options, 15m bars.

Data: Kaggle mvignesh2k19/upstox-stock-options-15m-<symbol> (expired monthly stock options, 15m OHLCV+OI,
plus underlying_daily__<SYM>.parquet).  Pull with:  python3 research/gamma/gamma_backtest.py --pull
Run:  python3 -I research/gamma/gamma_backtest.py            (base run + sweeps -> results/gamma/)
"""
import argparse, glob, itertools, json, os, subprocess, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data/gamma/opt")
OUT = os.path.join(ROOT, "results/gamma")
TIMES = pd.date_range("2000-01-01 09:15", "2000-01-01 15:15", freq="15min").time
NB = len(TIMES)  # 25 bars/day

BASE = dict(
    dte_max=14, lookback=40, prox=0.02, near_steps=2,          # setup (daily)
    vol_k=2.0, min_lots=5, oi_x=0.03, oi_bars=3,               # 15m trigger
    sl_bars=8, max_risk=0.60, first_bar=1, last_bar=22,        # stop / entry window (bar idx 1=09:30 .. 22=14:45)
    exit_mode="target", target=1.0, hold_days=2, trail_bars=4, # exits
    slip=0.01, capital=1_000_000, risk_pct=0.01, max_prem_pct=0.15,
)


def pull():
    env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("kaggle_api_key", ""))
    out = subprocess.run(["kaggle", "datasets", "list", "--mine", "--csv", "-s", "upstox-stock-options-15m", "--page-size", "100"],
                         capture_output=True, text=True, env=env).stdout
    refs = [l.split(",")[0] for l in out.splitlines() if "stock-options-15m" in l]
    for r in refs:
        subprocess.run(["kaggle", "datasets", "download", r, "-p", f"{DATA}/{r.split('/')[1]}", "--unzip", "-q"], env=env)


def load_symbol(d):
    fs = [f for f in glob.glob(d + "/options__*.parquet")]
    parts = [pd.read_parquet(f) for f in fs]
    parts = [p for p in parts if len(p)]
    if not parts:
        return None
    o = pd.concat(parts, ignore_index=True)
    o = o[(o.ts.dt.time >= TIMES[0]) & (o.ts.dt.time <= TIMES[-1])]
    o = o.drop_duplicates(["instrument_key", "ts"])
    o["d"] = o.ts.dt.normalize()
    o["oi"] = o.oi.where(o.oi > 0)
    u = pd.read_parquet(glob.glob(d + "/underlying_daily__*.parquet")[0])
    u = u.rename(columns={"trade_date": "d"}).assign(d=lambda x: pd.to_datetime(x.d)).sort_values("d").reset_index(drop=True)
    return o, u


def grid(c, days):
    """Contract bars on a full 15m grid: missing bars -> flat at last close, volume 0; OI ffilled."""
    idx = pd.MultiIndex.from_product([days, range(NB)], names=["d", "b"])
    c = c.assign(b=((c.ts.dt.hour * 60 + c.ts.dt.minute) - 555) // 15).set_index(["d", "b"])
    c = c[~c.index.duplicated()].reindex(idx)
    real = c.close.notna().values
    cl = c.close.ffill()
    for k in ("open", "high", "low"):
        c[k] = c[k].fillna(cl)
    c["close"] = cl
    c["volume"] = c.volume.fillna(0)
    c["oi"] = c.oi.ffill()
    c["real"] = real
    return c.reset_index()


def candidates(o, u, p):
    """Daily setups: (expiry, day, side, strike). Resistance/support from rolling swing, peak-OI strike near it."""
    out = []
    days_all = u.d.values
    hi, lo, cl = u.high.values, u.low.values, u.close.values
    for exp, oe in o.groupby("expiry"):
        e = pd.Timestamp(exp)
        strikes = np.sort(oe.strike.unique())
        step = np.median(np.diff(strikes)) if len(strikes) > 1 else 0
        # strike step actually used near the money = smallest common gap
        step = pd.Series(np.diff(strikes)).mode().min() if len(strikes) > 1 else 0
        if step <= 0:
            continue
        td = sorted(oe.d.unique())
        for D in td:
            dte = (e - D).days
            if dte < 1 or dte > p["dte_max"]:
                continue
            i = np.searchsorted(days_all, np.datetime64(D))
            if i >= len(days_all) or days_all[i] != np.datetime64(D) or i < p["lookback"] + 4:
                continue
            w = slice(i - p["lookback"] - 3, i - 3)       # swing window ends 4 days before D (a real older level)
            R, S, pc = hi[w].max(), lo[w].min(), cl[i - 1]
            # OI snapshot at prior trading day close (last known OI per contract up to D-1)
            prev = oe[oe.d < D]
            if prev.empty:
                continue
            snap = prev.sort_values("ts").groupby("instrument_key").last()
            for side, lvl, ok in (("CE", R, 0.0 <= (R - pc) / R <= p["prox"] or 0.0 < (pc - R) / R <= 0.01),
                                  ("PE", S, 0.0 <= (pc - S) / S <= p["prox"] or 0.0 < (S - pc) / S <= 0.01)):
                if not ok:
                    continue
                s = snap[(snap.opt == side) & ((snap.strike - lvl).abs() <= p["near_steps"] * step) & snap.oi.notna()]
                if s.empty:
                    continue
                r = s.sort_values("oi").iloc[-1]
                out.append(dict(expiry=exp, d=D, side=side, key=s.oi.idxmax(), strike=r.strike, lot=int(r.lot_size),
                                level=lvl, prev_close=pc, dte=dte, peak_oi=r.oi))
    return pd.DataFrame(out)


def costs(buy, sell, qty):
    bv, sv = buy * qty, sell * qty
    brk = 40.0                                       # Rs20 flat per order, two orders
    exch = 0.000356 * (bv + sv)                      # NSE option premium turnover charge
    sebi = 1e-6 * (bv + sv)
    stt = 0.001 * sv                                 # 0.1% on sell premium
    stamp = 0.00003 * bv
    gst = 0.18 * (brk + exch + sebi)
    return brk + exch + sebi + stt + stamp + gst


def simulate(g, row, p, days):
    """Scan the selected contract; return trade dict or None. g = grid df of that contract."""
    g = g.reset_index(drop=True)
    n = len(g)
    vol, oi = g.volume.values, g.oi.values
    sma = pd.Series(vol).rolling(20).mean().shift(1).values
    day_idx = (g.d.values == np.datetime64(row.d))
    start = np.flatnonzero(day_idx)
    if len(start) == 0:
        return None
    s0 = start[0]
    lot = row.lot
    for i in range(s0 + p["first_bar"], s0 + p["last_bar"] + 1):
        if i < 22 or i + 1 >= n or not g.real.values[i]:
            continue
        if vol[i] < p["vol_k"] * sma[i] or vol[i] < p["min_lots"] * lot:
            continue
        o3 = oi[i - p["oi_bars"]]
        if not (oi[i] / o3 - 1 <= -p["oi_x"]):
            continue
        if not (g.close.values[i] > g.open.values[i] and g.close.values[i] > g.high.values[i - 1]):
            continue
        entry_raw = g.open.values[i + 1]
        sl = g.low.values[i - p["sl_bars"]:i + 1].min()
        entry = entry_raw * (1 + p["slip"])
        if sl >= entry_raw or (entry_raw - sl) / entry_raw > p["max_risk"]:
            continue
        # ---- exits
        edays = sorted(set(g.d.values[s0:]))
        last_day = edays[min(p["hold_days"] - 1, len(edays) - 1)]
        tgt = entry_raw * (1 + p["target"]) if p["exit_mode"] == "target" else np.inf
        stop, why, px = sl, None, None
        for j in range(i + 1, n):
            op, hi_, lo_, cl_ = g.open.values[j], g.high.values[j], g.low.values[j], g.close.values[j]
            if lo_ <= stop:
                px, why = min(op, stop), "SL"; break
            if hi_ >= tgt:
                px, why = max(op, tgt), "TARGET"; break
            if g.d.values[j] >= np.datetime64(last_day) and g.b.values[j] == NB - 1:
                px, why = cl_, "TIME"; break
            if p["exit_mode"] == "trail" and j >= i + p["trail_bars"]:
                stop = max(stop, g.low.values[j - p["trail_bars"] + 1:j + 1].min()) if g.close.values[j] > entry_raw else stop
        if px is None:
            px, why, j = g.close.values[-1], "TIME", n - 1
        j_exit = j
        sell = px * (1 - p["slip"])
        risk_ps = max(entry - sl * (1 - p["slip"]), 0.05)
        lots = int(min(p["capital"] * p["risk_pct"] / (risk_ps * lot), p["capital"] * p["max_prem_pct"] / (entry * lot)))
        lots = max(lots, 1)
        q = lots * lot
        c = costs(entry, sell, q)
        gross = (sell - entry) * q
        return dict(symbol=row.symbol, side=row.side, expiry=row.expiry, strike=row.strike, d=row.d, dte=row.dte,
                    entry_ts=g.d.values[i + 1] + np.timedelta64(555 + 15 * int(g.b.values[i + 1]), "m"),
                    exit_ts=g.d.values[j_exit] + np.timedelta64(555 + 15 * int(g.b.values[j_exit]), "m"),
                    entry=entry, sl=sl, exit=sell, reason=why, lots=lots, lot=lot, qty=q,
                    ret=sell / entry - 1, R=(sell - entry) / (entry - sl * (1 - p["slip"])) if entry > sl else np.nan,
                    gross=gross, cost=c, pnl=gross - c, pnl_1lot=(sell - entry) * lot - costs(entry, sell, lot))
    return None


def build(symbols, p):
    cands, grids = [], {}
    for sym, (o, u) in symbols.items():
        c = candidates(o, u, p)
        if c.empty:
            continue
        c["symbol"] = sym
        cands.append(c)
        grids[sym] = (o, sorted(o.d.unique()))
    return pd.concat(cands, ignore_index=True), grids


def run(cands, symbols, p, gcache):
    trades = []
    busy = {}
    for row in cands.sort_values("d").itertuples():
        o = symbols[row.symbol][0]
        k = (row.symbol, row.key)
        if k not in gcache:
            c = o[o.instrument_key == row.key]
            days = sorted(o[o.expiry == row.expiry].d.unique())
            gcache[k] = grid(c, days)
        if busy.get(row.symbol, pd.Timestamp.min) >= row.d:
            continue
        t = simulate(gcache[k], row, p, None)
        if t:
            busy[row.symbol] = pd.Timestamp(t["exit_ts"]).normalize()
            trades.append(t)
    return pd.DataFrame(trades)


def stats(t, p, label=""):
    if t.empty:
        return dict(label=label, n=0)
    w, l = t[t.pnl > 0], t[t.pnl <= 0]
    eq = t.sort_values("exit_ts").pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    return dict(label=label, n=len(t), win=round((t.pnl > 0).mean() * 100, 1), avg_ret=round(t.ret.mean() * 100, 1),
                med_ret=round(t.ret.median() * 100, 1), avg_R=round(t.R.mean(), 2),
                pf=round(w.pnl.sum() / -l.pnl.sum(), 2) if len(l) and l.pnl.sum() < 0 else np.inf,
                net=int(t.pnl.sum()), cost=int(t.cost.sum()), net_1lot=int(t.pnl_1lot.sum()),
                maxdd=int(dd), ret_pct_cap=round(t.pnl.sum() / p["capital"] * 100, 1),
                hit2x=round((t.ret >= 1).mean() * 100, 1), best=round(t.ret.max() * 100))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--no-sweep", action="store_true")
    a = ap.parse_args()
    if a.pull:
        return pull()
    os.makedirs(OUT, exist_ok=True)
    symbols = {}
    for d in sorted(glob.glob(DATA + "/*")):
        r = load_symbol(d)
        if r:
            symbols[os.path.basename(d).split("15m-")[1].upper()] = r
    print("symbols", len(symbols), file=sys.stderr)
    cands, _ = build(symbols, BASE)
    print("daily candidates", len(cands), file=sys.stderr)
    gcache = {}
    base = run(cands, symbols, BASE, gcache)
    base.to_csv(f"{OUT}/trades_base.csv", index=False)
    rows = [stats(base, BASE, "BASE")]
    for side in ("CE", "PE"):
        rows.append(stats(base[base.side == side], BASE, f"BASE {side}"))
    sweeps = [("slip", [0, 0.005, 0.01, 0.02, 0.03]), ("exit_mode", ["target", "trail", "time"]),
              ("target", [0.5, 1.0, 2.0]), ("hold_days", [1, 2, 3]), ("vol_k", [1.5, 2.0, 3.0]),
              ("oi_x", [0.01, 0.03, 0.05, 0.10]), ("sl_bars", [4, 8, 12]), ("lookback", [20, 40, 60])]
    if not a.no_sweep:
        for k, vals in sweeps:
            for v in vals:
                if v == BASE[k]:
                    continue
                p = dict(BASE, **{k: v})
                c = cands if k != "lookback" else build(symbols, p)[0]
                rows.append(stats(run(c, symbols, p, gcache), p, f"{k}={v}"))
    pd.DataFrame(rows).to_csv(f"{OUT}/summary.csv", index=False)
    print(pd.DataFrame(rows).to_string())


if __name__ == "__main__":
    main()
