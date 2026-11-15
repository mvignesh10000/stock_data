# Test plan: SMC + Fibonacci "High-Probability Zone" (HPZ), local validation before any ai_trader integration

Source: IJCSE 2026, "A Mathematical Integration of Smart Money Concepts and Fibonacci Ratios" (Uttreshwar et al.), supplied by the owner as a PDF.

## Context

The paper claims that zones where Fibonacci levels overlap SMC liquidity (order blocks / liquidity pools) predict reversals with 72 % accuracy, against 65 % for SMC alone, 58 % for Fibonacci alone and 54 % for moving averages. The data is NIFTY 50 at 15-minute and daily resolution, 2015–2024. The paper gives no exact rules, no event definition, no base rate and no costs, so the claim cannot be checked as published. This plan turns the idea into exact, causal rules and tests it on Kaggle data. ai_trader is not touched. HybridSwingNet is out of scope (already rejected: its own walk-forward lost 64.3 %).

Outcome: a go/no-go report. Only a "go" result justifies proposing an ai_trader screener change, which would follow ai_trader's own process: a Python reference, then Rust in rust_core, then a parity test.

## Step 0: setup

- Data from Kaggle, OHLCV only: NIFTY 50 index minute data (`debashis74017/nifty-50-minute-data`), Nifty 100 stock data.
- Raw data stays out of git. `data/MANIFEST` records each file's SHA-256.
- Rust crates: csv, serde, chrono, rayon, rand + rand_chacha (seeded), serde_json. No ML or dataframe stack.

## Step 1: data integrity (E0)

- Parse, convert to IST, keep 09:15–15:30 only. Drop duplicates, flag gaps.
- Resample to 15-minute bars that never cross a session boundary, and to daily bars. Check resampled daily bars against source daily OHLC where available.
- Report per symbol: bars, gaps, zero-volume bars, date span.
- Note survivorship bias (Nifty 100 list is today's constituents).
- Verify: unit tests for resampling, session boundaries, timezone conversion.

## Step 2: exact rules (all causal; a value at bar t uses bars ≤ t only)

- Distances in ATR(14) (Wilder) of the timeframe tested.
- Swing pivots: k-bar fractals, k ∈ {2, 3}; usable from bar i+k.
- Market structure: bullish BOS = close > last confirmed swing high while trend up; CHoCH = same break while trend down. Bearish mirrors.
- Displacement: the leg producing a BOS/CHoCH has range ≥ d·ATR, d ∈ {1.0, 1.5}.
- Order block (bullish): last down-close candle before the displacement leg. Zone A = [low, high]; zone B = [low, body top]. Active once the break is confirmed. Invalidated by a close below the zone low or at age N ∈ {50, 100} bars. One touch only (first retest). Bearish mirrors.
- Fair value gap (bullish): high[t−2] < low[t]; gap = [high[t−2], low[t]]. Optional confluence.
- Liquidity pool: ≥ 2 confirmed swing lows (or highs) within 0.1·ATR. Sweep: a bar whose wick goes beyond the pool and whose close comes back inside.
- Fibonacci on the impulse leg (swing low → swing high) that produced the BOS. Retracements 0.382, 0.5, 0.618, 0.705, 0.786. Extensions (targets) 1.272, 1.618.
- Paper's probabilistic zone: P_F(x) = max_i exp(−(x−μ_i)²/(2σ²)), σ = c·ATR, c ∈ {0.25, 0.5}. P_L(x) = 1 inside an active OB or liquidity pool, else 0 (variant: weight by relative volume of the OB candle; stocks only). HPZ score = P_F·P_L. HPZ touch = price touches the zone with score ≥ τ, τ ∈ {0.5, 0.7}. This product is our reading of the paper's max{P(F) ∩ P(L)}.
- Baselines: Fibonacci-only touch (P_F ≥ τ); SMC-only touch (active OB, no Fibonacci condition); MA touch (EMA20/50 while trend is up).
- Verify: synthetic bar fixtures for each detector; lookahead test (truncate at random t; no output for bars ≤ t changes).
- Optional: compare with ai_trader's existing definitions (`intraday_structure.py`, `ft_stock.py stock_ft_smc`, `ft_screener.rs ft_zones`).

## Step 3: E1 event study (is "72 %" real, or the base rate of a 1:1 barrier in a trending sample?)

- Event: first touch of a zone (HPZ / Fib-only / SMC-only / MA) in the expected reversal direction.
- Outcome (triple barrier from the next bar's open): success = +1·ATR before −1·ATR within H bars; H = 16 (15-minute) and 10 (daily). Same-bar double hit = loss. Repeat with +2/−1.
- Controls: (a) random-level touch: same symbols and dates, zone shifted to a random price within ±3 ATR, 1000 seeded draws; (b) unconditional base rate of the same outcome on every bar, same direction.
- Report: hit rate with Wilson 95 % CI, lift over each control, N. Split by timeframe, long/short, index vs stocks, calendar year.

## Step 4: E2 tradable backtest (after costs)

- Entry: touch bar closes back in the expected direction; enter at the next open.
- Stop: beyond the zone edge − 0.1·ATR. Target: 2R or the 1.272 Fibonacci extension (two variants). Time exit H bars. One position per symbol.
- Costs: stocks 41 bps round trip on daily bars (delivery) and ~8 bps intraday (MIS) plus 5 bps slippage. Index as NIFTY futures at ~3 bps plus 2 bps slippage.
- Metrics: expectancy in R, profit factor, win rate, CAGR, max drawdown, daily-equity Sharpe, trade count, exposure.
- Controls: random entry (same trades per symbol and year, same exit rules and costs), 1000 seeded runs, p-value of expectancy. Buy-and-hold benchmark.

## Step 5: E3 walk-forward (decides go/no-go)

- Grid (≤ 96 combinations) over k, d, N, zone variant, c, τ, target, chosen on the trailing 3 years; trade the next calendar year unchanged. Test years 2018–2024 plus 2025+ where the data covers it.
- Selection rule (fixed in advance): best net expectancy with ≥ 30 trades.
- Report every fold. Concatenate OOS equity. Block bootstrap CI (10,000 resamples, seed 42). Deflated Sharpe over the grid size.
- Robustness slices: regime (NIFTY above/below 200-DMA), sector, liquidity tercile, timeframe.

## Go / no-go criteria (fixed before running)

GO (propose a research-only screener variant to ai_trader) only if all hold:

1. E1 HPZ hit rate beats the random-level control with a lower CI bound above the control, and beats both Fibonacci-only and SMC-only.
2. Concatenated E3 OOS expectancy after costs > 0, with lower bootstrap CI bound > 0 and ≥ 200 OOS trades.
3. It beats random entry at p < 0.05 and has a deflated Sharpe > 0.
4. Positive in ≥ 60 % of folds, and no single year accounts for more than half of the PnL.

Anything else is NO-GO. Record the null result; do not tune further against the OOS years.

## Deliverables

- `results/<run_id>/`: config, data manifest hashes, git commit, per-experiment JSON, and `report.md` (tables for E0–E3 and the go/no-go checklist).
- One CLI: `cargo run --release -- run --config configs/hpz.toml`, deterministic from the seed.

## Verification checklist

- `cargo test`: detector fixtures, lookahead truncation test, resampling and session tests, cost math, triple-barrier stop-first test.
- Rerun with the same seed and confirm the results are byte-identical.
- Sanity check on a random-walk synthetic series: every strategy's E1 lift ≈ 0 and E2 expectancy ≈ −costs.
