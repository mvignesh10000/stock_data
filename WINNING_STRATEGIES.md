# WINNING_STRATEGIES — NIFTY intraday non-directional option selling

Generated 2026-11-07 by `research/finalize.py` + `research/report.py`. Interactive version: `reports/strategy_report.html`.

## Data, splits and assumptions

- Data: Kaggle `senthilkumarvaithi/historical-nifty-options-2024-all-expiries` (2024, true 1-min OHLC) + `pariminikhil/nifty-option-chain-3-oct-24-to-24-mar-26` (Jan-2025 → Mar-2026, 1-min LTP; bar high/low = envelope of consecutive LTPs). Nearest weekly expiry only, strikes within ±1500 pts of the 09:15 spot. 551 trading days.
- Chronological splits: **train** 20240101–20250616 (65%), **validation** 20250617–20251124 (20%), **holdout** 20251125–20260324 (15%).
- Costs on every order: ₹20 brokerage, STT 0.1% (sell), NSE txn 0.03503%, SEBI ₹10/cr, stamp 0.003% (buy), GST 18%. Slippage 0.3% per market fill (min ₹0.05), plus 0.5% on stop fills; stops fill at max(trigger, bar open).
- Lot size normalised to **65** for all years. **₹2L capital = 1 lot**, **₹3L capital = 2 lots** (≈₹1.5L margin per hedged lot). Every structure buys far-OTM wings so margin stays inside that budget. Brokerage is flat per order, so 2 lots cost proportionally less.
- Hard gate (all per 1 lot on ₹2L): expectancy ≥ ₹450/trade-day, worst day ≤ 2.5× p90 winning day and ≤ 1.5% of capital (₹3,000), ≤ 15% losing months, max underwater ≤ 25 active trading days. Stability ratio ≥ 0.75 (entry ±1/±2 min, SL ±2.5/±5 pts). Out-of-sample: Calmar ≥ 3.5 and PF ≥ 1.45 on validation **and** holdout.

## Verdict

- **Tier A (passed every gate): S1, the expiry-day (DTE 0) premium-matched strangle.**
- **Tier B (stable, passed validation, missed one train gate by a small margin under a rule fixed before they saw the holdout): S2 (DTE 2–3) and S3 (DTE 4–6).** S3 then also passed the holdout bar (Calmar 6.44, PF 1.55). S2 has only 2 holdout days, because NIFTY weekly expiry moved from Thursday to Tuesday in Sep-2025 and DTE-2/3 sessions have almost disappeared since. **S2 is not deployable on the current calendar.**
- Baselines (plain straddles) show what the defence mechanics are worth: the plain every-day hedged straddle nets only ₹15k over 2.2 years with a ₹58k drawdown.
- Recommended live set for **₹2L: P1 = S1 + S3** (they trade on different days, so only one hedged lot is ever open). For **₹3L, run the same set with 2 lots.**

## S1 — Expiry-day (DTE 0)  (tier: A)

Source candidate `v2:g7_276`, stability ratio **0.79**.

**Rules — `S1_strangle_premium_dte0`**
1. Trade only on days with DTE 0 (calendar days to the nearest weekly expiry).
2. At 09:23: sell the OTM CE and OTM PE whose premium is closest to ₹71 each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹71).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 20.2% above each leg's sell price (SL-M).
5. When one leg is stopped, move the other leg's SL to its sell price +7.4% (move-SL-to-cost).
6. Portfolio max loss: exit everything at −18 premium points (≈ ₹1,170 per lot, before costs).
7. Profit lock: once MTM ≥ +29 pts, lock 64% of it, then raise the lock by 5 pts for every further 10 pts.
8. Time exit: square off everything at 15:02.

