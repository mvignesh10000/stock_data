# stock_data — NIFTY intraday non-directional option-selling research

| What | Where |
|---|---|
| **Interactive report** (strategies, net P&L, drawdown, month/quarter/year, ₹2L vs ₹3L) | `reports/strategy_report.html` |
| Winning strategies, exact JSON configs, IS vs OOS tables, worst days | `WINNING_STRATEGIES.md` |
| Generation-by-generation discovery log | `EXPERIMENT_LOG.md` (+ `results/discovery/EXPERIMENT_LOG_v1.md`) |
| Rust backtest engine (`opt_engine`) | `opt_engine/` |
| Parquet ETL | `etl/` |
| Discovery loop / final evaluation / report | `research/` |

## Headline (1 lot = ₹2L, all costs + slippage, Jan-2024 → Mar-2026)

| | Tier | Net | ROI/yr | Max DD | Holdout Calmar / PF |
|---|---|---|---|---|---|
| S1 expiry-day (DTE 0) premium-matched strangle | A (all gates) | ₹85.4k | 19.5% | ₹6.1k (2.1%) | 5.05 / 1.92 |
| S3 DTE 4–6 premium-matched strangle | B | ₹53.2k | 12.2% | ₹4.8k | 6.44 / 1.55 |
| **P1 = S1 + S3 (live calendar)** | portfolio | **₹1.39L** | **31.7%** | **₹5.7k (2.6%)** | 11.6 / 1.69 |

Use 2 lots on ₹3L (see report). S2 (DTE 2–3) is not deployable since NIFTY moved to Tuesday expiry. This is research, not advice; paper-trade first.

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
python research/finalize.py && python research/report.py
```
