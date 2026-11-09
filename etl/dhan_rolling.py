#!/usr/bin/env python3
"""Dhan expired-options downloader (POST /v2/charts/rollingoption) -> data/dhan/<SET>/<YYYY-MM-DD>.parquet

Verified behaviour (2026-11-09), which differs from the docs:
  * the request is only accepted when toDate == fromDate + 1 calendar day; it then returns BOTH days (inclusive),
    1-minute bars stamped with the bar START (matches Upstox), up to 15:39 after the Aug-2026 hours extension;
  * headers access-token + client-id (client id is inside the JWT); expiryCode 0 is rejected;
    1 = current (nearest) expiry, 2 = next, 3 = the one after;
  * data is ROLLING: "ATM+k" follows spot minute by minute; each row carries the actual strike, so per-contract
    series are rebuilt later from the union of offsets (etl/etl_dhan.py);
  * limits: data APIs 5 req/s, 100,000 req/day.
One window = (day d, day d+1) for every offset and CE/PE. Windows start on Mon, Wed, Fri, so 3 per week.
Resumable: a window file is written atomically once all its calls are done.

Token: env DHAN_ACCESS_TOKEN or file data/dhan/token.txt (never commit it).
Usage: python etl/dhan_rolling.py SET_NAME FROM TO   (sets defined in SETS below)
"""
import base64, collections, concurrent.futures as cf, datetime as dt, json, os, sys, threading, time
import polars as pl
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data/dhan")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SETS = {  # name: (exchangeSegment, securityId, expiryFlag, expiryCode, max |offset|)
    "NIFTY_W1": ("NSE_FNO", "13", "WEEK", 1, 10),
    "NIFTY_W2": ("NSE_FNO", "13", "WEEK", 2, 3),
    "BANKNIFTY_W1": ("NSE_FNO", "25", "WEEK", 1, 10),
    "SENSEX_W1": ("BSE_FNO", "51", "WEEK", 1, 10),
    "NIFTY_M1": ("NSE_FNO", "13", "MONTH", 1, 10),
}
FIELDS = ["open", "high", "low", "close", "volume", "oi", "iv", "strike", "spot"]


def tok():
    p = os.path.join(OUT, "token.txt")
    t = open(p).read().strip() if os.path.exists(p) else os.environ.get("DHAN_ACCESS_TOKEN", "")
    cid = json.loads(base64.urlsafe_b64decode(t.split(".")[1] + "=="))["dhanClientId"]
    return t, cid


class Limiter:
    def __init__(self, per_sec=4.5):
        self.gap, self.lock, self.next = 1.0 / per_sec, threading.Lock(), time.time()

    def wait(self):
        with self.lock:
            now = time.time()
            t = max(now, self.next)
            self.next = t + self.gap
        time.sleep(max(0, t - now))


LIM = Limiter()
COUNT = collections.Counter()
SESSION = requests.Session()


def log(*a):
    s = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(os.path.join(OUT, "dhan.log"), "a") as f:
        f.write(s + "\n")


def call(seg, sid, flag, code, strike, opt, d0):
    t, cid = tok()
    body = {"exchangeSegment": seg, "interval": "1", "securityId": sid, "instrument": "OPTIDX", "expiryFlag": flag,
            "expiryCode": code, "strike": strike, "drvOptionType": opt, "requiredData": FIELDS,
            "fromDate": d0.isoformat(), "toDate": (d0 + dt.timedelta(days=1)).isoformat()}
    h = {"access-token": t, "client-id": cid, "Content-Type": "application/json", "Accept": "application/json"}
    for attempt in range(8):
        LIM.wait()
        COUNT["calls"] += 1
        try:
            r = SESSION.post("https://api.dhan.co/v2/charts/rollingoption", data=json.dumps(body), headers=h, timeout=60)
        except requests.RequestException as e:
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 200:
            d = (r.json().get("data") or {})
            s = d.get("ce") or d.get("pe")
            return s if s and s.get("timestamp") else None
        if r.status_code == 429 or "DH-904" in r.text:
            COUNT["429"] += 1
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code in (400,) and "DH-905" in r.text:
            return None  # no data for this window (holiday pair, before listing, ...)
        if r.status_code in (401, 403):
            log("AUTH ERROR", r.status_code, r.text[:200])
            raise SystemExit(2)
        time.sleep(5)
    return None


def window(setname, d0):
    seg, sid, flag, code, k = SETS[setname]
    out = f"{OUT}/{setname}/{d0}.parquet"
    if os.path.exists(out) or os.path.exists(out + ".empty"):
        return 0
    jobs = [(f"ATM{o:+d}" if o else "ATM", o, opt) for o in range(-k, k + 1) for opt in ("CALL", "PUT")]
    frames = []
    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda j: (j, call(seg, sid, flag, code, j[0], j[2], d0)), jobs))
    for (strike, o, opt), s in res:
        if not s:
            continue
        n = len(s["timestamp"])
        frames.append(pl.DataFrame({
            "ts": pl.Series([int(x) for x in s["timestamp"]]).cast(pl.Int64), "offset": [o] * n, "opt": ["CE" if opt == "CALL" else "PE"] * n,
            **{f: pl.Series([float(v) if v is not None else None for v in s.get(f, [None] * n)], dtype=pl.Float64) for f in FIELDS}}))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not frames:
        open(out + ".empty", "w").close()
        return 0
    df = pl.concat(frames).with_columns(pl.from_epoch("ts", "s").dt.convert_time_zone("Asia/Kolkata").dt.replace_time_zone(None).alias("ts"))
    df.write_parquet(out + ".tmp", compression="zstd")
    os.replace(out + ".tmp", out)
    return df.height


def windows(a, b):
    d = a
    while d <= b:
        if d.weekday() in (0, 2, 4):  # Mon(Mon,Tue) Wed(Wed,Thu) Fri(Fri,Sat)
            yield d
        d += dt.timedelta(days=1)


def main():
    setname, a, b = sys.argv[1], dt.date.fromisoformat(sys.argv[2]), dt.date.fromisoformat(sys.argv[3])
    os.makedirs(OUT, exist_ok=True)
    ws = list(windows(a, b))
    log(setname, "windows", len(ws), a, "->", b)
    t0, rows = time.time(), 0
    for i, d0 in enumerate(ws):
        rows += window(setname, d0)
        if i % 20 == 0:
            el = time.time() - t0
            log(setname, f"[{i + 1}/{len(ws)}] {d0} rows {rows} calls {COUNT['calls']} 429s {COUNT['429']} {COUNT['calls'] / max(el, 1):.2f}/s")
    log(setname, "DONE rows", rows, "calls", COUNT["calls"])


if __name__ == "__main__":
    main()