```json
{
 "name": "S1_strangle_premium_dte0",
 "structure": "strangle_premium",
 "target_premium": 71,
 "otm_steps": 3,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  0
 ],
 "entry_minutes": [
  8
 ],
 "lots": 1,
 "or_filter_pct": 0.0,
 "sl_mode": "leg",
 "sl_pct": 20.2,
 "combined_sl_pct": 13.4,
 "move_sl_to_cost": true,
 "cost_offset": 0.074,
 "max_reentries": 0,
 "reentry_cutoff": 300,
 "wt_drop_pct": 0,
 "wt_window": 60,
 "max_loss_pts": 18,
 "target_pts": 0,
 "lock_trigger_pts": 29,
 "lock_pct": 0.64,
 "trail_step_pts": 10,
 "trail_by_pts": 5,
 "exit_minute": 347,
 "roll_ratio": 0.0,
 "max_rolls": 2,
 "roll_cutoff": 270
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 76 | ₹66,356 | 23.4% | ₹4,658 (2.1%) | 10.03 | 61.8% | 2.79 | 3 | ₹873 | ₹-1,556 | 11% |
| Validation ₹2L | 23 | ₹8,941 | 10.2% | ₹3,431 (1.6%) | 5.97 | 65.2% | 1.80 | 2 | ₹389 | ₹-1,603 | 17% |
| Holdout ₹2L | 18 | ₹10,088 | 15.3% | ₹6,068 (2.8%) | 5.05 | 55.6% | 1.92 | 4 | ₹560 | ₹-1,549 | 40% |
| Full period ₹2L / 1 lot | 117 | ₹85,385 | 19.5% | ₹6,068 (2.1%) | 6.44 | 61.5% | 2.45 | 4 | ₹730 | ₹-1,603 | 15% |
| Full period ₹3L / 2 lots | 117 | ₹192,860 | 29.4% | ₹11,381 (2.3%) | 7.75 | 61.5% | 2.76 | 4 | ₹1,648 | ₹-3,017 | 15% |
| Full ₹2L, zero brokerage | 117 | ₹107,475 | 24.6% | ₹5,313 (1.7%) | 9.25 | 61.5% | 3.13 | 4 | ₹919 | ₹-1,414 | 11% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 2,798 | 2,122 | 4,233 | -561 | 9,764 | -3,188 | 2,508 | 1,806 | 435 | 7,887 | 7,014 | 1,198 | **36,016** |
| 2025 | 8,434 | 326 | 1,909 | 10,152 | 9,368 | 1,065 | 874 | 1,449 | 5,274 | 1,080 | -1,997 | 3,176 | **41,109** |
| 2026 | 5,386 | 8,942 | -6,068 |  |  |  |  |  |  |  |  |  | **8,261** |

**Quarterly (₹):** 2024-Q1: 9,153, 2024-Q2: 6,015, 2024-Q3: 4,749, 2024-Q4: 16,099, 2025-Q1: 10,668, 2025-Q2: 20,585, 2025-Q3: 7,597, 2025-Q4: 2,259, 2026-Q1: 8,261

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20251028 | 0 | -1,603 | 2 | MAXLOSS @ 09:53 | T0HCE B 26450CE 09:23@2.1→09:53@1.6 (MAXLOSS)<br>T0HPE B 25350PE 09:23@2.0→09:53@1.4 (MAXLOSS)<br>T0CE S 26000CE 09:23@74.4→09:33@89.9 (SL)<br>T0PE S 26000PE 09:23@60.1→09:53@64.9 (SL) |
| 20250626 | 0 | -1,589 | 2 | MAXLOSS @ 10:41 | T0HCE B 25750CE 09:23@2.3→10:41@1.4 (MAXLOSS)<br>T0HPE B 24600PE 09:23@2.0→10:41@0.9 (MAXLOSS)<br>T0CE S 25350CE 09:23@68.0→09:30@82.2 (SL)<br>T0PE S 25350PE 09:23@64.1→10:41@69.2 (SL) |
| 20240627 | 0 | -1,556 | 2 | MAXLOSS @ 09:38 | T0HCE B 24250CE 09:23@1.9→09:38@1.7 (MAXLOSS)<br>T0HPE B 23400PE 09:23@2.0→09:38@2.0 (MAXLOSS)<br>T0CE S 23850CE 09:23@69.3→09:38@74.9 (SL)<br>T0PE S 23850PE 09:23@71.9→09:26@86.9 (SL) |
| 20260310 | 0 | -1,549 | 2 | MAXLOSS @ 10:15 | T0HCE B 24750CE 09:23@2.1→10:15@1.4 (MAXLOSS)<br>T0HPE B 23400PE 09:23@2.1→10:15@1.4 (MAXLOSS)<br>T0CE S 24200CE 09:23@70.1→10:15@75.7 (SL)<br>T0PE S 24100PE 09:23@65.2→09:36@78.8 (SL) |
| 20260324 | 0 | -1,545 | 2 | MAXLOSS @ 09:42 | T0HCE B 23400CE 09:23@2.1→09:42@1.4 (MAXLOSS)<br>T0HPE B 22050PE 09:23@1.8→09:42@1.5 (MAXLOSS)<br>T0CE S 22900CE 09:23@65.3→09:26@78.9 (SL)<br>T0PE S 22700PE 09:23@73.3→09:42@79.1 (SL) |

## S2 — Mid-week (DTE 2-3)  (tier: B)

Source candidate `v3:g6_124`, stability ratio **0.90**.

**Rules — `S2_strangle_offset_dte23`**
1. Trade only on days with DTE 2, 3 (calendar days to the nearest weekly expiry).
2. At 10:08: sell CE at ATM+3 strikes and PE at ATM−3 strikes (150 pts each side).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 24.6% above each leg's sell price (SL-M).
5. Re-entry: if a stopped leg trades back to its original sell price before 14:15, re-sell it (max 2×).
6. Wait & trade: sell each leg only after it decays 5% from its reference price (within 60 min).
7. Skip the day if the first 15-min spot range exceeds 0.4% of spot.
8. Time exit: square off everything at 14:33.

```json
{
 "name": "S2_strangle_offset_dte23",
 "structure": "strangle_offset",
 "target_premium": 130,
 "otm_steps": 3,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  2,
  3
 ],
 "entry_minutes": [
  53
 ],
 "lots": 1,
 "or_filter_pct": 0.4,
 "sl_mode": "leg",
 "sl_pct": 24.6,
 "combined_sl_pct": 16.4,
 "move_sl_to_cost": false,
 "cost_offset": -0.1,
 "max_reentries": 2,
 "reentry_cutoff": 300,
 "wt_drop_pct": 5,
 "wt_window": 60,
 "max_loss_pts": 0,
 "target_pts": 0,
 "lock_trigger_pts": 0,
 "lock_pct": 0.31,
 "trail_step_pts": 0,
 "trail_by_pts": 5,
 "exit_minute": 318,
 "roll_ratio": 0.0,
 "max_rolls": 1,
 "roll_cutoff": 270
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 111 | ₹37,387 | 13.2% | ₹4,527 (2.2%) | 5.81 | 61.3% | 2.12 | 6 | ₹337 | ₹-2,395 | 17% |
| Validation ₹2L | 21 | ₹9,683 | 11.1% | ₹1,401 (0.7%) | 15.83 | 71.4% | 3.37 | 3 | ₹461 | ₹-1,401 | 25% |
| Holdout ₹2L | 2 | ₹-3,316 | -5.0% | ₹3,316 (1.7%) | -3.04 | 0.0% | -0.00 | 2 | ₹-1,658 | ₹-2,438 | 100% |
| Full period ₹2L / 1 lot | 134 | ₹43,754 | 10.0% | ₹4,527 (2.2%) | 4.42 | 61.9% | 2.08 | 6 | ₹327 | ₹-2,438 | 18% |
| Full period ₹3L / 2 lots | 134 | ₹112,052 | 17.1% | ₹7,867 (1.9%) | 6.51 | 64.9% | 2.58 | 6 | ₹836 | ₹-4,735 | 18% |
| Full ₹2L, zero brokerage | 134 | ₹68,298 | 15.6% | ₹3,627 (1.3%) | 8.61 | 68.7% | 3.22 | 3 | ₹510 | ₹-2,297 | 18% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 1,204 | 3,183 | -2,096 | 1,363 | 1,410 | 4,296 | -2,068 | 1,570 | 2,391 | 7,104 | 13 | 3,377 | **21,746** |
| 2025 | 10,309 | 1,863 | 1,303 | 1,687 | 734 | 1,132 | 1,634 | 7,588 | 0 | -924 | 0 | 0 | **25,324** |
| 2026 | 0 | -3,316 | 0 |  |  |  |  |  |  |  |  |  | **-3,316** |

