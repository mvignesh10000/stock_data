#!/usr/bin/env python3
"""Upstox (Plus) backfill -> Parquet lake under data/upstox/.

Jobs (resumable; finished units are skipped on restart):
  1. index  : 1-minute candles for NIFTY 50, SENSEX and India VIX (v3 historical-candle, monthly chunks).
  2. options: for every expired weekly expiry of NIFTY / SENSEX, every CE/PE contract whose strike lies within
              [min spot - R, max spot + R] over the 21 calendar days before expiry (R = 700 NIFTY, 2300 SENSEX);
              one request returns the contract's whole life of 1-minute OHLC+volume+OI; we keep the last 21
              calendar days (covers current-week AND next-week use for calendars).
Rate limits (official, per user): 25/s, 250/min, 1000/30 min -> we use 20/s, 240/min, 960/30 min.
Token: env UPSTOX_ACCESS_TOKEN, overridden by data/upstox/token.txt if present (re-read on every 401, so a
fresh token can be dropped in without restarting). On 401 the job sleeps and retries every 60 s.

Usage: python etl/upstox_backfill.py [index] [options NIFTY|SENSEX] [--from 2026-03-01] [--order newest]
"""
import collections, datetime as dt, json, os, sys, threading, time, urllib.parse, urllib.request, urllib.error
import polars as pl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKE = os.path.join(ROOT, "data/upstox")
B = "https://api.upstox.com"
IDX = {"NIFTY": "NSE_INDEX|Nifty 50", "SENSEX": "BSE_INDEX|SENSEX", "VIX": "NSE_INDEX|India VIX"}
RANGE = {"NIFTY": 700, "SENSEX": 2300}
LOG = os.path.join(LAKE, "backfill.log")


def log(*a):
    s = time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a") as f:
        f.write(s + "\n")


def token():
    f = os.environ.get("UPSTOX_TOKEN_FILE")  # per-account token (execution/run_b.py)
    if f and os.path.exists(os.path.expanduser(f)):
        return open(os.path.expanduser(f)).read().strip()
    p = os.path.join(LAKE, "token.txt")
    if os.path.exists(p):
        t = open(p).read().strip()
        if t:
            return t
    return os.environ.get("UPSTOX_ACCESS_TOKEN", "")


class Limiter:
    def __init__(self, limits=((1, 20), (60, 240), (1800, 960))):
        self.limits, self.hist, self.lock = limits, collections.deque(), threading.Lock()

    def wait(self):
        while True:
            with self.lock:
                now = time.time()
                while self.hist and now - self.hist[0] > 1800:
                    self.hist.popleft()
                ok = True
                for win, cap in self.limits:
                    n = sum(1 for t in self.hist if now - t <= win) if win < 1800 else len(self.hist)
                    if n >= cap:
                        ok = False
                        break
                if ok:
                    self.hist.append(now)
                    return
            time.sleep(0.05)


LIM = Limiter()


def get(path, params=None):
    url = B + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for attempt in range(1000):
        LIM.wait()
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "stock-data-backfill/1.0", "Authorization": "Bearer " + token()})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="ignore")[:300]
            if e.code == 401:
                log("401 (token expired?) — waiting 60s for a fresh token in data/upstox/token.txt or env:", body[:120])
                time.sleep(60)
                continue
            if e.code == 429:
                log("429 rate limited — backing off 30s")
                time.sleep(30)
                continue
            if e.code >= 500:
                time.sleep(5)
                continue
            log("HTTP", e.code, url, body)
            return None
        except Exception as e:  # network
            log("net error", e, "retry in 5s")
            time.sleep(5)
    return None


def enc(k):
    return urllib.parse.quote(k, safe="")


