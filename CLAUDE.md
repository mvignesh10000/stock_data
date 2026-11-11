# Working rules for this repo (read first)

**Round 13 (2026-11-10): Strategy M (overnight momentum premium) in `STRATEGY_M_CARD.md`, code `research/r13/`; final choice M-safe (trend filter + 3 % wing), executor `execution/upstox_m.py`; recommended portfolio B2 + W1 + M-safe 1.**

**Latest handoff: `HANDOFF_2026-11-11_R13-14.md`** (rounds 13-14, Strategy M; read it after the older `HANDOFF_2026-11-09T1931IST.md`, which still covers data, APIs, B and W) (state, data, APIs, Kaggle, validation methods, strategies, next ideas).

Current focus (user, 2026-11-09): **NIFTY only**. SENSEX/BANKNIFTY downloads were stopped on purpose; the live candidate is
Strategy B in `STRATEGY_CARD.md` plus overnight Strategy W in `STRATEGY_W_CARD.md` (user accepted overnight on 2026-11-09); 5-year NIFTY cache = `opt_engine build-cache --parquet-dir data/parquet/NIFTY_UPX
--parquet-dir data/parquet/NIFTY_OHLC --parquet-dir data/parquet/NIFTY_DHAN --out data/cache/nifty_5y.bin`.

## Persistence: the cloud container can be recycled at any time
- Nothing on local disk is safe. Background `nohup` processes die with the container, which happens soon after the
  session goes idle. Run long jobs as tracked background tasks (`run_in_background`, at most 2 h; use
  `timeout 6900 …` and restart the next chunk when notified), and make every job resumable.
- **Code, configs, Markdown, small results (< ~5 MB)** → commit and push to GitHub on the working branch
  (currently `claude/nifty-trading-strategies-6ln3vy`) right after each meaningful step.
- **Datasets and any large files** (Parquet lake, raw downloads, big result dumps) → Kaggle via the API, never git
  (`data/` is git-ignored). Use `etl/kaggle_sync.py push|pull history|bidask`, or `kaggle datasets create/version -p DIR`
  for other sets. Datasets are private by default. Upload progress at natural checkpoints, not only at the end.
- At the start of a session, restore data with `python3 etl/kaggle_sync.py pull history` (and `pull bidask`)
  instead of re-downloading from Upstox.
- Engine caches (`data/cache/*.bin`) are rebuildable from Parquet with `opt_engine build-cache`; no need to store them.

## Kaggle datasets (account mvignesh2k19, all private)
| Dataset | Contents |
|---|---|
| `upstox-nifty-sensex-1min` | Upstox lake: NIFTY/SENSEX/VIX 1-min index + expired NIFTY/SENSEX weekly options (1-min OHLC+OI) |
| `upstox-bidask-1s-YYYY-MM` | 1-second bid/ask recordings (etl/bidask_recorder.py), one dataset per month |
| `dhan-expired-options-rolling-1min` | raw Dhan rolling windows (NIFTY W1/W2, SENSEX W1, partial BANKNIFTY); `kaggle_sync.py pull dhan` |
| `nifty-dhan-weekly-1min-2021-2024` | NIFTY weekly options 2021-11..2024-10 from Dhan, canonical Parquet per year (rank 0 = current week ATM±10, rank 1 = next week ATM±3) |
| `nifty-1min-2017-2020` | Zenodo 10899828 mirror (CC0) + canonical Parquet of the monthly-expiry options |
| `stock-data` | the user's own older archive, do not modify |

## Credentials
- `UPSTOX_ACCESS_TOKEN` is an environment variable of the "Strategy" cloud environment: an extended token valid to
  2027-10-09, read-only (data APIs). Live orders need a normal daily token and the user's static IP, so they run on
  the user's machine, never here.
- Dhan: read-only access token (short-lived, about 1 day) supplied by the user in chat; keep it in `data/dhan/token.txt`
  (git-ignored) or env `DHAN_ACCESS_TOKEN`. Data plan valid to 2027-11-06. API quirks in `etl/dhan_rolling.py` docstring:
  rollingoption only accepts toDate = fromDate + 1 day (returns both days), needs the `client-id` header, and
  expiryCode 1 is the current expiry. Limits: 5 req/s, 100k/day.
- `KAGGLE_API_TOKEN`: use the environment variable if present. Never write tokens into tracked files or logs.

## Project map
- `etl/`: Upstox backfill (resumable, rate-limited 960/30 min), lake → engine Parquet (`etl_upstox.py`), Zenodo
  2017-20 ETL, bid/ask recorder + schedulers (`etl/scheduler/`, `CLAUDE_SCHEDULER.md`), `kaggle_sync.py`.
- `opt_engine/`: Rust backtester (`cargo build --release`; CLI build-cache/info/backtest/batch-sweep).
- `research/`: experiment scripts; `EXPERIMENT_LOG.md` holds results, newest round last.
- `execution/upstox_ironfly.py`: Upstox OrderApiV3 executor (paper by default).
