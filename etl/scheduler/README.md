# Upstox schedulers (run on your own machine)

| Job | When (IST, Mon–Fri) | Command | Output |
|---|---|---|---|
| Bid/ask recorder | 09:12 → self-stops 15:41 | `etl/scheduler/run_recorder.sh` (or `python etl/bidask_recorder.py`) | `data/upstox/bidask/date=YYYY-MM-DD/part-HHMMSS.parquet` (new part every 60 s) |
| Compaction + spread summary | 15:50 | `python etl/scheduler/compact_bidask.py` | `…/date=…/day.parquet`, `data/upstox/bidask/spread_summary.parquet` |
| Iron-fly executor (optional, paper by default) | 09:15 | `python execution/upstox_ironfly.py NIFTY` (exits at once on non-expiry days) | `data/upstox/exec.log` |
| Weekly lake top-up | Sat 10:00 | `python etl/upstox_backfill.py index NIFTY SENSEX` (resumable, only new expiries) | `data/upstox/{index,options}/` |

Install: Linux/macOS → paste `crontab.txt` into `crontab -e` (fix the path). Windows → edit and run `windows_task.ps1`.

## What gets recorded
Every second: for NIFTY (ATM ±600) and SENSEX (ATM ±2000), the two nearest expiries (current week + next week, so
calendars can be studied), CE and PE: LTP, best bid/ask and quantities, OI, IV, delta/gamma/theta/vega, cumulative
volume, plus the index and India VIX. Strikes re-centre every 10 minutes. About 260 instruments, ~5.9 M rows/day,
~40–60 MB/day zstd before compaction.

## Daily token (the one manual step)
Upstox access tokens expire at **03:30 IST every day**. Each morning before 09:12:
1. Log in through your Upstox app's OAuth URL, exchange the `code` for an `access_token` (`/v2/login/authorization/token`).
2. Write it to `data/upstox/token.txt` (one line). All scripts re-read this file on every 401, so running jobs
   pick the new token up without a restart.

Upstox also offers an "access token request" flow (`POST /v3/login/auth/token/request/{client_id}`), which sends an approve
prompt to your phone and delivers the token to a notifier webhook. That removes the browser login if you host a
small webhook receiver.

## Why not run the scheduler in the cloud session?
The cloud container is ephemeral and this branch can't be pushed (GitHub returns 403), so anything recorded there
is lost when the container is reclaimed. Market data needs no static IP, but **order placement does** (Upstox static-IP
rule), so the executor has to run on your registered machine anyway. Keep both on the same box.
