# stock_data — NIFTY intraday non-directional option-selling research

| What | Where |
|---|---|
| **Interactive report** (strategies, net P&L, drawdown, month/quarter/year, ₹2L vs ₹3L) | `reports/strategy_report.html` |
| Winning strategies, exact JSON configs, IS vs OOS tables, worst days | `WINNING_STRATEGIES.md` |
| Generation-by-generation discovery log | `EXPERIMENT_LOG.md` (+ `results/discovery/EXPERIMENT_LOG_v1.md`) |
| Rust backtest engine (`opt_engine`) | `opt_engine/` |
| Parquet ETL | `etl/` |
| Discovery loop / final evaluation / report | `research/` |

## Headline (v2 — realistic engine, after external review)

| Deliverable | Where |
|---|---|
| AlgoTest field-by-field setup of the deployable strategy | `ALGOTEST_SETUP.md` |

**Deploy one strategy: the NIFTY expiry-day iron fly** (trading DTE 0, i.e. every Tuesday). At 09:20 sell ATM CE+PE with a 60% SL each and buy OTM12 wings; trail SL to break-even on the SL legs; overall SL ₹2,000; exit 15:15.

| 1 lot (₹2L) | Net | Max DD | PF |
|---|---|---|---|
| Honest walk-forward OOS (7 blind quarters) | ₹41.9k (≈ ₹24k/yr, ~12%) | ₹15.4k | 1.44 |
| Full sample, parameters fitted on everything (upper bound) | ₹93.4k (21%/yr) | ₹12.4k | 1.81 |

Intraday selling on DTE 1–4 lost money out of sample and is not deployed. ₹3L also runs 1 lot, because the 2% expiry-day ELM makes one lot need ≈ ₹1.7L. The edge is shrinking (2024 > 2025 > 2026-Q1) and is not statistically proven (Deflated Sharpe 0.07 at 1,000 trials). Paper-trade first. This is research, not advice.

v1 (first report) claimed P1 = S1+S3 with holdout Calmar 11.6. Re-tested with realistic slippage and intra-minute wicks it falls to 0.7, so v1 is superseded (see `WINNING_STRATEGIES.md` §rejected).

## Reproduce

```bash
pip install kagglehub polars pyarrow
export KAGGLE_API_TOKEN=...   # your own token; never commit it
python -c "import kagglehub;print(kagglehub.dataset_download('pariminikhil/nifty-option-chain-3-oct-24-to-24-mar-26'))"
python -c "import kagglehub;print(kagglehub.dataset_download('senthilkumarvaithi/historical-nifty-options-2024-all-expiries'))"
python etl/etl_pariminikhil.py <path>/final_merged_output.csv data/parquet
python etl/etl_senthil2024.py <path-to-version-dir> data/parquet
cargo build --release --manifest-path opt_engine/Cargo.toml
./opt_engine/target/release/opt_engine build-cache --parquet-dir data/parquet/NIFTY_OHLC --parquet-dir data/parquet/NIFTY --out data/cache/nifty.bin
./opt_engine/target/release/opt_engine backtest --cache data/cache/nifty.bin --strategy-config configs/final/P1_2L_all.json --out /tmp/p1.json
python research/discover_loop.py --generations 8 --pop 400 --label v2     # (see EXPERIMENT_LOG for v3/v4 flags)
python etl/crosscheck_wicks.py <npartha dir> data/parquet etl/wick_model.json   # verify 2024 data + calibrate wicks
python etl/inject_wicks.py data/parquet/NIFTY etl/wick_model.json data/parquet/NIFTY_WICK
./opt_engine/target/release/opt_engine build-cache --parquet-dir data/parquet/NIFTY_OHLC --parquet-dir data/parquet/NIFTY_WICK --out data/cache/nifty_wick.bin
python research/discover_v5.py && python research/discover_v6.py && python research/discover_v7.py
python research/finalize_v7.py && python research/report_static.py   # static, JS-free report
```