**Quarterly (₹):** 2024-Q1: 2,291, 2024-Q2: 7,068, 2024-Q3: 1,894, 2024-Q4: 10,494, 2025-Q1: 13,474, 2025-Q2: 3,552, 2025-Q3: 9,222, 2025-Q4: -924, 2026-Q1: -3,316

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20260201 | 2 | -2,438 | 1 | FLAT @ 14:15 | T0HCE B 26750CE 10:08@5.1→14:15@1.8 (FLAT)<br>T0HPE B 23800PE 10:08@5.5→14:15@6.4 (FLAT)<br>T0PE S 25200PE 10:15@128.7→12:12@161.2 (SL) |
| 20240319 | 2 | -2,395 | 3 | TIME @ 14:33 | T0HCE B 22700CE 10:08@2.0→14:33@1.7 (TIME)<br>T0HPE B 21000PE 10:08@2.0→14:33@1.1 (TIME)<br>T0PE S 21750PE 10:09@67.1→10:30@84.1 (SL)<br>T0CE S 22050CE 10:29@54.6→14:33@35.2 (TIME)<br>T0PE S 21750PE 10:34@65.5→11:40@82.1 (SL)<br>T0PE S 21750PE 12:26@65.5→14:16@82.1 (SL) |
| 20250602 | 3 | -2,240 | 1 | FLAT @ 14:15 | T0HCE B 26050CE 10:08@2.1→14:15@2.1 (FLAT)<br>T0HPE B 23150PE 10:08@2.0→14:15@1.5 (FLAT)<br>T0CE S 24750CE 10:15@124.4→10:38@155.9 (SL) |
| 20240708 | 3 | -2,108 | 2 | TIME @ 14:33 | T0HCE B 24950CE 10:08@2.1→14:33@1.6 (TIME)<br>T0HPE B 23450PE 10:08@2.0→14:33@1.8 (TIME)<br>T0CE S 24450CE 10:09@47.7→10:28@59.8 (SL)<br>T0PE S 24150PE 10:23@46.9→11:11@58.7 (SL)<br>T0CE S 24450CE 10:34@44.3→14:33@48.5 (TIME)<br>T0PE S 24150PE 13:18@46.5→14:33@45.2 (TIME) |
| 20240729 | 3 | -2,019 | 2 | TIME @ 14:33 | T0HCE B 25800CE 10:08@2.0→14:33@1.3 (TIME)<br>T0HPE B 23500PE 10:08@2.1→14:33@1.5 (TIME)<br>T0CE S 25050CE 10:13@54.3→10:56@68.1 (SL)<br>T0PE S 24750PE 10:54@55.7→12:18@69.8 (SL)<br>T0CE S 25050CE 12:18@52.7→14:33@50.6 (TIME) |

## S3 — Far-week (DTE 4-6)  (tier: B)

Source candidate `v4:g4_211`, stability ratio **0.85**.

**Rules — `S3_strangle_premium_dte4567`**
1. Trade only on days with DTE 4, 5, 6, 7 (calendar days to the nearest weekly expiry).
2. At 09:38: sell the OTM CE and OTM PE whose premium is closest to ₹60 each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹60).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 16.9% above each leg's sell price (SL-M).
5. Re-entry: if a stopped leg trades back to its original sell price before 14:15, re-sell it (max 1×).
6. Skip the day if the first 15-min spot range exceeds 0.65% of spot.
7. Portfolio max loss: exit everything at −32 premium points (≈ ₹2,080 per lot, before costs).
8. Time exit: square off everything at 14:22.

