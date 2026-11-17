# Gamma Move (short-covering breakout) option buying – backtest report

**Verdict: not profitable as specified.** 320 trades, win rate 29.7 %, net −₹3.94 L on ₹10 L capital (−39 %), profit factor 0.77, avg R −0.12.
Calls lose (−54 %), puts are mildly positive (+15 %) but not statistically significant. No parameter variant in the sweep makes the strategy robustly profitable.

## Data used (Kaggle, account mvignesh2k19)
- `upstox-stock-options-15m-<symbol>` × 43 symbols: expired monthly stock options, 15m OHLC + volume + OI, expiries 2024-10 → 2026-10; each also contains `underlying_daily__<SYM>` (daily spot OHLC) used for support/resistance.
- Not used: index/NIFTY datasets (strategy is stock options), `nifty50-stocks-1min` (Apr–Nov 2026 only), `nse-archives…` (EOD only).
- Gaps: Dec-2024 and Mar-2025 expiries are empty in the datasets; the video's case-study stocks (BIOCON, POWERINDIA, SAMMAANCAP, CGPOWER, FORTIS) are not in the uploaded set, so the video examples could not be replicated directly. Only 43 of ~200 F&O stocks (mostly Nifty-50) are available.
- Bars exist only when the contract traded; I rebuilt a full 15m grid (flat price, volume 0 on missing bars, OI forward-filled, OI=0 treated as missing).

## Rules implemented (`research/gamma/gamma_backtest.py`)
| Item | Implementation (base case) |
|---|---|
| Window | Entry only when calendar DTE to monthly expiry is 1–14 |
| Level (1D) | Resistance = highest high / Support = lowest low of days D-43…D-4 (40-day swing); prior close within 2 % below (or ≤1 % beyond) the level |
| Strike | Within ±2 strike steps of the level, the CE (resistance) / PE (support) strike with max OI at prior close |
| Entry (all on 15m option bar, 09:30–14:45) | OI down ≥3 % vs 3 bars earlier; volume ≥2× prior-20-bar mean and ≥5 lots; close>open and close>previous high. Fill = **next bar open + 1 % slippage** |
| Stop-loss | Lowest low of the last 8 option 15m bars incl. signal bar (skipped if risk >60 % of premium); gaps through SL fill at open |
| Exit | +100 % target (2×) or SL, else time-exit at 15:15 of entry day+1 (hold_days=2); sell side also gets 1 % slippage |
| Costs | ₹20/order brokerage ×2, STT 0.1 % sell premium, NSE 0.0356 %, SEBI, stamp, 18 % GST (≈₹30.6 k total) |
| Sizing | 1 % of ₹10 L risked per trade (entry→SL), premium ≤15 % of capital, ≥1 lot; one open trade per stock |

## Base result
| | Trades | Win % | Avg ret | Median ret | Avg R | PF | Net ₹ | Max DD ₹ |
|---|---|---|---|---|---|---|---|---|
| All | 320 | 29.7 | −3.8 % | −22.2 % | −0.12 | 0.77 | −393,944 | −450,038 |
| Calls (resistance) | 175 | 22.9 | −11.6 % | −24.9 % | −0.37 | 0.46 | −544,833 | −560,940 |
| Puts (support) | 145 | 37.9 | +5.7 % | −19.0 % | +0.17 | 1.21 | +150,888 | −170,303 |

Exit reasons: SL 183 (avg −35 %, −₹16.1 L), TARGET 43 (avg +99 %, +₹9.3 L), TIME 94 (avg +11 %, +₹2.9 L). Only 13 % of trades reach 2×; the video's "2–3×" is the tail, not the typical outcome. Largest winner +154 %.
Statistics: call avg R −0.37 (t = −4.3, 95 % CI −0.53…−0.19); put avg R +0.17 (t = 1.3, CI −0.09…+0.44, includes zero).
Both halves of the sample are negative (Oct-24→Sep-25: −₹1.70 L; Oct-25→Nov-26: −₹2.24 L). Winning months are driven by a few large trades (Jan-26 +₹1.25 L, Nov-25 +₹0.56 L).

## Sensitivity (net ₹ on ₹10 L; base −393,944)
| Variant | Trades | Win % | Net ₹ | PF |
|---|---|---|---|---|
| Slippage 0 % | 320 | 30.6 | −273,519 | 0.84 |
| Slippage 0.5 % | 320 | 30.0 | −316,209 | 0.82 |
| Slippage 2 % | 320 | 29.4 | −485,569 | 0.72 |
| Slippage 3 % | 320 | 28.7 | −638,695 | 0.63 |
| Exit: trail 4-bar swing low | 329 | 36.8 | −295,365 | 0.74 |
| Exit: time only | 320 | 28.7 | −156,912 | 0.91 |
| Target 50 % / 200 % | 322 / 320 | 38.8 / 29.4 | −259,057 / −112,182 | 0.83 / 0.94 |
| Hold 1 / 3 days | 342 / 311 | 33.9 / 28.0 | −535,540 / −416,534 | 0.55 / 0.78 |
| Volume ≥1.5× / ≥3× | 421 / 175 | 31.6 / 33.7 | −85,959 / −82,134 | 0.96 / 0.91 |
| OI drop ≥1 % / 5 % / 10 % | 450 / 233 / 110 | 28.9 / 27.5 / 32.7 | −205,206 / −452,823 / −41,212 | 0.92 / 0.65 / 0.92 |
| SL lookback 4 / 12 bars | 333 / 314 | 29.1 / 30.6 | −305,277 / −298,638 | 0.84 / 0.82 |
| Swing lookback 20 / 60 days | 441 / 254 | 28.3 / 28.7 | −780,943 / −289,425 | 0.70 / 0.79 |

Even with zero slippage the strategy loses after costs; each extra 1 % of slippage costs ≈₹1.2 L. Best variants only get to roughly break-even (OI ≥10 % drop: −₹41 k; 1-lot sizing sometimes slightly positive, e.g. time-exit +₹67 k over 320 trades, i.e. ≈₹200/trade, noise level).

## Caveats
- Stop/target fills assume you can trade at 15m bar prices; stock options are illiquid, many bars are untraded, so real slippage can exceed the modelled 1 %.
- No spot 15m data: "stock is breaking the level" is inferred from the option's own OI-unwind + volume + price-breakout, not from the spot chart.
- The video's discretionary S/R zones are replaced by a mechanical 40-day swing level; a trader's judgement on "A+ setups" is not captured, and the video examples are survivor/cherry-picked cases. Parameters were swept on the same data (no separate out-of-sample), so the negative result is if anything optimistic.
- STT/exchange rates are approximate (0.1 % STT assumed).

Files: `trades_base.csv` (every trade: entry/exit time, strike, entry, SL, exit, reason, lots, ret, R, costs, P&L), `summary.csv` (all variants).
