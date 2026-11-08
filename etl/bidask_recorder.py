#!/usr/bin/env python3
"""Live bid/ask recorder: Upstox MarketDataStreamerV3 -> 1-second snapshots -> Parquet (append-only parts).

Records, for NIFTY and SENSEX, the two nearest expiries, every CE/PE within ATM +/- R (NIFTY 600, SENSEX 2000;
re-centred every 10 min as spot moves), plus the index and India VIX:
  ts (IST, 1 s grid), name, expiry, strike, opt, ltp, bid, bid_qty, ask, ask_qty, oi, iv, delta, gamma, theta, vega,
  vtt (cumulative day volume), spot.
Mode "option_greeks" (1 depth level + greeks), which is enough for spread/slippage modelling and much lighter than "full".

Output: data/upstox/bidask/date=YYYY-MM-DD/part-HHMMSS.parquet (a new part every 60 s, so a crash loses <= 60 s).
Run window: starts immediately, stops itself at 15:41 IST (or --until HH:MM). Safe to start at any time; the
scheduler (etl/scheduler/) launches it at 09:12 IST on weekdays.

Token: data/upstox/token.txt or env UPSTOX_ACCESS_TOKEN (same as the backfill). Upstox tokens expire daily at 03:30
IST, so generate one each morning before 09:12 (see etl/scheduler/README.md).
Market data needs no static IP (only order APIs do), so this can run on any machine.
"""
import datetime as dt, json, os, ssl, sys, threading, time, uuid
import polars as pl
import websocket  # pip install websocket-client

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import MarketDataFeedV3_pb2 as pb  # noqa: E402  (vendored from upstox-python-sdk 2.30.0)
from upstox_backfill import get, token, LAKE, IDX  # noqa: E402

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
RANGE = {"NIFTY": 600, "SENSEX": 2000}
OUT = os.path.join(LAKE, "bidask")
STATE, META, LOCK = {}, {}, threading.Lock()
SUBS = set()


def now_ist():
    return dt.datetime.now(IST).replace(tzinfo=None)


def log(*a):
    s = now_ist().strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(s, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "recorder.log"), "a") as f:
        f.write(s + "\n")


def universe():
    """Instrument keys to subscribe now: index + VIX + ATM +/- R for the 2 nearest expiries of each name."""
    keys = {IDX["VIX"]}
    META[IDX["VIX"]] = ("VIX", None, None, None)
    for name in ("NIFTY", "SENSEX"):
        k = IDX[name]
        keys.add(k)
        META[k] = (name, None, None, None)
        with LOCK:
            spot = STATE.get(k, {}).get("ltp")
        if not spot:
            q = (get("/v2/market-quote/ltp", {"instrument_key": k}) or {}).get("data", {})
            spot = float(list(q.values())[0]["last_price"]) if q else None
        cons = (get("/v2/option/contract", {"instrument_key": k}) or {}).get("data", [])
        if not spot or not cons:
            log("universe: no spot/contracts for", name)
            continue
        exps = sorted({c["expiry"] for c in cons})[:2]
        for c in cons:
            if c["expiry"] in exps and abs(c["strike_price"] - spot) <= RANGE[name]:
                keys.add(c["instrument_key"])
                META[c["instrument_key"]] = (name, c["expiry"], int(c["strike_price"]), c["instrument_type"])
    return keys


def on_message(ws, msg):
    r = pb.FeedResponse()
    r.ParseFromString(msg)
    with LOCK:
        for k, f in r.feeds.items():
            s = STATE.setdefault(k, {})
            if f.HasField("firstLevelWithGreeks"):
                g = f.firstLevelWithGreeks
                s["ltp"] = g.ltpc.ltp
                d = g.firstDepth
                s.update(bid=d.bidP, bid_qty=d.bidQ, ask=d.askP, ask_qty=d.askQ, oi=g.oi, iv=g.iv, vtt=g.vtt,
                         delta=g.optionGreeks.delta, gamma=g.optionGreeks.gamma, theta=g.optionGreeks.theta, vega=g.optionGreeks.vega)
            elif f.HasField("fullFeed"):
                ff = f.fullFeed
                if ff.HasField("indexFF"):
                    s["ltp"] = ff.indexFF.ltpc.ltp
                else:
                    m = ff.marketFF
                    s["ltp"] = m.ltpc.ltp
                    if m.marketLevel.bidAskQuote:
                        q = m.marketLevel.bidAskQuote[0]
                        s.update(bid=q.bidP, bid_qty=q.bidQ, ask=q.askP, ask_qty=q.askQ)
                    s.update(oi=m.oi, iv=m.iv, vtt=m.vtt)
            elif f.HasField("ltpc"):
                s["ltp"] = f.ltpc.ltp