```json
{
 "name": "S3_strangle_premium_dte4567",
 "structure": "strangle_premium",
 "target_premium": 60,
 "otm_steps": 1,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  4,
  5,
  6,
  7
 ],
 "entry_minutes": [
  23
 ],
 "lots": 1,
 "or_filter_pct": 0.65,
 "sl_mode": "leg",
 "sl_pct": 16.9,
 "combined_sl_pct": 11.7,
 "move_sl_to_cost": false,
 "cost_offset": 0.072,
 "max_reentries": 1,
 "reentry_cutoff": 300,
 "wt_drop_pct": 0,
 "wt_window": 60,
 "max_loss_pts": 32,
 "target_pts": 0,
 "lock_trigger_pts": 0,
 "lock_pct": 0.52,
 "trail_step_pts": 5,
 "trail_by_pts": 5,
 "exit_minute": 307,
 "roll_ratio": 0.0,
 "max_rolls": 1,
 "roll_cutoff": 270
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 65 | ₹30,147 | 10.6% | ₹4,760 (2.2%) | 4.46 | 66.2% | 2.70 | 4 | ₹464 | ₹-2,527 | 22% |
| Validation ₹2L | 42 | ₹13,772 | 15.8% | ₹1,307 (0.6%) | 24.13 | 73.8% | 2.91 | 2 | ₹328 | ₹-1,307 | 17% |
| Holdout ₹2L | 47 | ₹9,300 | 14.1% | ₹4,382 (2.1%) | 6.44 | 59.6% | 1.55 | 3 | ₹198 | ₹-2,414 | 20% |
| Full period ₹2L / 1 lot | 154 | ₹53,219 | 12.2% | ₹4,760 (2.2%) | 5.11 | 66.2% | 2.27 | 4 | ₹346 | ₹-2,527 | 22% |
| Full period ₹3L / 2 lots | 154 | ₹140,139 | 21.4% | ₹8,953 (2.6%) | 7.16 | 68.8% | 2.96 | 4 | ₹910 | ₹-4,771 | 22% |
| Full ₹2L, zero brokerage | 154 | ₹86,920 | 19.9% | ₹4,240 (1.8%) | 9.37 | 74.0% | 3.86 | 3 | ₹564 | ₹-2,244 | 19% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 717 | -1,710 | 2,755 | 1,903 | 2,298 | 278 | 1,314 | 788 | 2,547 | 2,836 | -856 | 4,874 | **17,745** |
| 2025 | -627 | 8,097 | 1,568 | 2,875 | -1,035 | 2,600 | 2,255 | -1,059 | 1,994 | 9,341 | 1,588 | 8,163 | **35,760** |
| 2026 | -3,389 | 1,600 | 1,503 |  |  |  |  |  |  |  |  |  | **-286** |

**Quarterly (₹):** 2024-Q1: 1,762, 2024-Q2: 4,479, 2024-Q3: 4,650, 2024-Q4: 6,854, 2025-Q1: 9,039, 2025-Q2: 4,439, 2025-Q3: 3,190, 2025-Q4: 19,093, 2026-Q1: -286

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20250523 | 6 | -2,527 | 3 | MAXLOSS @ 12:12 | T0HCE B 26150CE 09:38@2.5→12:12@2.5 (MAXLOSS)<br>T0HPE B 23200PE 09:38@4.7→12:12@4.4 (MAXLOSS)<br>T0CE S 25200CE 09:38@57.7→10:03@67.9 (SL)<br>T0PE S 24350PE 09:38@56.1→11:49@66.0 (SL)<br>T0CE S 25200CE 10:34@55.0→10:37@64.7 (SL)<br>T0PE S 24350PE 12:07@55.6→12:12@59.6 (MAXLOSS) |
| 20260107 | 6 | -2,414 | 3 | MAXLOSS @ 11:23 | T0HCE B 27000CE 09:38@1.9→11:23@1.7 (MAXLOSS)<br>T0HPE B 24750PE 09:38@2.0→11:23@1.8 (MAXLOSS)<br>T0CE S 26250CE 09:38@66.8→10:12@78.5 (SL)<br>T0PE S 26050PE 09:38@60.3→09:46@70.9 (SL)<br>T0PE S 26050PE 09:59@57.2→11:23@55.1 (MAXLOSS)<br>T0CE S 26250CE 10:29@66.5→10:56@78.2 (SL) |
| 20250110 | 6 | -2,363 | 3 | MAXLOSS @ 11:04 | T0HCE B 24650CE 09:38@2.1→11:04@1.9 (MAXLOSS)<br>T0HPE B 22100PE 09:38@4.2→11:04@4.0 (MAXLOSS)<br>T0CE S 23800CE 09:38@61.1→11:04@71.8 (SL)<br>T0PE S 23050PE 09:38@62.4→09:59@73.3 (SL)<br>T0PE S 23050PE 10:22@58.2→10:32@68.5 (SL) |
| 20250117 | 6 | -2,349 | 3 | MAXLOSS @ 12:00 | T0HCE B 24500CE 09:38@2.0→12:00@1.9 (MAXLOSS)<br>T0HPE B 21750PE 09:38@3.0→12:00@3.4 (MAXLOSS)<br>T0CE S 23500CE 09:38@62.3→10:26@73.2 (SL)<br>T0PE S 22900PE 09:38@62.3→10:49@73.2 (SL)<br>T0CE S 23500CE 10:44@60.5→12:00@71.1 (SL) |
| 20260121 | 6 | -2,246 | 3 | FLAT @ 14:15 | T0HCE B 26650CE 09:38@2.9→14:15@1.9 (FLAT)<br>T0HPE B 23700PE 09:38@7.8→14:15@7.4 (FLAT)<br>T0CE S 25500CE 09:38@55.0→12:37@64.7 (SL)<br>T0PE S 24950PE 09:38@57.3→10:00@67.4 (SL)<br>T0CE S 25500CE 13:34@53.9→13:38@63.4 (SL) |

## B1 — Plain hedged ATM straddle, every day  (tier: baseline)

**Rules — `B1_plain_straddle_all`**
1. Trade only on days with DTE any (calendar days to the nearest weekly expiry).
2. At 09:25: sell the ATM CE + ATM PE (ATM = strike near spot with the smallest |CE−PE|, i.e. synthetic-future ATM).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹3, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 30% above each leg's sell price (SL-M).
5. Time exit: square off everything at 15:15.

```json
{
 "name": "B1_plain_straddle_all",
 "structure": "straddle",
 "entry_minutes": [
  10
 ],
 "sl_pct": 30,
 "hedge_premium": 3,
 "exit_minute": 360
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 358 | ₹37,941 | 13.4% | ₹58,003 (22.9%) | 0.46 | 60.1% | 1.08 | 5 | ₹106 | ₹-12,934 | 39% |
| Validation ₹2L | 109 | ₹-7,161 | -8.2% | ₹34,192 (16.6%) | -0.48 | 63.3% | 0.93 | 5 | ₹-66 | ₹-6,304 | 67% |
| Holdout ₹2L | 83 | ₹-15,560 | -23.6% | ₹28,973 (14.1%) | -1.63 | 56.6% | 0.87 | 5 | ₹-187 | ₹-8,345 | 60% |
| Full period ₹2L / 1 lot | 550 | ₹15,220 | 3.5% | ₹58,003 (22.9%) | 0.12 | 60.2% | 1.02 | 5 | ₹28 | ₹-12,934 | 44% |
| Full period ₹3L / 2 lots | 550 | ₹134,281 | 20.5% | ₹93,539 (21.7%) | 0.66 | 61.3% | 1.10 | 5 | ₹244 | ₹-25,680 | 44% |
| Full ₹2L, zero brokerage | 550 | ₹119,060 | 27.2% | ₹36,761 (13.1%) | 1.48 | 61.8% | 1.18 | 5 | ₹216 | ₹-12,746 | 44% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 5,405 | 402 | 9,773 | -4,991 | 3,433 | 31,391 | 1,427 | -9,148 | 875 | -11,291 | -6,673 | -22,905 | **-2,303** |
| 2025 | 18,399 | 29,163 | -6,674 | -12,553 | 3,183 | 5,373 | -6,787 | -8,848 | -7,405 | 7,981 | 9,465 | 5,201 | **36,500** |
| 2026 | -10,914 | 1,205 | -9,267 |  |  |  |  |  |  |  |  |  | **-18,977** |

**Quarterly (₹):** 2024-Q1: 15,579, 2024-Q2: 29,833, 2024-Q3: -6,846, 2024-Q4: -40,869, 2025-Q1: 40,888, 2025-Q2: -3,996, 2025-Q3: -23,040, 2025-Q4: 22,648, 2026-Q1: -18,977

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20250407 | 2 | -12,934 | 2 | FLAT @ 12:05 | T0HCE B 23500CE 09:25@6.7→12:05@6.8 (FLAT)<br>T0HPE B 20650PE 09:25@70.0→12:05@45.7 (FLAT)<br>T0CE S 22100CE 09:25@279.5→09:33@365.2 (SL)<br>T0PE S 22100PE 09:25@277.1→12:05@362.0 (SL) |
| 20241105 | 2 | -8,349 | 2 | FLAT @ 14:26 | T0HCE B 24900CE 09:25@3.2→14:26@3.4 (FLAT)<br>T0HPE B 22450PE 09:25@3.8→14:26@2.5 (FLAT)<br>T0CE S 24000CE 09:25@205.7→14:26@268.8 (SL)<br>T0PE S 24000PE 09:25@188.3→11:41@248.9 (SL) |
| 20260201 | 2 | -8,345 | 2 | FLAT @ 12:19 | T0HCE B 26750CE 09:25@4.2→12:19@2.5 (FLAT)<br>T0HPE B 23800PE 09:25@6.1→12:19@4.7 (FLAT)<br>T0CE S 25300CE 09:25@204.1→11:10@266.8 (SL)<br>T0PE S 25300PE 09:25@191.7→12:19@250.5 (SL) |
| 20241220 | 6 | -8,270 | 2 | FLAT @ 09:50 | T0HCE B 25450CE 09:25@4.9→09:50@4.3 (FLAT)<br>T0HPE B 22500PE 09:25@5.0→09:50@5.1 (FLAT)<br>T0CE S 23950CE 09:25@192.6→09:38@251.7 (SL)<br>T0PE S 23950PE 09:25@208.4→09:50@272.3 (SL) |
| 20260129 | 5 | -8,247 | 2 | FLAT @ 13:44 | T0HCE B 26750CE 09:25@4.0→13:44@3.6 (FLAT)<br>T0HPE B 23800PE 09:25@6.9→13:44@6.0 (FLAT)<br>T0CE S 25300CE 09:25@210.1→13:44@274.6 (SL)<br>T0PE S 25300PE 09:25@187.3→09:53@244.7 (SL) |

## B2 — Plain hedged ATM straddle, DTE 1 (Mon under the Tue-expiry calendar)  (tier: baseline)

**Rules — `B2_plain_straddle_dte1`**
1. Trade only on days with DTE 1 (calendar days to the nearest weekly expiry).
2. At 09:25: sell the ATM CE + ATM PE (ATM = strike near spot with the smallest |CE−PE|, i.e. synthetic-future ATM).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹3, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 30% above each leg's sell price (SL-M).
5. Time exit: square off everything at 15:15.

```json
{
 "name": "B2_plain_straddle_dte1",
 "structure": "straddle",
 "dte_allowed": [
  1
 ],
 "entry_minutes": [
  10
 ],
 "sl_pct": 30,
 "hedge_premium": 3,
 "exit_minute": 360
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 69 | ₹5,365 | 1.9% | ₹34,813 (15.3%) | 0.11 | 58.0% | 1.06 | 4 | ₹78 | ₹-6,529 | 50% |
| Validation ₹2L | 22 | ₹2,269 | 2.6% | ₹5,581 (2.8%) | 0.93 | 63.6% | 1.14 | 2 | ₹103 | ₹-4,328 | 50% |
| Holdout ₹2L | 15 | ₹-5,125 | -7.8% | ₹16,933 (8.1%) | -0.92 | 60.0% | 0.79 | 4 | ₹-342 | ₹-7,181 | 75% |
| Full period ₹2L / 1 lot | 106 | ₹2,509 | 0.6% | ₹34,813 (15.3%) | 0.03 | 59.4% | 1.02 | 4 | ₹24 | ₹-7,181 | 56% |
| Full period ₹3L / 2 lots | 106 | ₹25,031 | 3.8% | ₹62,427 (17.4%) | 0.18 | 61.3% | 1.10 | 4 | ₹236 | ₹-14,173 | 56% |
| Full ₹2L, zero brokerage | 106 | ₹22,522 | 5.2% | ₹28,759 (12.4%) | 0.36 | 61.3% | 1.18 | 4 | ₹212 | ₹-6,992 | 52% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 9,566 | 11,454 | 3,646 | -444 | -6,599 | 5,986 | 2,692 | -3,404 | -5,355 | -12,793 | 8,998 | -9,677 | **4,070** |
| 2025 | -7,368 | -2,763 | 5,563 | -4,994 | 8,670 | -827 | -1,903 | 4,961 | -3,617 | 970 | 4,872 | 9,459 | **13,024** |
| 2026 | -9,951 | -3,181 | -1,452 |  |  |  |  |  |  |  |  |  | **-14,585** |

**Quarterly (₹):** 2024-Q1: 24,666, 2024-Q2: -1,057, 2024-Q3: -6,067, 2024-Q4: -13,472, 2025-Q1: -4,568, 2025-Q2: 2,849, 2025-Q3: -559, 2025-Q4: 15,302, 2026-Q1: -14,585

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20260316 | 1 | -7,181 | 2 | FLAT @ 10:26 | T0HCE B 24450CE 09:25@3.1→10:26@2.9 (FLAT)<br>T0HPE B 21700PE 09:25@4.9→10:26@5.0 (FLAT)<br>T0CE S 23150CE 09:25@171.1→09:34@223.6 (SL)<br>T0PE S 23150PE 09:25@177.1→10:26@231.4 (SL) |
| 20260202 | 1 | -6,982 | 2 | FLAT @ 14:52 | T0HCE B 26050CE 09:25@3.1→14:52@1.3 (FLAT)<br>T0HPE B 23600PE 09:25@3.0→14:52@2.0 (FLAT)<br>T0CE S 24850CE 09:25@161.1→14:52@210.5 (SL)<br>T0PE S 24850PE 09:25@168.6→11:22@220.3 (SL) |
| 20250408 | 1 | -6,529 | 2 | FLAT @ 12:31 | T0HCE B 24000CE 09:25@3.0→12:31@1.7 (FLAT)<br>T0HPE B 21050PE 09:25@11.7→12:31@15.8 (FLAT)<br>T0CE S 22550CE 09:25@162.9→12:31@212.9 (SL)<br>T0PE S 22550PE 09:25@161.9→09:57@211.5 (SL) |
| 20250129 | 1 | -5,581 | 2 | FLAT @ 11:24 | T0HCE B 23700CE 09:25@3.2→11:24@4.0 (FLAT)<br>T0HPE B 22250PE 09:25@3.1→11:24@5.6 (FLAT)<br>T0CE S 23050CE 09:25@132.0→10:09@172.6 (SL)<br>T0PE S 23050PE 09:25@146.9→11:24@191.9 (SL) |
| 20241204 | 1 | -5,438 | 2 | FLAT @ 11:56 | T0HCE B 25050CE 09:25@2.8→11:56@2.0 (FLAT)<br>T0HPE B 23550PE 09:25@2.9→11:56@2.3 (FLAT)<br>T0CE S 24500CE 09:25@117.4→10:06@153.4 (SL)<br>T0PE S 24500PE 09:25@139.5→11:56@182.3 (SL) |

## P1 — Portfolio S1+S3 (live calendar: expiry day + DTE 4-6)  (tier: portfolio)

**Rules — `S1_strangle_premium_dte0`**
1. Trade only on days with DTE 0 (calendar days to the nearest weekly expiry).
2. At 09:23: sell the OTM CE and OTM PE whose premium is closest to ₹71 each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹71).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 20.2% above each leg's sell price (SL-M).
5. When one leg is stopped, move the other leg's SL to its sell price +7.4% (move-SL-to-cost).
6. Portfolio max loss: exit everything at −18 premium points (≈ ₹1,170 per lot, before costs).
7. Profit lock: once MTM ≥ +29 pts, lock 64% of it, then raise the lock by 5 pts for every further 10 pts.
8. Time exit: square off everything at 15:02.

```json
{
 "name": "S1_strangle_premium_dte0",
 "structure": "strangle_premium",
 "target_premium": 71,
 "otm_steps": 3,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  0
 ],
 "entry_minutes": [
  8
 ],
 "lots": 1,
 "or_filter_pct": 0.0,
 "sl_mode": "leg",
 "sl_pct": 20.2,
 "combined_sl_pct": 13.4,
 "move_sl_to_cost": true,
 "cost_offset": 0.074,
 "max_reentries": 0,
 "reentry_cutoff": 300,
 "wt_drop_pct": 0,
 "wt_window": 60,
 "max_loss_pts": 18,
 "target_pts": 0,
 "lock_trigger_pts": 29,
 "lock_pct": 0.64,
 "trail_step_pts": 10,
 "trail_by_pts": 5,
 "exit_minute": 347,
 "roll_ratio": 0.0,
 "max_rolls": 2,
 "roll_cutoff": 270
}
```

**Rules — `S3_strangle_premium_dte4567`**
1. Trade only on days with DTE 4, 5, 6, 7 (calendar days to the nearest weekly expiry).
2. At 09:38: sell the OTM CE and OTM PE whose premium is closest to ₹60 each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹60).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 16.9% above each leg's sell price (SL-M).
5. Re-entry: if a stopped leg trades back to its original sell price before 14:15, re-sell it (max 1×).
6. Skip the day if the first 15-min spot range exceeds 0.65% of spot.
7. Portfolio max loss: exit everything at −32 premium points (≈ ₹2,080 per lot, before costs).
8. Time exit: square off everything at 14:22.

```json
{
 "name": "S3_strangle_premium_dte4567",
 "structure": "strangle_premium",
 "target_premium": 60,
 "otm_steps": 1,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  4,
  5,
  6,
  7
 ],
 "entry_minutes": [
  23
 ],
 "lots": 1,
 "or_filter_pct": 0.65,
 "sl_mode": "leg",
 "sl_pct": 16.9,
 "combined_sl_pct": 11.7,
 "move_sl_to_cost": false,
 "cost_offset": 0.072,
 "max_reentries": 1,
 "reentry_cutoff": 300,
 "wt_drop_pct": 0,
 "wt_window": 60,
 "max_loss_pts": 32,
 "target_pts": 0,
 "lock_trigger_pts": 0,
 "lock_pct": 0.52,
 "trail_step_pts": 5,
 "trail_by_pts": 5,
 "exit_minute": 307,
 "roll_ratio": 0.0,
 "max_rolls": 1,
 "roll_cutoff": 270
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 141 | ₹96,503 | 34.0% | ₹5,737 (2.6%) | 11.84 | 63.8% | 2.76 | 6 | ₹684 | ₹-2,527 | 6% |
| Validation ₹2L | 65 | ₹22,713 | 26.0% | ₹3,746 (1.8%) | 13.89 | 70.8% | 2.24 | 3 | ₹349 | ₹-1,603 | 17% |
| Holdout ₹2L | 65 | ₹19,388 | 29.4% | ₹5,081 (2.3%) | 11.59 | 58.5% | 1.69 | 4 | ₹298 | ₹-2,414 | 20% |
| Full period ₹2L / 1 lot | 271 | ₹138,604 | 31.7% | ₹5,737 (2.6%) | 11.05 | 64.2% | 2.37 | 6 | ₹511 | ₹-2,527 | 11% |
| Full period ₹3L / 2 lots | 271 | ₹332,999 | 50.8% | ₹9,770 (2.2%) | 15.59 | 65.7% | 2.84 | 6 | ₹1,229 | ₹-4,771 | 7% |
| Full ₹2L, zero brokerage | 271 | ₹194,395 | 44.5% | ₹4,460 (1.6%) | 19.93 | 68.6% | 3.40 | 4 | ₹717 | ₹-2,244 | 7% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 3,515 | 412 | 6,988 | 1,342 | 12,062 | -2,909 | 3,823 | 2,594 | 2,982 | 10,722 | 6,158 | 6,072 | **53,760** |
| 2025 | 7,807 | 8,423 | 3,477 | 13,027 | 8,332 | 3,665 | 3,129 | 390 | 7,268 | 10,421 | -408 | 11,339 | **76,869** |
| 2026 | 1,998 | 10,543 | -4,565 |  |  |  |  |  |  |  |  |  | **7,975** |

