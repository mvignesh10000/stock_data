# Round 13 (2026-11-10)
Setup: restore data as in the handoff (section 12); Breeze 2024 ETL output must sit at `data/parquet/NIFTY_OHLC/year=2024/`.
Index CSVs (debashis74017/nifty-50-minute-data) go to any folder: `python3 research/r13/idx.py <folder>`.
2017-2020: place `canonical_NIFTY_monthly_YYYY.parquet` as `data/parquet/NIFTY_ZEN/year=YYYY/data.parquet`, then `python3 research/r13/zen.py`.
| Script | What |
|---|---|
| s1_decomp.py | per-leg premium by segment / moneyness / tdte |
| idx.py | 11-year index table |
| s2_overnight.py, s4_on_grid.py, s3_basis.py | first overnight tests, synthetic-future basis |
| on2.py | Strategy M family (class ON2) |
| on2_zen.py | M on 2017-2020 monthly options |
| m_robust.py | robustness grid |
| margins.py | live Upstox margins |
| portfolio.py | `build` then report: B, W, M daily series and portfolios |
