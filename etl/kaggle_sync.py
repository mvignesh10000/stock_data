#!/usr/bin/env python3
"""Keep the Upstox lake on Kaggle (private datasets), so ephemeral cloud sessions can pull -> add -> push.

Datasets (owner = the Kaggle account of KAGGLE_API_TOKEN):
  history : <user>/upstox-nifty-sensex-1min        index/VIX 1-min + every expired NIFTY/SENSEX option (1-min OHLC+OI)
  bidask  : <user>/upstox-bidask-1s-YYYY-MM        1-second bid/ask/IV/greeks snapshots, one dataset per month
            (keeps each daily upload bounded, about 1 GB at most)
Kaggle stores a flat file list: lake path "options/NIFTY/expiry=2026-11-03.parquet" <-> "options__NIFTY__expiry_eq_2026-11-03.parquet".

Usage:
  python etl/kaggle_sync.py pull history|bidask [--month YYYY-MM]   # restore into data/upstox (no-op if dataset absent)
  python etl/kaggle_sync.py push history|bidask [--month YYYY-MM]   # create (private) or add a new version
Needs: pip install kaggle; env KAGGLE_API_TOKEN.
"""
import datetime as dt, glob, json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKE = os.path.join(ROOT, "data/upstox")
STAGE = os.path.join(ROOT, "data/kaggle_stage")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def user():
    from kaggle.api.kaggle_api_extended import KaggleApi
    a = KaggleApi()
    a.authenticate()
    return a.get_config_value("username")


def enc(rel):
    return rel.replace("=", "_eq_").replace("/", "__")


def dec(flat):
    return flat.replace("__", "/").replace("_eq_", "=")


def spec(kind, month):
    if kind == "history":
        files = glob.glob(f"{LAKE}/index/*_1min.parquet") + glob.glob(f"{LAKE}/options/*/expiry=*.parquet")
        return "upstox-nifty-sensex-1min", "Upstox NIFTY SENSEX options 1-min", files
    files = glob.glob(f"{LAKE}/bidask/date={month}-*/day.parquet")
    return f"upstox-bidask-1s-{month}", f"Upstox NIFTY SENSEX bid-ask 1s {month}", files


def exists(slug):
    r = subprocess.run(["kaggle", "datasets", "files", slug], capture_output=True, text=True)
    return r.returncode == 0 and "404" not in r.stdout + r.stderr


def pull(kind, month):
    slug, _, _ = spec(kind, month)
    ref = f"{user()}/{slug}"
    if not exists(ref):
        print("no dataset yet:", ref)
        return
    tmp = tempfile.mkdtemp(dir=os.path.dirname(LAKE))
    subprocess.run(["kaggle", "datasets", "download", ref, "-p", tmp, "--unzip", "-q"], check=True)
    n = 0
    for f in os.listdir(tmp):
        if not f.endswith(".parquet"):
            continue
        dst = os.path.join(LAKE, dec(f))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):  # local files win (they may be newer)
            shutil.move(os.path.join(tmp, f), dst)
            n += 1
    shutil.rmtree(tmp, ignore_errors=True)
    print("pulled", ref, n, "files ->", LAKE)


def push(kind, month):
    slug, title, files = spec(kind, month)
    if not files:
        print("nothing to push for", slug)
        return
    u = user()
    d = os.path.join(STAGE, slug)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for f in files:
        dst = os.path.join(d, enc(os.path.relpath(f, LAKE)))
        try:
            os.link(f, dst)
        except OSError:
            shutil.copy2(f, dst)
    meta = {"title": title[:50], "id": f"{u}/{slug}", "licenses": [{"name": "other"}],
            "description": "Recorded from the Upstox API for personal research (see etl/ in the stock_data repo). "
                           "File names are lake paths with '/' -> '__' and '=' -> '_eq_'."}
    json.dump(meta, open(os.path.join(d, "dataset-metadata.json"), "w"), indent=1)
    msg = f"auto update {dt.datetime.now(IST):%Y-%m-%d %H:%M} IST, {len(files)} files"
    if exists(f"{u}/{slug}"):
        cmd = ["kaggle", "datasets", "version", "-p", d, "-m", msg, "-q"]
    else:
        cmd = ["kaggle", "datasets", "create", "-p", d, "-q"]  # private by default (no --public)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(" ".join(cmd[:3]), f"{u}/{slug}:", (r.stdout + r.stderr).strip()[-300:])
    if r.returncode != 0:
        sys.exit(r.returncode)


if __name__ == "__main__":
    op, kind = sys.argv[1], sys.argv[2]
    month = sys.argv[sys.argv.index("--month") + 1] if "--month" in sys.argv else f"{dt.datetime.now(IST):%Y-%m}"
    {"pull": pull, "push": push}[op](kind, month)