**Quarterly (₹):** 2024-Q1: 10,915, 2024-Q2: 10,494, 2024-Q3: 9,398, 2024-Q4: 22,953, 2025-Q1: 19,707, 2025-Q2: 25,025, 2025-Q3: 10,786, 2025-Q4: 21,351, 2026-Q1: 7,975

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20250523 | 6 | -2,527 | 3 | MAXLOSS @ 12:12 | T0HCE B 26150CE 09:38@2.5→12:12@2.5 (MAXLOSS)<br>T0HPE B 23200PE 09:38@4.7→12:12@4.4 (MAXLOSS)<br>T0CE S 25200CE 09:38@57.7→10:03@67.9 (SL)<br>T0PE S 24350PE 09:38@56.1→11:49@66.0 (SL)<br>T0CE S 25200CE 10:34@55.0→10:37@64.7 (SL)<br>T0PE S 24350PE 12:07@55.6→12:12@59.6 (MAXLOSS) |
| 20260107 | 6 | -2,414 | 3 | MAXLOSS @ 11:23 | T0HCE B 27000CE 09:38@1.9→11:23@1.7 (MAXLOSS)<br>T0HPE B 24750PE 09:38@2.0→11:23@1.8 (MAXLOSS)<br>T0CE S 26250CE 09:38@66.8→10:12@78.5 (SL)<br>T0PE S 26050PE 09:38@60.3→09:46@70.9 (SL)<br>T0PE S 26050PE 09:59@57.2→11:23@55.1 (MAXLOSS)<br>T0CE S 26250CE 10:29@66.5→10:56@78.2 (SL) |
| 20250110 | 6 | -2,363 | 3 | MAXLOSS @ 11:04 | T0HCE B 24650CE 09:38@2.1→11:04@1.9 (MAXLOSS)<br>T0HPE B 22100PE 09:38@4.2→11:04@4.0 (MAXLOSS)<br>T0CE S 23800CE 09:38@61.1→11:04@71.8 (SL)<br>T0PE S 23050PE 09:38@62.4→09:59@73.3 (SL)<br>T0PE S 23050PE 10:22@58.2→10:32@68.5 (SL) |
| 20250117 | 6 | -2,349 | 3 | MAXLOSS @ 12:00 | T0HCE B 24500CE 09:38@2.0→12:00@1.9 (MAXLOSS)<br>T0HPE B 21750PE 09:38@3.0→12:00@3.4 (MAXLOSS)<br>T0CE S 23500CE 09:38@62.3→10:26@73.2 (SL)<br>T0PE S 22900PE 09:38@62.3→10:49@73.2 (SL)<br>T0CE S 23500CE 10:44@60.5→12:00@71.1 (SL) |
| 20260121 | 6 | -2,246 | 3 | FLAT @ 14:15 | T0HCE B 26650CE 09:38@2.9→14:15@1.9 (FLAT)<br>T0HPE B 23700PE 09:38@7.8→14:15@7.4 (FLAT)<br>T0CE S 25500CE 09:38@55.0→12:37@64.7 (SL)<br>T0PE S 24950PE 09:38@57.3→10:00@67.4 (SL)<br>T0CE S 25500CE 13:34@53.9→13:38@63.4 (SL) |