# ------------------------------------------------------------------ 1. index / VIX minute candles
def job_index(start="2022-01-01"):
    os.makedirs(f"{LAKE}/index", exist_ok=True)
    for name, key in IDX.items():
        out = f"{LAKE}/index/{name}_1min.parquet"
        have = pl.read_parquet(out) if os.path.exists(out) else None
        d0 = dt.date.fromisoformat(start)
        if have is not None and have.height:
            d0 = max(d0, (have["ts"].max().date() - dt.timedelta(days=3)))
        frames = [have] if have is not None else []
        cur, end = d0, dt.date.today()
        while cur <= end:
            to = min(end, (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1))
            r = get(f"/v3/historical-candle/{enc(key)}/minutes/1/{to}/{cur}")
            c = (r or {}).get("data", {}).get("candles", [])
            if c:
                frames.append(pl.DataFrame(c, schema=["ts", "open", "high", "low", "close", "volume", "oi"], orient="row")
                              .with_columns(pl.col("ts").str.to_datetime("%Y-%m-%dT%H:%M:%S%z").dt.convert_time_zone("Asia/Kolkata").dt.replace_time_zone(None)))
            cur = to + dt.timedelta(days=1)
        if not frames:
            log("index", name, "no data fetched")
            continue
        df = pl.concat([f.with_columns(pl.col("ts").cast(pl.Datetime("us"))) for f in frames]).unique("ts").sort("ts")
        df.write_parquet(out, compression="zstd")
        log("index", name, df.height, "rows", df["ts"].min(), "->", df["ts"].max())


# ------------------------------------------------------------------ 2. expired option contracts
def spot_range(name, expiry):
    df = pl.read_parquet(f"{LAKE}/index/{name}_1min.parquet")
    e = dt.datetime.fromisoformat(expiry)
    w = df.filter((pl.col("ts") >= e - dt.timedelta(days=21)) & (pl.col("ts") <= e + dt.timedelta(days=1)))
    if w.height == 0:
        return None
    return float(w["low"].min()), float(w["high"].max())


def job_options(name, order="newest", since=None):
    key = IDX[name]
    exps = (get("/v2/expired-instruments/expiries", {"instrument_key": key}) or {}).get("data", [])
    if since:
        exps = [e for e in exps if e >= since]
    exps = sorted(exps, reverse=(order == "newest"))
    os.makedirs(f"{LAKE}/options/{name}", exist_ok=True)
    log(name, "expiries to process:", len(exps))
    for ei, e in enumerate(exps):
        out = f"{LAKE}/options/{name}/expiry={e}.parquet"
        if os.path.exists(out):
            continue
        rng = spot_range(name, e)
        if not rng:
            log(name, e, "no spot data — skipped")
            continue
        lo, hi = rng[0] - RANGE[name], rng[1] + RANGE[name]
        cons = (get("/v2/expired-instruments/option/contract", {"instrument_key": key, "expiry_date": e}) or {}).get("data", [])
        cons = [c for c in cons if lo <= c["strike_price"] <= hi]
        cut = dt.datetime.fromisoformat(e) - dt.timedelta(days=21)
        frames, t0 = [], time.time()
        for c in cons:
            r = get(f"/v2/expired-instruments/historical-candle/{enc(c['instrument_key'])}/1minute/{e}/{(cut.date()).isoformat()}")
            cs = (r or {}).get("data", {}).get("candles", [])
            if not cs:
                continue
            frames.append(pl.DataFrame(cs, schema=["ts", "open", "high", "low", "close", "volume", "oi"], orient="row").with_columns(
                pl.col("ts").str.to_datetime("%Y-%m-%dT%H:%M:%S%z").dt.convert_time_zone("Asia/Kolkata").dt.replace_time_zone(None),
                pl.lit(int(c["strike_price"])).alias("strike"), pl.lit(c["instrument_type"]).alias("opt"),
                pl.lit(e).alias("expiry"), pl.lit(int(c["lot_size"])).alias("lot_size")))
        if frames:
            df = pl.concat(frames).with_columns(pl.col("volume").cast(pl.Int64), pl.col("oi").cast(pl.Int64))
            df.write_parquet(out + ".tmp", compression="zstd")
            os.replace(out + ".tmp", out)
            log(name, e, f"[{ei + 1}/{len(exps)}]", len(cons), "contracts", df.height, "rows", f"{time.time() - t0:.0f}s")
        else:
            log(name, e, "no candles")


if __name__ == "__main__":
    os.makedirs(LAKE, exist_ok=True)
    args = sys.argv[1:]
    since = None
    if "--from" in args:
        since = args[args.index("--from") + 1]
    order = "oldest" if "oldest" in args else "newest"
    if "index" in args:
        job_index()
    for nm in ("NIFTY", "SENSEX"):
        if nm in args:
            job_options(nm, order, since)
