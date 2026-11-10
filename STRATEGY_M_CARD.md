# Strategy M: NIFTY overnight momentum premium (non-expiry sleeve, all weekdays)

Found in round 13 (research/r13/). M trades the one effect in this project that shows up in **every year from 2017 to 2026** on
two independent option datasets and in 11 of 12 years of index data: **the direction of the day continues overnight**.
After an up day the market tends to open firm; after a down day it tends to open weak. M sells the option that this
makes worthless faster, holds it only from 15:20 to 09:20, and so also collects one night of time decay.

## Rules
| Item | Setting |
|---|---|
| Signal (15:19) | r = NIFTY spot at 15:19 close / spot at 09:20 − 1 |
| Up day, r > +0.3 % | **SELL ATM PE** (nearest weekly expiry that is not today) at 15:20 |
| Down day, r < −0.3 % | **SELL ATM CE** at 15:20 |
| Otherwise | no trade (about 4 of 10 days) |
| Protection (live) | BUY the same-type option **4 % of spot beyond the short strike** first (≈ 1,000 pts; costs ≈ ₹2-5 of premium) |
| Exit | **09:20 next trading day**, everything (short leg first). Never held into the day session |
| Stops | none overnight (they cannot act); the wing is the stop |
| Expiry choice | on expiry day use next week's contract; the night before expiry use the expiring contract (exit 09:20) |
| Product / orders | carry-forward (NRML / "D"), limit orders with a buffer |
| Margin (Upstox, 10-Nov-2026) | naked ₹1.68L · with 4 % wing **₹0.84L** · with 3 % wing ₹0.69L per lot |
| Trades | ~100 nights a year per lot (≈ 50 up, 50 down) |

## Backtest, 1 lot (65), naked short leg, today's costs (STT 0.15 %, slippage 0.5 %/fill, brokerage ₹20/order)
| | Value |
|---|---|
| Period | 2021-11-15 – 2026-11-06, true exchange 1-min option prices |
| Net | **₹72.3k / year**, profit factor 1.42, daily Sharpe 1.58 |
| Winning months | **69 %**, worst month −₹31.0k |
| Max drawdown | ₹35.0k · bootstrap 95th percentile ₹87k |
| Worst night | −₹24.1k |
| By year | 2021 (6 wk) +9.0k · 2022 +105.7k · 2023 +38.2k · 2024 +54.6k · 2025 +75.0k · 2026 +85.0k |
| Blocks (PF / ₹ per yr) | 2021-23 1.42 / 70.6k · 2024-26Q1 1.53 / 81.5k · 2026 holdout 1.19 / 41.7k |
| Up leg only / down leg only | ₹39.6k/yr PF 1.49 · ₹32.7k/yr PF 1.33 (both positive every year) |
| With the 4 % wing (clean data, 2024-26 only) | PF 1.37, ₹58k/yr (vs ₹81k naked in the same period): the wing costs ≈ ₹250-300 per trade |

## Why believe it (and how much)
1. **11 years of index data (2015-2026, 2,912 nights).** Holding from 15:20 to next 09:20 after an up day (> 0.3 %) earned
   +8 bp a night net of futures carry and costs, t = 3.5, positive in 11 of 12 years. The edge grows with the size of the
   day's move (monotonic), which is what a real effect looks like.
2. **Unseen option data, 2017-2020 (monthly options, Zenodo):** the same rules, unchanged, made money in all four years
   (+3.5k, +2.2k, +21.3k, +32.7k per lot), but only PF 1.13. Index levels were 2.3x lower and monthly options cost more to
   trade, so this era understates today's edge; still, plan for **roughly half the 2021-26 result** in a weak regime.
3. **No cliff next to the parameters** (5-year PF): threshold 0 / 0.2 / 0.4 / 0.5 % -> 1.26 / 1.36 / 1.40 / 1.42; entry 15:10 /
   15:25 -> 1.31 / 1.34; exit 09:17 / 09:25 / 09:45 -> 1.48 / 1.36 / 1.27; slippage x2 -> 1.34. All 15 variants are profitable
   in 2021-23 and 2024-26; one (entry 15:10) is slightly negative in the 2026 holdout.
4. **Uncorrelated with B and W** (daily correlation −0.01 and −0.10).

What is *not* proven: the threshold and the short-option structure were chosen after seeing 2021-26, so that period is not a
clean holdout for M. The clean evidence is point 1 (signal) and point 2 (options, 2017-20).

## Risks (read this)
1. **Overnight gaps against the signal.** Since 2015 the worst were 20-Mar-2020 (7.3 %), 23-Mar-2020 (5.1 %), 13-Mar-2020
   (4.6 %), 8-Nov-2016 demonetisation night (3.9 %). Naked, those cost ₹60k-₹1.14L per lot at today's index level. With the
   4 % wing the loss is capped near ₹60k per lot; 0.9 % of nights moved more than 2 % against the signal.
   **Trade it with the wing.** Wing prices before 2024 could not be tested (old data holds only ATM ± 500 points).
2. **The down leg is younger evidence.** Short futures after down days lost money in 2015-2021; the short-call version
   worked from 2018. If you want only the oldest effect, trade the up leg alone (₹39.6k/yr, PF 1.49, DD ₹25.8k).
3. **Regime dependence.** 2017-18 were barely positive. Expect flat years.
4. **Execution at the edges of the day.** Signal at 15:19, orders at 15:20; exit orders at 09:20 when spreads are wider than
   at midday. Doubling slippage still leaves PF 1.34, but a missed exit converts the trade into an unplanned day position.
5. Rule changes (expiry weekday, lot size, STT, margin) change the trade.

## Portfolio on ₹5L (1-lot series added day by day, 2021-11 – 2026-11)
| Portfolio | Per year | Max DD | Bad-case DD (95 %) | Winning months | Worst month | Losing years |
|---|---|---|---|---|---|---|
| B 2 lots + W 1 lot (previous) | ₹76.8k (15.4 %) | ₹61.9k (12.4 %) | ₹1.33L | 64 % | −₹56.0k | 1 |
| M 1 lot | ₹72.3k (14.5 %) | ₹35.0k (7.0 %) | ₹87k | 69 % | −₹31.0k | 0 |
| B 2 + M 1 | ₹120.8k (24.2 %) | ₹46.5k (9.3 %) | ₹89k | 69 % | −₹37.2k | 0 |
| **B 2 + W 1 + M 1** | **₹149.0k (29.8 %)** | **₹45.7k (9.1 %)** | ₹90k | **75 %** | −₹26.0k | 0 |
| B 2 + W 1 + M 2 | ₹221.3k (44.3 %) | ₹74.2k (14.8 %) | ₹1.52L | 74 % | −₹55.2k | 0 |
M figures are for the naked leg; with the wing take about a quarter off M's line (≈ ₹130k/yr for B2+W1+M1).
Margin never exceeds the capital: nights W ₹1.1L + M ₹0.84L (winged); expiry day B ₹3.3L after W and M have exited at 09:20.
Idle margin can sit in pledged liquid funds / G-secs (about 6-7 %/yr extra on the pledged part; keep ~50 % cash for overnight positions).

## Going live
1. Paper trade M for 6-8 weeks next to B and W; log signal, fills, and slippage vs the 15:20 / 09:20 closes.
2. Then 1 lot with the wing. Kill-switch: drawdown from peak above ₹90k per lot, or a negative rolling 12 months.
3. On expiry morning the order is: exit W and M at 09:20, then enter B.