def send(ws, method, keys, mode=None):
    data = {"instrumentKeys": sorted(keys)}
    if mode:
        data["mode"] = mode
    ws.send(json.dumps({"guid": str(uuid.uuid4()), "method": method, "data": data}).encode(), opcode=websocket.ABNF.OPCODE_BINARY)


def subscribe(ws, keys):
    new = keys - SUBS
    if not new:
        return
    idx = {k for k in new if META.get(k, (None, None))[1] is None}
    opts = sorted(new - idx)
    if idx:
        send(ws, "sub", idx, "ltpc")
    for i in range(0, len(opts), 100):
        send(ws, "sub", set(opts[i:i + 100]), "option_greeks")
    SUBS.update(new)
    log("subscribed", len(new), "new; total", len(SUBS))


def snapshot_rows(ts):
    rows = []
    with LOCK:
        spot = {n: STATE.get(IDX[n], {}).get("ltp") for n in ("NIFTY", "SENSEX", "VIX")}
        for k in SUBS:
            s = STATE.get(k)
            if not s or "ltp" not in s:
                continue
            name, exp, strike, opt = META.get(k, ("?", None, None, None))
            rows.append({"ts": ts, "key": k, "name": name, "expiry": exp, "strike": strike, "opt": opt,
                         "ltp": s.get("ltp"), "bid": s.get("bid"), "bid_qty": s.get("bid_qty"), "ask": s.get("ask"),
                         "ask_qty": s.get("ask_qty"), "oi": s.get("oi"), "iv": s.get("iv"), "delta": s.get("delta"),
                         "gamma": s.get("gamma"), "theta": s.get("theta"), "vega": s.get("vega"), "vtt": s.get("vtt"),
                         "spot": spot.get(name if name in spot else "NIFTY")})
    return rows


SCHEMA = {"ts": pl.Datetime("ms"), "key": pl.Utf8, "name": pl.Utf8, "expiry": pl.Utf8, "strike": pl.Int32, "opt": pl.Utf8,
          "ltp": pl.Float32, "bid": pl.Float32, "bid_qty": pl.Int64, "ask": pl.Float32, "ask_qty": pl.Int64, "oi": pl.Float64,
          "iv": pl.Float32, "delta": pl.Float32, "gamma": pl.Float32, "theta": pl.Float32, "vega": pl.Float32,
          "vtt": pl.Int64, "spot": pl.Float32}


def flush(buf):
    if not buf:
        return
    t = buf[-1]["ts"]
    d = f"{OUT}/date={t:%Y-%m-%d}"
    os.makedirs(d, exist_ok=True)
    p = f"{d}/part-{t:%H%M%S}.parquet"
    pl.DataFrame(buf, schema=SCHEMA).write_parquet(p + ".tmp", compression="zstd")
    os.replace(p + ".tmp", p)


def main():
    until = "15:41"
    if "--until" in sys.argv:
        until = sys.argv[sys.argv.index("--until") + 1]
    stop_at = dt.datetime.combine(now_ist().date(), dt.time.fromisoformat(until))
    while now_ist() < stop_at:
        SUBS.clear()
        auth = (get("/v3/feed/market-data-feed/authorize") or {}).get("data", {})
        url = auth.get("authorized_redirect_uri")
        if not url:
            log("authorize failed; retry in 30 s")
            time.sleep(30)
            continue
        opened = threading.Event()
        ws = websocket.WebSocketApp(url, on_message=on_message, on_open=lambda w: opened.set(),
                                    on_error=lambda w, e: log("ws error", e), on_close=lambda w, c, m: log("ws closed", c, m))
        th = threading.Thread(target=ws.run_forever, kwargs={"sslopt": {"cert_reqs": ssl.CERT_REQUIRED}, "ping_interval": 20}, daemon=True)
        th.start()
        if not opened.wait(20):
            log("ws did not open; retry")
            ws.close()
            time.sleep(10)
            continue
        log("ws open")
        subscribe(ws, universe())
        buf, last_flush, last_uni = [], time.time(), time.time()
        nxt = time.time() // 1 + 1
        while th.is_alive() and now_ist() < stop_at:
            time.sleep(max(0, nxt - time.time()))
            nxt += 1
            buf.extend(snapshot_rows(now_ist().replace(microsecond=0)))
            if time.time() - last_flush >= 60:
                flush(buf)
                buf, last_flush = [], time.time()
            if time.time() - last_uni >= 600:  # re-centre strikes as spot moves
                try:
                    subscribe(ws, universe())
                except Exception as e:  # noqa: BLE001
                    log("universe refresh failed", e)
                last_uni = time.time()
        flush(buf)
        ws.close()
        if now_ist() < stop_at:
            log("reconnecting in 5 s")
            time.sleep(5)
    log("stop time reached, exiting")


if __name__ == "__main__":
    main()