## P2 — Portfolio S1+S2+S3 (all discovered, disjoint DTE days)  (tier: portfolio)

**Rules — `S1_strangle_premium_dte0`**
1. Trade only on days with DTE 0 (calendar days to the nearest weekly expiry).
2. At 09:23: sell the OTM CE and OTM PE whose premium is closest to ₹71 each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹71).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 20.2% above each leg's sell price (SL-M).
5. When one leg is stopped, move the other leg's SL to its sell price +7.4% (move-SL-to-cost).
6. Portfolio max loss: exit everything at −18 premium points (≈ ₹1,170 per lot, before costs).
7. Profit lock: once MTM ≥ +29 pts, lock 64% of it, then raise the lock by 5 pts for every further 10 pts.
8. Time exit: square off everything at 15:02.

```json
{
 "name": "S1_strangle_premium_dte0",
 "structure": "strangle_premium",
 "target_premium": 71,
 "otm_steps": 3,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  0
 ],
 "entry_minutes": [
  8
 ],
 "lots": 1,
 "or_filter_pct": 0.0,
 "sl_mode": "leg",
 "sl_pct": 20.2,
 "combined_sl_pct": 13.4,
 "move_sl_to_cost": true,
 "cost_offset": 0.074,
 "max_reentries": 0,
 "reentry_cutoff": 300,
 "wt_drop_pct": 0,
 "wt_window": 60,
 "max_loss_pts": 18,
 "target_pts": 0,
 "lock_trigger_pts": 29,
 "lock_pct": 0.64,
 "trail_step_pts": 10,
 "trail_by_pts": 5,
 "exit_minute": 347,
 "roll_ratio": 0.0,
 "max_rolls": 2,
 "roll_cutoff": 270
}
```

