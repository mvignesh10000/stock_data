# Working rules for this repo (read first)

## Persistence: the cloud container can be recycled at any time
- Nothing on local disk is safe. Background `nohup` processes die with the container, which happens soon after the
  session goes idle. Run long jobs as tracked background tasks (`run_in_background`, at most 2 h; use
  `timeout 6900 …` and restart the next chunk when notified), and make every job resumable.
- **Code, configs, Markdown, small results (< ~5 MB)** → commit and push to GitHub on the working branch
  (currently `claude/nifty-options-strategy-discovery-ifg0wm`) right after each meaningful step.
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
| `nifty-1min-2017-2020` | Zenodo 10899828 mirror (CC0) + canonical Parquet of the monthly-expiry options |
| `stock-data` | the user's own older archive, do not modify |

## Credentials
- `UPSTOX_ACCESS_TOKEN` is an environment variable of the "Strategy" cloud environment: an extended token valid to
  2027-10-09, read-only (data APIs). Live orders need a normal daily token and the user's static IP, so they run on
  the user's machine, never here.
- `KAGGLE_API_TOKEN`: use the environment variable if present. Never write tokens into tracked files or logs.

## Project map
- `etl/`: Upstox backfill (resumable, rate-limited 960/30 min), lake → engine Parquet (`etl_upstox.py`), Zenodo
  2017-20 ETL, bid/ask recorder + schedulers (`etl/scheduler/`, `CLAUDE_SCHEDULER.md`), `kaggle_sync.py`.
- `opt_engine/`: Rust backtester (`cargo build --release`; CLI build-cache/info/backtest/batch-sweep).
- `research/`: experiment scripts; `EXPERIMENT_LOG.md` holds results, newest round last.
- `execution/upstox_ironfly.py`: Upstox OrderApiV3 executor (paper by default).
