# Running the data jobs as Claude scheduled tasks (cloud), with Kaggle as the permanent store

Cloud sessions start from a fresh container, so every job is **pull from Kaggle → add new data → push a new
Kaggle version**. Nothing depends on the container surviving.

| Kaggle dataset (private) | What | Updated by |
|---|---|---|
| `mvignesh2k19/upstox-nifty-sensex-1min` | NIFTY/SENSEX/VIX 1-min index + every expired NIFTY & SENSEX weekly option, 1-min OHLC+OI | Task B (weekly) |
| `mvignesh2k19/upstox-bidask-1s-YYYY-MM` | 1-second bid/ask, qty, LTP, OI, IV, greeks; ATM ±600 NIFTY / ±2000 SENSEX, 2 nearest expiries | Task A (daily), one dataset per month |
| `mvignesh2k19/nifty-1min-2017-2020` | Zenodo 10899828 mirror (CC0) + canonical Parquet (monthly expiries) | static |

## One-time setup (you)
1. **Kaggle token in the cloud environment.** Open claude.ai/code → environment **"Strategy"** → Environment variables,
   and add `KAGGLE_API_TOKEN=<your KGAT_… token>`. `UPSTOX_ACCESS_TOKEN` (the 1-year extended token) is already there.
2. Merge this branch to `main` (or keep the branch name in the prompts below).
3. Create the two scheduled tasks below (claude.ai/code → Scheduled, or ask Claude: "create a scheduled task …"),
   environment **Strategy**, repository **mvignesh10000/stock_data**, *new session each run*.

## Task A: daily bid/ask recorder
* Schedule: `CRON_TZ=Asia/Kolkata 3 9 * * 1-5` (09:03 IST, Mon–Fri)
* Prompt (paste as-is):

```
Daily Upstox bid/ask recording job for the stock_data repo. Do exactly this, no strategy work:
1. cd to the repo; git fetch origin claude/nifty-options-strategy-discovery-ifg0wm && git checkout claude/nifty-options-strategy-discovery-ifg0wm
2. pip install -q polars websocket-client protobuf kaggle
3. Check today is an NSE trading day: python3 -c "import sys;sys.path.insert(0,'etl');from upstox_backfill import get;import datetime as d;print(get(f'/v2/market/holidays/{d.date.today()}'))"
   If it is a weekend, or the response lists NFO under closed_exchanges (holiday_type TRADING_HOLIDAY), stop and report "holiday".
   (SPECIAL_TIMING days such as Muhurat trading: record only if NFO is open during 09:15-15:30; otherwise stop.)
4. python3 etl/kaggle_sync.py pull bidask      (restores this month's earlier days; prints "no dataset yet" on the 1st run of a month)
5. Record in chunks, because one background command may run at most 2 hours: start
   `python3 etl/bidask_recorder.py --until HH:MM` with run_in_background, where HH:MM (IST) is the earlier of now+110 min and 15:41.
   When it exits, start the next chunk the same way, until 15:41 IST has passed. Never run two recorders at once.
6. python3 etl/scheduler/compact_bidask.py
7. python3 etl/kaggle_sync.py push bidask
8. Report one line: rows recorded today (from data/upstox/bidask/date=<today>/day.parquet), median ATM spread %, and the Kaggle version message.
If a step fails, retry it once, then report the error; do not modify code or push to GitHub.
```

## Task B: weekly history update (newly expired contracts + index/VIX)
* Schedule: `CRON_TZ=Asia/Kolkata 17 10 * * 6` (Saturday 10:17 IST)
* Prompt:

```
Weekly Upstox history update for the stock_data repo. Do exactly this:
1. cd to the repo; git fetch origin claude/nifty-options-strategy-discovery-ifg0wm && git checkout claude/nifty-options-strategy-discovery-ifg0wm
2. pip install -q polars kaggle
3. python3 etl/kaggle_sync.py pull history
4. Run with run_in_background (it is resumable and only downloads expiries that are not already on disk; rate limit
   ~10 expiries per 30 min): python3 etl/upstox_backfill.py index NIFTY SENSEX   — note: this runs index, then NIFTY, then SENSEX.
   Wait for it to finish (re-arm if a single wait exceeds 2 h).
5. python3 etl/kaggle_sync.py push history
6. Report: number of option expiry files per index on disk, newest expiry for each, index last timestamp, Kaggle version message.
If a step fails, retry once, then report the error; do not modify code or push to GitHub.
```

## Notes
* Order placement is NOT part of these jobs: Upstox order APIs require your registered static IP and a normal daily
  token, so `execution/upstox_ironfly.py --live` must run on your own machine.
* Cost: Task A keeps a session alive ~6.5 h per trading day (mostly idle waits). If you'd rather not, run the
  same recorder on any always-on machine with `crontab.txt` / `windows_task.ps1` and keep Task B in the cloud.
* Size: about 40–60 MB per recorded day, so a month's dataset stays around 1 GB.