**Rules — `S2_strangle_offset_dte23`**
1. Trade only on days with DTE 2, 3 (calendar days to the nearest weekly expiry).
2. At 10:08: sell CE at ATM+3 strikes and PE at ATM−3 strikes (150 pts each side).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 24.6% above each leg's sell price (SL-M).
5. Re-entry: if a stopped leg trades back to its original sell price before 14:15, re-sell it (max 2×).
6. Wait & trade: sell each leg only after it decays 5% from its reference price (within 60 min).
7. Skip the day if the first 15-min spot range exceeds 0.4% of spot.
8. Time exit: square off everything at 14:33.

```json
{
 "name": "S2_strangle_offset_dte23",
 "structure": "strangle_offset",
 "target_premium": 130,
 "otm_steps": 3,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  2,
  3
 ],
 "entry_minutes": [
  53
 ],
 "lots": 1,
 "or_filter_pct": 0.4,
 "sl_mode": "leg",
 "sl_pct": 24.6,
 "combined_sl_pct": 16.4,
 "move_sl_to_cost": false,
 "cost_offset": -0.1,
 "max_reentries": 2,
 "reentry_cutoff": 300,
 "wt_drop_pct": 5,
 "wt_window": 60,
 "max_loss_pts": 0,
 "target_pts": 0,
 "lock_trigger_pts": 0,
 "lock_pct": 0.31,
 "trail_step_pts": 0,
 "trail_by_pts": 5,
 "exit_minute": 318,
 "roll_ratio": 0.0,
 "max_rolls": 1,
 "roll_cutoff": 270
}
```

**Rules — `S3_strangle_premium_dte4567`**
1. Trade only on days with DTE 4, 5, 6, 7 (calendar days to the nearest weekly expiry).
2. At 09:38: sell the OTM CE and OTM PE whose premium is closest to ₹60 each (premium-matched; collapses to the ATM straddle when ATM premium ≤ ₹60).
3. Simultaneously buy far-OTM wings (CE & PE) priced closest to ₹2, at least 4 strikes beyond the shorts — for margin benefit and gap protection.
4. Per-leg stop-loss: 16.9% above each leg's sell price (SL-M).
5. Re-entry: if a stopped leg trades back to its original sell price before 14:15, re-sell it (max 1×).
6. Skip the day if the first 15-min spot range exceeds 0.65% of spot.
7. Portfolio max loss: exit everything at −32 premium points (≈ ₹2,080 per lot, before costs).
8. Time exit: square off everything at 14:22.

```json
{
 "name": "S3_strangle_premium_dte4567",
 "structure": "strangle_premium",
 "target_premium": 60,
 "otm_steps": 1,
 "hedge_premium": 2.0,
 "hedge_min_steps": 4,
 "dte_allowed": [
  4,
  5,
  6,
  7
 ],
 "entry_minutes": [
  23
 ],
 "lots": 1,
 "or_filter_pct": 0.65,
 "sl_mode": "leg",
 "sl_pct": 16.9,
 "combined_sl_pct": 11.7,
 "move_sl_to_cost": false,
 "cost_offset": 0.072,
 "max_reentries": 1,
 "reentry_cutoff": 300,
 "wt_drop_pct": 0,
 "wt_window": 60,
 "max_loss_pts": 32,
 "target_pts": 0,
 "lock_trigger_pts": 0,
 "lock_pct": 0.52,
 "trail_step_pts": 5,
 "trail_by_pts": 5,
 "exit_minute": 307,
 "roll_ratio": 0.0,
 "max_rolls": 1,
 "roll_cutoff": 270
}
```

