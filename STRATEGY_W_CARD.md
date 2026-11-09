# Strategy W: NIFTY weekly iron fly (overnight, 3 days to expiry)

The overnight complement to Strategy B. Option sellers earn the volatility premium **overnight**: selling the ATM straddle 2-4
trading days before expiry and holding earns ~5x what intraday selling earns (research round 9). W harvests it with hard wings.
Backtested on 5 years of true exchange 1-minute data (Nov 2021 – Nov 2026) in the validated simulator (`research/sim/`).

## Rules
| Item | Setting |
|---|---|
| Entry day / time | **3 trading days before the weekly expiry, 15:15** (e.g. Wednesday 15:15 for a Tuesday expiry, shifted for holidays) |
| Legs | SELL ATM CE + ATM PE; BUY CE and PE **3 % of spot beyond the short strike** (≈ 750 pts at NIFTY 25,000), wings first |
| Leg stops | none (the wings are the protection) |
| Weekly stop | close everything if the position's MTM since entry reaches **–₹8,000 per lot** (checked every minute while the market is open) |
| Exit | **09:20 on expiry morning** (avoids expiry-day gamma; frees margin as Strategy B enters) |
| Adjustments | none |
| Product | carry-forward (NRML / "D"), limit orders with a price buffer |
| Margin | about ₹1.1L per lot (Upstox fly ±800: ₹1.06L) |
| Maximum loss | bounded by the wings: ≈ (wing distance – credit) × 65 ≈ ₹39k per lot even on an extreme gap |

## How the rules were chosen (and how much to trust them)
* 576 positional configs (entry 2/3/4 days before expiry x 09:20/15:15, fly/strangle, wings ₹20 / 1.5 % / 3 %, leg SL, weekly stop
  ₹4k/8k, recenter or not, exit expiry 09:20/15:15). **The pre-declared single pick failed** out of sample (PF 0.77 in 2021-23).
* What is robust is the **structure**: of the 80 configs profitable in all three blocks, 69 are flies and 52 use 3 % wings. Across
  all 24 variants of "fly + 3 % wings + 15:15 entry + no leg SL" (none picked): median PF 1.27 / 1.15 / 1.10 in 2021-23 / 2024-26 /
  2026, profitable in 92 % / 96 % / 79 % of them. The structure was recognised after seeing all blocks, so treat it as strong
  evidence, not a clean holdout.
* The remaining choices were fixed by reasoning, not results: middle entry day (3), looser weekly stop (₹8k), no adjustments,
  early exit (09:20).

## Backtest (1 lot, today's costs: STT 0.15 % on option sells, slippage 0.5 %/fill)
| | Value |
|---|---|
| Net, Nov 2021 – Nov 2026 | ₹1,43,771 (₹28.9k / year) |
| Profit factor | 1.17 (2021-23 1.23 · 2024-26 1.09 · 2026 1.35) |
| Winning months | 56 %, longest losing run 7 months |
| Max drawdown | ₹64.2k · bootstrap 95th percentile ₹1.35L |
| Worst day / worst month | –₹17.0k (2-Mar-2026 gap) / –₹31.7k |
| By year | 2022 +54.9k · 2023 +4.5k · 2024 +28.7k · 2025 +54.1k · 2026 +0.9k (Jan-Mar –₹48k, Apr-Nov +₹49k) |
| Slippage x2 | PF 1.12, ₹21.0k / year |

**On its own W is a weak strategy** (PF 1.17, long losing runs). Its value is in the portfolio: daily correlation with Strategy B is
–0.01, so it adds return without adding B's risk on the same days.

## Recommended portfolio on ₹5L
| Portfolio | Per year | Max DD | Bad-case DD (95 %) | Winning months | Worst month |
|---|---|---|---|---|---|
| B 2 lots | ₹49.6k (9.9 %) | ₹49.5k (9.9 %) | ₹81.6k | 64 % | –₹24.3k |
| **B 2 lots + W 1 lot** | **₹78.5k (15.7 %)** | **₹61.9k (12.4 %)** | ₹1.33L | 64 % | –₹56.0k |
| B 2 lots + W 2 lots | ₹1.07L (21.5 %) | ₹1.11L (22.3 %) | ₹2.25L | 61 % | –₹87.7k (too much risk for ₹5L) |
Margin never stacks: W holds ~₹1.1L from Wednesday 15:15 to Tuesday 09:20; B uses ~₹3.4L on Tuesday from 09:20.

## Risks specific to W (read this)
1. **Overnight gaps.** The worst days are gap opens (2-Mar-2026 –₹17k, 9-Mar-2026 –₹14.8k, 24-Feb-2022 –₹13.6k). Stops cannot act
   before the open; the wings cap the damage at ~₹39k per lot.
2. **Long losing runs** (7 months) and a flat 2023. Size for the bootstrap drawdown, not the average.
3. **Weekend/holiday risk** sits inside every week (Wed → Tue holds include a weekend).
4. Rule changes (expiry weekday, lot size, margin, settlement) change the trade.

## Going live
1. Paper trade 8 weeks with `execution/upstox_weekly.py` (paper by default) alongside Strategy B's paper run.
2. Then 1 lot live. Kill-switch: drawdown from peak above ₹1.0L per lot, or 6 losing months in a row.