| Window | Trade days | Net P&L | ROI/yr | Max DD | Calmar | Win % | PF | Max consec. losing days | Expectancy / lot-day | Worst day | Losing months |
|---|---|---|---|---|---|---|---|---|---|---|---|
| In-sample (train) ₹2L | 252 | ₹133,890 | 47.1% | ₹6,883 (3.0%) | 13.69 | 62.7% | 2.52 | 6 | ₹531 | ₹-2,527 | 0% |
| Validation ₹2L | 86 | ₹32,396 | 37.1% | ₹3,462 (1.6%) | 21.44 | 70.9% | 2.45 | 4 | ₹377 | ₹-1,603 | 17% |
| Holdout ₹2L | 67 | ₹16,072 | 24.4% | ₹5,959 (2.7%) | 8.19 | 56.7% | 1.51 | 5 | ₹240 | ₹-2,438 | 20% |
| Full period ₹2L / 1 lot | 405 | ₹182,358 | 41.7% | ₹6,883 (3.0%) | 12.12 | 63.5% | 2.29 | 6 | ₹450 | ₹-2,527 | 7% |
| Full period ₹3L / 2 lots | 405 | ₹445,051 | 67.8% | ₹12,444 (3.3%) | 16.36 | 65.4% | 2.77 | 6 | ₹1,099 | ₹-4,771 | 4% |
| Full ₹2L, zero brokerage | 405 | ₹262,693 | 60.1% | ₹5,561 (2.2%) | 21.60 | 68.6% | 3.35 | 5 | ₹649 | ₹-2,297 | 4% |

**Monthly net P&L (₹, 1 lot)**

| Month | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 4,719 | 3,596 | 4,892 | 2,705 | 13,471 | 1,386 | 1,755 | 4,164 | 5,373 | 17,826 | 6,171 | 9,449 | **75,507** |
| 2025 | 18,116 | 10,285 | 4,779 | 14,714 | 9,066 | 4,797 | 4,762 | 7,978 | 7,268 | 9,496 | -408 | 11,339 | **102,193** |
| 2026 | 1,998 | 7,226 | -4,565 |  |  |  |  |  |  |  |  |  | **4,658** |

**Quarterly (₹):** 2024-Q1: 13,206, 2024-Q2: 17,562, 2024-Q3: 11,292, 2024-Q4: 33,446, 2025-Q1: 33,181, 2025-Q2: 28,577, 2025-Q3: 20,008, 2025-Q4: 20,427, 2026-Q1: 4,658

**Top-5 worst days**

| Date | DTE | Net ₹ | Stops | Final exit | Legs |
|---|---|---|---|---|---|
| 20250523 | 6 | -2,527 | 3 | MAXLOSS @ 12:12 | T0HCE B 26150CE 09:38@2.5→12:12@2.5 (MAXLOSS)<br>T0HPE B 23200PE 09:38@4.7→12:12@4.4 (MAXLOSS)<br>T0CE S 25200CE 09:38@57.7→10:03@67.9 (SL)<br>T0PE S 24350PE 09:38@56.1→11:49@66.0 (SL)<br>T0CE S 25200CE 10:34@55.0→10:37@64.7 (SL)<br>T0PE S 24350PE 12:07@55.6→12:12@59.6 (MAXLOSS) |
| 20260201 | 2 | -2,438 | 1 | FLAT @ 14:15 | T0HCE B 26750CE 10:08@5.1→14:15@1.8 (FLAT)<br>T0HPE B 23800PE 10:08@5.5→14:15@6.4 (FLAT)<br>T0PE S 25200PE 10:15@128.7→12:12@161.2 (SL) |
| 20260107 | 6 | -2,414 | 3 | MAXLOSS @ 11:23 | T0HCE B 27000CE 09:38@1.9→11:23@1.7 (MAXLOSS)<br>T0HPE B 24750PE 09:38@2.0→11:23@1.8 (MAXLOSS)<br>T0CE S 26250CE 09:38@66.8→10:12@78.5 (SL)<br>T0PE S 26050PE 09:38@60.3→09:46@70.9 (SL)<br>T0PE S 26050PE 09:59@57.2→11:23@55.1 (MAXLOSS)<br>T0CE S 26250CE 10:29@66.5→10:56@78.2 (SL) |
| 20240319 | 2 | -2,395 | 3 | TIME @ 14:33 | T0HCE B 22700CE 10:08@2.0→14:33@1.7 (TIME)<br>T0HPE B 21000PE 10:08@2.0→14:33@1.1 (TIME)<br>T0PE S 21750PE 10:09@67.1→10:30@84.1 (SL)<br>T0CE S 22050CE 10:29@54.6→14:33@35.2 (TIME)<br>T0PE S 21750PE 10:34@65.5→11:40@82.1 (SL)<br>T0PE S 21750PE 12:26@65.5→14:16@82.1 (SL) |
| 20250110 | 6 | -2,363 | 3 | MAXLOSS @ 11:04 | T0HCE B 24650CE 09:38@2.1→11:04@1.9 (MAXLOSS)<br>T0HPE B 22100PE 09:38@4.2→11:04@4.0 (MAXLOSS)<br>T0CE S 23800CE 09:38@61.1→11:04@71.8 (SL)<br>T0PE S 23050PE 09:38@62.4→09:59@73.3 (SL)<br>T0PE S 23050PE 10:22@58.2→10:32@68.5 (SL) |

## Worst-day analysis (S1 / S3)

- S1's five worst days are all the same pattern: a fast move right after the 09:23 entry stops one leg (20% SL), the other leg's SL is pulled to cost +7.4%, the reversal stops it too, and the 18-point portfolio cap closes the day at about −₹1.6k. The tail is **capped by construction**. No day lost more than ₹1,603 on 1 lot.
- S3 (DTE 4–6) loses through slow trend days: one leg stopped, the other decays too slowly to pay for it. Its worst day is −₹2.5k, also inside the ₹3k gate.
- Phase-D diagnostics in the log flagged double-SL whipsaws and gap-and-go mornings as the main loss drivers. That is why move-SL-to-cost and the hard max-loss survive in every finalist.

## Honest caveats

- 551 days (≈2.2 years) is a short history for tail risk. A 2020-style crash or a budget-day gap is not in the sample.
- 2025–26 data is 1-minute LTP, not true OHLC, so intrabar spikes beyond the LTP envelope are missed. The 0.5% stop slippage only partly compensates.
- Wing prices of ₹2–5 are often stale or illiquid; real fills can be worse.
- ~8,000 configurations were tested. Splits, stability and a holdout were used, but selection bias cannot be fully removed. Paper-trade before going live.
- 2026 Q1 (holdout tail) was flat to slightly negative for S2/S3. Edge decay is possible.
