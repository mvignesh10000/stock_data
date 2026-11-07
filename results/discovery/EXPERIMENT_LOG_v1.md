# EXPERIMENT_LOG — autonomous discovery of NIFTY intraday non-directional selling strategies

Splits (chronological): train (20240101, 20250616), validation (20250617, 20251124), holdout (20251125, 20260324).

Costs: ₹20/order brokerage, STT 0.1% sell, NSE txn 0.03503%, SEBI 0.0001%, stamp 0.003% buy, GST 18%; slippage 0.3% per market fill (min 0.05), +0.5% on stop fills; lot 65 constant; capital ₹2,00,000 per lot.

## Generation 1  (400 train runs in 0.9s engine time, 3.3s wall)

- Hard-gate passes on train: **0/400**
- Top `g1_381` straddle_d0 (score 1.71): net ₹50,221 | DD ₹7,977 | Calmar 4.43 | PF 2.12 | win 67.1% | exp ₹661 | worst ₹-3,419 | losing-months 22% | UW 9d
  - gate failures: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%
- Top `g1_312` strangle_offset_d0 (score 0.87): net ₹32,661 | DD ₹7,852 | Calmar 2.93 | PF 2.10 | win 63.2% | exp ₹430 | worst ₹-3,389 | losing-months 17% | UW 16d
  - gate failures: thin edge: expectancy ₹430 < ₹450; tail: worst day ₹3389 > 1.5% of capital; losing months 16.7% > 15%
- Top `g1_185` strangle_offset_d456 (score 0.71): net ₹32,758 | DD ₹7,142 | Calmar 3.23 | PF 1.85 | win 57.1% | exp ₹468 | worst ₹-3,179 | losing-months 33% | UW 11d
  - gate failures: tail: worst day ₹3179 > 1.5% of capital; losing months 33.3% > 15%
- Phase B stability audit:
  - `g1_381` straddle_d0 Calmar 4.43 → neighbour mean 5.02, Stability 1.13 ✅
  - `g1_312` strangle_offset_d0 Calmar 2.93 → neighbour mean 2.63, Stability 0.90 ✅
  - `g1_185` strangle_offset_d456 Calmar 3.23 → neighbour mean 2.88, Stability 0.89 ✅
  - `g1_399` strangle_premium_d0 Calmar 3.71 → neighbour mean 2.61, Stability 0.70 ❌ discarded (lucky spike)
  - `g1_134` strangle_offset_d0 Calmar 3.42 → neighbour mean 2.84, Stability 0.83 ✅
  - `g1_187` strangle_offset_d456 Calmar 2.48 → neighbour mean 1.99, Stability 0.80 ✅
  - `g1_335` strangle_premium_d456 Calmar 2.28 → neighbour mean 0.96, Stability 0.42 ❌ discarded (lucky spike)
  - `g1_43` straddle_d456 Calmar 2.56 → neighbour mean 2.48, Stability 0.97 ✅
  - `g1_85` strangle_premium_d456 Calmar 2.41 → neighbour mean 1.52, Stability 0.63 ❌ discarded (lucky spike)
  - `g1_220` strangle_premium_d456 Calmar 1.40 → neighbour mean 1.33, Stability 0.95 ✅
- Phase C walk-forward/holdout:
  - `g1_381` straddle_d0: valid Calmar 2.72 PF 1.55 net ₹6,526; holdout not touched → rejected (train hard-gate: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 2.72/PF 1.55)
  - `g1_312` strangle_offset_d0: valid Calmar 1.61 PF 1.47 net ₹3,020; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹430 < ₹450; tail: worst day ₹3389 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar 1.61/PF 1.47)
  - `g1_185` strangle_offset_d456: valid Calmar 0.05 PF 1.01 net ₹188; holdout not touched → rejected (train hard-gate: tail: worst day ₹3179 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar 0.05/PF 1.01)
  - `g1_134` strangle_offset_d0: valid Calmar -2.19 PF 0.39 net ₹-5,653; holdout not touched → rejected (train hard-gate: losing months 50.0% > 15%; underwater 30 active days > 25; validation Calmar -2.19/PF 0.39)
  - `g1_187` strangle_offset_d456: valid Calmar -0.76 PF 0.85 net ₹-2,137; holdout not touched → rejected (train hard-gate: tail: worst day ₹3145 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.76/PF 0.85)
  - `g1_43` straddle_d456: valid Calmar 1.18 PF 1.24 net ₹2,640; holdout not touched → rejected (train hard-gate: tail: worst day ₹5993 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar 1.18/PF 1.24)
  - `g1_220` strangle_premium_d456: valid Calmar -0.16 PF 0.97 net ₹-327; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹166 < ₹450; tail: worst day ₹3645 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.16/PF 0.97)
- Phase D hypotheses:
  - 9/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 4/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 10/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20240808(dte0,₹-3,419,1SL,MAXLOSS), 20240718(dte0,₹-3,298,3SL,MAXLOSS), 20250515(dte0,₹-3,031,2SL,MAXLOSS), 20240912(dte0,₹-2,756,3SL,MAXLOSS), 20240926(dte0,₹-2,692,2SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[0, 1]
- Next-gen bucket weights: d0=2.11, d1=0.40, d01=0.47, d12=0.46, d23=0.48, d456=1.11, d0123=0.44

## Generation 2  (378 train runs in 0.8s engine time, 3.4s wall)

- Hard-gate passes on train: **0/378**
- Top `g2_266` straddle_d456 (score 5.51): net ₹79,218 | DD ₹6,167 | Calmar 9.04 | PF 3.94 | win 50.0% | exp ₹1523 | worst ₹-5,773 | losing-months 33% | UW 12d
  - gate failures: tail: worst day ₹5773 > 1.5% of capital; losing months 33.3% > 15%
- Top `g2_367` straddle_d456 (score 4.87): net ₹50,009 | DD ₹5,904 | Calmar 5.96 | PF 3.05 | win 76.9% | exp ₹962 | worst ₹-5,745 | losing-months 17% | UW 13d
  - gate failures: tail: worst day ₹5745 > 1.5% of capital; losing months 16.7% > 15%
- Top `g2_264` strangle_premium_d0 (score 3.66): net ₹43,788 | DD ₹6,605 | Calmar 4.67 | PF 2.27 | win 34.2% | exp ₹576 | worst ₹-1,353 | losing-months 17% | UW 16d
  - gate failures: losing months 16.7% > 15%
- Phase B stability audit:
  - `g2_266` straddle_d456 Calmar 9.04 → neighbour mean 7.01, Stability 0.77 ✅
  - `g2_367` straddle_d456 Calmar 5.96 → neighbour mean 3.43, Stability 0.58 ❌ discarded (lucky spike)
  - `g2_264` strangle_premium_d0 Calmar 4.67 → neighbour mean 4.37, Stability 0.94 ✅
  - `g2_194` strangle_offset_d0 Calmar 6.62 → neighbour mean 3.52, Stability 0.53 ❌ discarded (lucky spike)
  - `g2_207` straddle_d0 Calmar 5.39 → neighbour mean 4.03, Stability 0.75 ❌ discarded (lucky spike)
  - `g2_351` strangle_offset_d0 Calmar 5.37 → neighbour mean 2.66, Stability 0.50 ❌ discarded (lucky spike)
  - `g2_192` straddle_d0 Calmar 4.84 → neighbour mean 4.92, Stability 1.02 ✅
  - `g2_372` straddle_d0 Calmar 5.11 → neighbour mean 5.19, Stability 1.02 ✅
  - `g2_127` straddle_d0 Calmar 4.18 → neighbour mean 2.10, Stability 0.50 ❌ discarded (lucky spike)
  - `g2_268` straddle_d0 Calmar 4.43 → neighbour mean 5.02, Stability 1.13 ✅
- Phase C walk-forward/holdout:
  - `g2_266` straddle_d456: valid Calmar -0.51 PF 0.91 net ₹-2,608; holdout not touched → rejected (train hard-gate: tail: worst day ₹5773 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.51/PF 0.91)
  - `g2_264` strangle_premium_d0: valid Calmar -0.01 PF 1.00 net ₹-30; holdout not touched → rejected (train hard-gate: losing months 16.7% > 15%; validation Calmar -0.01/PF 1.00)
  - `g2_192` straddle_d0: valid Calmar 1.18 PF 1.16 net ₹2,269; holdout not touched → rejected (train hard-gate: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 1.18/PF 1.16)
  - `g2_372` straddle_d0: valid Calmar 0.32 PF 1.05 net ₹796; holdout not touched → rejected (train hard-gate: tail: worst day ₹3177 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 0.32/PF 1.05)
  - `g2_268` straddle_d0: valid Calmar 2.72 PF 1.55 net ₹6,526; holdout not touched → rejected (train hard-gate: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 2.72/PF 1.55)
- Phase D hypotheses:
  - 7/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - Leader worst days: 20240105(dte6,₹-5,773,4SL,FLAT), 20241220(dte6,₹-3,092,4SL,TIME), 20240712(dte6,₹-2,640,3SL,TIME), 20240816(dte6,₹-2,593,5SL,TIME), 20250321(dte6,₹-2,327,4SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[1], straddle/DTE[1, 2], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

## Generation 3  (356 train runs in 0.7s engine time, 3.3s wall)

- Hard-gate passes on train: **0/356**
- Top `g3_238` straddle_d456 (score 14.39): net ₹56,954 | DD ₹4,511 | Calmar 8.89 | PF 3.92 | win 73.1% | exp ₹1095 | worst ₹-4,511 | losing-months 17% | UW 6d
  - gate failures: tail: worst day ₹4511 > 1.5% of capital; losing months 16.7% > 15%
- Top `g3_265` straddle_d456 (score 13.82): net ₹55,313 | DD ₹4,511 | Calmar 8.63 | PF 3.91 | win 76.9% | exp ₹1064 | worst ₹-4,511 | losing-months 17% | UW 9d
  - gate failures: tail: worst day ₹4511 > 1.5% of capital; losing months 16.7% > 15%
- Top `g3_334` straddle_d456 (score 13.82): net ₹55,313 | DD ₹4,511 | Calmar 8.63 | PF 3.91 | win 76.9% | exp ₹1064 | worst ₹-4,511 | losing-months 17% | UW 9d
  - gate failures: tail: worst day ₹4511 > 1.5% of capital; losing months 16.7% > 15%
- Phase B stability audit:
  - `g3_238` straddle_d456 Calmar 8.89 → neighbour mean 5.85, Stability 0.66 ❌ discarded (lucky spike)
  - `g3_265` straddle_d456 Calmar 8.63 → neighbour mean 5.56, Stability 0.64 ❌ discarded (lucky spike)
  - `g3_334` straddle_d456 Calmar 8.63 → neighbour mean 5.56, Stability 0.64 ❌ discarded (lucky spike)
  - `g3_239` straddle_d456 Calmar 10.04 → neighbour mean 7.72, Stability 0.77 ✅
  - `g3_292` straddle_d456 Calmar 9.82 → neighbour mean 7.95, Stability 0.81 ✅
  - `g3_175` strangle_offset_d0 Calmar 9.52 → neighbour mean 6.05, Stability 0.64 ❌ discarded (lucky spike)
  - `g3_211` straddle_d456 Calmar 9.81 → neighbour mean 6.75, Stability 0.69 ❌ discarded (lucky spike)
  - `g3_291` strangle_offset_d0 Calmar 8.02 → neighbour mean 8.20, Stability 1.02 ✅
  - `g3_346` straddle_d456 Calmar 9.04 → neighbour mean 7.01, Stability 0.77 ✅
  - `g3_344` straddle_d0 Calmar 4.94 → neighbour mean 5.15, Stability 1.04 ✅
- Phase C walk-forward/holdout:
  - `g3_239` straddle_d456: valid Calmar -0.38 PF 0.93 net ₹-1,829; holdout not touched → rejected (train hard-gate: tail: worst day ₹5797 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.38/PF 0.93)
  - `g3_292` straddle_d456: valid Calmar -0.54 PF 0.90 net ₹-2,865; holdout not touched → rejected (train hard-gate: tail: worst day ₹5797 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.54/PF 0.90)
  - `g3_291` strangle_offset_d0: valid Calmar -1.42 PF 0.72 net ₹-6,031; holdout not touched → rejected (train hard-gate: losing months 22.2% > 15%; validation Calmar -1.42/PF 0.72)
  - `g3_346` straddle_d456: valid Calmar -0.51 PF 0.91 net ₹-2,608; holdout not touched → rejected (train hard-gate: tail: worst day ₹5773 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.51/PF 0.91)
  - `g3_344` straddle_d0: valid Calmar 0.08 PF 1.02 net ₹322; holdout not touched → rejected (train hard-gate: tail: worst day ₹7904 > 1.5% of capital; validation Calmar 0.08/PF 1.02)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20241220(dte6,₹-4,511,2SL,TIME), 20240816(dte6,₹-3,268,2SL,TIME), 20240105(dte6,₹-3,078,1SL,TIME), 20240802(dte6,₹-1,878,1SL,TIME), 20240712(dte6,₹-1,576,1SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

## Generation 4  (343 train runs in 0.7s engine time, 3.3s wall)

- Hard-gate passes on train: **0/343**
- Top `g4_312` straddle_d456 (score 35.37): net ₹59,999 | DD ₹4,624 | Calmar 9.13 | PF 4.59 | win 78.8% | exp ₹1154 | worst ₹-4,624 | losing-months 11% | UW 6d
  - gate failures: tail: worst day ₹4624 > 1.5% of capital
- Top `g4_335` straddle_d456 (score 24.04): net ₹74,321 | DD ₹3,901 | Calmar 13.41 | PF 4.46 | win 59.6% | exp ₹1429 | worst ₹-3,901 | losing-months 22% | UW 14d
  - gate failures: tail: worst day ₹3901 > 1.5% of capital; losing months 22.2% > 15%
- Top `g4_226` straddle_d456 (score 12.91): net ₹57,372 | DD ₹4,511 | Calmar 8.95 | PF 3.72 | win 71.2% | exp ₹1103 | worst ₹-4,511 | losing-months 17% | UW 8d
  - gate failures: tail: worst day ₹4511 > 1.5% of capital; losing months 16.7% > 15%
- Phase B stability audit:
  - `g4_312` straddle_d456 Calmar 9.13 → neighbour mean 5.75, Stability 0.63 ❌ discarded (lucky spike)
  - `g4_335` straddle_d456 Calmar 13.41 → neighbour mean 7.58, Stability 0.57 ❌ discarded (lucky spike)
  - `g4_226` straddle_d456 Calmar 8.95 → neighbour mean 5.94, Stability 0.66 ❌ discarded (lucky spike)
  - `g4_171` straddle_d456 Calmar 8.40 → neighbour mean 5.57, Stability 0.66 ❌ discarded (lucky spike)
  - `g4_167` straddle_d456 Calmar 10.09 → neighbour mean 7.74, Stability 0.77 ✅
  - `g4_248` strangle_offset_d0 Calmar 10.28 → neighbour mean 6.67, Stability 0.65 ❌ discarded (lucky spike)
  - `g4_213` straddle_d0 Calmar 10.85 → neighbour mean 5.85, Stability 0.54 ❌ discarded (lucky spike)
  - `g4_321` straddle_d456 Calmar 9.82 → neighbour mean 7.95, Stability 0.81 ✅
  - `g4_191` strangle_offset_d0 Calmar 9.52 → neighbour mean 5.78, Stability 0.61 ❌ discarded (lucky spike)
  - `g4_265` strangle_offset_d0 Calmar 9.52 → neighbour mean 5.78, Stability 0.61 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g4_167` straddle_d456: valid Calmar -0.34 PF 0.94 net ₹-1,644; holdout not touched → rejected (train hard-gate: tail: worst day ₹5797 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.34/PF 0.94)
  - `g4_321` straddle_d456: valid Calmar -0.54 PF 0.90 net ₹-2,865; holdout not touched → rejected (train hard-gate: tail: worst day ₹5797 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.54/PF 0.90)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20241220(dte6,₹-4,624,2SL,TIME), 20240105(dte6,₹-3,000,1SL,TIME), 20250328(dte6,₹-1,902,2SL,TIME), 20240802(dte6,₹-1,838,1SL,TIME), 20240712(dte6,₹-1,630,1SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

## Generation 5  (352 train runs in 0.7s engine time, 2.8s wall)

- Hard-gate passes on train: **1/352**
- Top `g5_285` strangle_offset_d0 (score 42.40): net ₹57,514 | DD ₹4,078 | Calmar 9.93 | PF 2.61 | win 56.6% | exp ₹757 | worst ₹-1,870 | losing-months 11% | UW 6d
- Top `g5_228` straddle_d456 (score 32.11): net ₹59,167 | DD ₹5,058 | Calmar 8.23 | PF 4.44 | win 75.0% | exp ₹1138 | worst ₹-5,058 | losing-months 11% | UW 7d
  - gate failures: tail: worst day ₹5058 > 1.5% of capital
- Top `g5_258` straddle_d456 (score 29.66): net ₹74,934 | DD ₹3,078 | Calmar 17.14 | PF 4.87 | win 55.8% | exp ₹1441 | worst ₹-3,078 | losing-months 28% | UW 14d
  - gate failures: tail: worst day ₹3078 > 1.5% of capital; losing months 27.8% > 15%
- Phase B stability audit:
  - `g5_285` strangle_offset_d0 Calmar 9.93 → neighbour mean 5.83, Stability 0.59 ❌ discarded (lucky spike)
  - `g5_228` straddle_d456 Calmar 8.23 → neighbour mean 5.66, Stability 0.69 ❌ discarded (lucky spike)
  - `g5_258` straddle_d456 Calmar 17.14 → neighbour mean 8.33, Stability 0.49 ❌ discarded (lucky spike)
  - `g5_192` straddle_d456 Calmar 6.25 → neighbour mean 3.85, Stability 0.62 ❌ discarded (lucky spike)
  - `g5_277` straddle_d456 Calmar 8.89 → neighbour mean 5.85, Stability 0.66 ❌ discarded (lucky spike)
  - `g5_268` straddle_d456 Calmar 8.63 → neighbour mean 5.56, Stability 0.64 ❌ discarded (lucky spike)
  - `g5_287` straddle_d456 Calmar 8.53 → neighbour mean 5.79, Stability 0.68 ❌ discarded (lucky spike)
  - `g5_185` straddle_d456 Calmar 10.23 → neighbour mean 5.79, Stability 0.57 ❌ discarded (lucky spike)
  - `g5_186` straddle_d456 Calmar 8.95 → neighbour mean 5.94, Stability 0.66 ❌ discarded (lucky spike)
  - `g5_302` straddle_d456 Calmar 8.95 → neighbour mean 5.94, Stability 0.66 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - (no stable candidates)
- Phase D hypotheses:
  - 10/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 7/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 9/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241205(dte0,₹-1,870,2SL,MAXLOSS), 20241114(dte0,₹-1,808,3SL,MAXLOSS), 20240321(dte0,₹-1,681,4SL,MAXLOSS), 20240829(dte0,₹-1,671,4SL,MAXLOSS), 20240606(dte0,₹-1,643,3SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

## Generation 6  (348 train runs in 0.6s engine time, 2.7s wall)

- Hard-gate passes on train: **0/348**
- Top `g6_317` straddle_d456 (score 71.91): net ₹78,419 | DD ₹2,874 | Calmar 19.20 | PF 5.47 | win 61.5% | exp ₹1508 | worst ₹-2,755 | losing-months 22% | UW 14d
  - gate failures: losing months 22.2% > 15%
- Top `g6_204` straddle_d456 (score 43.77): net ₹60,029 | DD ₹4,291 | Calmar 9.85 | PF 4.95 | win 78.8% | exp ₹1154 | worst ₹-4,291 | losing-months 11% | UW 9d
  - gate failures: tail: worst day ₹4291 > 1.5% of capital
- Top `g6_322` straddle_d456 (score 32.11): net ₹59,167 | DD ₹5,058 | Calmar 8.23 | PF 4.44 | win 75.0% | exp ₹1138 | worst ₹-5,058 | losing-months 11% | UW 7d
  - gate failures: tail: worst day ₹5058 > 1.5% of capital
- Phase B stability audit:
  - `g6_317` straddle_d456 Calmar 19.20 → neighbour mean 9.05, Stability 0.47 ❌ discarded (lucky spike)
  - `g6_204` straddle_d456 Calmar 9.85 → neighbour mean 5.57, Stability 0.57 ❌ discarded (lucky spike)
  - `g6_322` straddle_d456 Calmar 8.23 → neighbour mean 5.66, Stability 0.69 ❌ discarded (lucky spike)
  - `g6_244` straddle_d456 Calmar 6.53 → neighbour mean 3.97, Stability 0.61 ❌ discarded (lucky spike)
  - `g6_179` straddle_d456 Calmar 17.14 → neighbour mean 8.33, Stability 0.49 ❌ discarded (lucky spike)
  - `g6_187` straddle_d456 Calmar 17.14 → neighbour mean 8.33, Stability 0.49 ❌ discarded (lucky spike)
  - `g6_216` straddle_d456 Calmar 17.14 → neighbour mean 8.33, Stability 0.49 ❌ discarded (lucky spike)
  - `g6_327` straddle_d456 Calmar 17.14 → neighbour mean 8.33, Stability 0.49 ❌ discarded (lucky spike)
  - `g6_353` straddle_d456 Calmar 8.02 → neighbour mean 5.23, Stability 0.65 ❌ discarded (lucky spike)
  - `g6_305` straddle_d456 Calmar 9.27 → neighbour mean 6.23, Stability 0.67 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - (no stable candidates)
- Phase D hypotheses:
  - 5/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - Leader worst days: 20250321(dte6,₹-2,755,2SL,TIME), 20241220(dte6,₹-2,502,2SL,TIME), 20240105(dte6,₹-2,432,2SL,TIME), 20240301(dte6,₹-2,069,2SL,TIME), 20250228(dte6,₹-1,044,0SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

## Generation 7  (336 train runs in 0.7s engine time, 3.3s wall)

- Hard-gate passes on train: **2/336**
- Top `g7_222` straddle_d456 (score 71.91): net ₹78,419 | DD ₹2,874 | Calmar 19.20 | PF 5.47 | win 61.5% | exp ₹1508 | worst ₹-2,755 | losing-months 22% | UW 14d
  - gate failures: losing months 22.2% > 15%
- Top `g7_153` straddle_d456 (score 52.64): net ₹78,182 | DD ₹3,190 | Calmar 17.25 | PF 5.77 | win 55.8% | exp ₹1504 | worst ₹-2,200 | losing-months 28% | UW 14d
  - gate failures: losing months 27.8% > 15%
- Top `g7_293` straddle_d456 (score 46.24): net ₹61,636 | DD ₹4,405 | Calmar 9.85 | PF 5.05 | win 78.8% | exp ₹1185 | worst ₹-4,405 | losing-months 11% | UW 6d
  - gate failures: tail: worst day ₹4405 > 1.5% of capital
- Phase B stability audit:
  - `g7_222` straddle_d456 Calmar 19.20 → neighbour mean 9.05, Stability 0.47 ❌ discarded (lucky spike)
  - `g7_153` straddle_d456 Calmar 17.25 → neighbour mean 8.51, Stability 0.49 ❌ discarded (lucky spike)
  - `g7_293` straddle_d456 Calmar 9.85 → neighbour mean 5.76, Stability 0.59 ❌ discarded (lucky spike)
  - `g7_198` straddle_d456 Calmar 9.85 → neighbour mean 5.57, Stability 0.57 ❌ discarded (lucky spike)
  - `g7_239` strangle_offset_d0 Calmar 9.93 → neighbour mean 5.83, Stability 0.59 ❌ discarded (lucky spike)
  - `g7_341` straddle_d456 Calmar 10.37 → neighbour mean 6.07, Stability 0.59 ❌ discarded (lucky spike)
  - `g7_187` straddle_d456 Calmar 8.07 → neighbour mean 6.85, Stability 0.85 ✅
  - `g7_232` strangle_offset_d0 Calmar 8.53 → neighbour mean 5.30, Stability 0.62 ❌ discarded (lucky spike)
  - `g7_299` straddle_d456 Calmar 13.43 → neighbour mean 7.91, Stability 0.59 ❌ discarded (lucky spike)
  - `g7_182` straddle_d456 Calmar 8.23 → neighbour mean 5.66, Stability 0.69 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g7_187` straddle_d456: valid Calmar 0.45 PF 1.07 net ₹1,428; holdout not touched → rejected (train hard-gate: tail: worst day ₹3419 > 1.5% of capital; validation Calmar 0.45/PF 1.07)
- Phase D hypotheses:
  - 5/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - Leader worst days: 20250321(dte6,₹-2,755,2SL,TIME), 20241220(dte6,₹-2,502,2SL,TIME), 20240105(dte6,₹-2,432,2SL,TIME), 20240301(dte6,₹-2,069,2SL,TIME), 20250228(dte6,₹-1,044,0SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

## Generation 8  (336 train runs in 0.5s engine time, 2.3s wall)

- Hard-gate passes on train: **1/336**
- Top `g8_311` straddle_d456 (score 71.91): net ₹78,419 | DD ₹2,874 | Calmar 19.20 | PF 5.47 | win 61.5% | exp ₹1508 | worst ₹-2,755 | losing-months 22% | UW 14d
  - gate failures: losing months 22.2% > 15%
- Top `g8_186` straddle_d456 (score 71.33): net ₹79,086 | DD ₹2,654 | Calmar 20.98 | PF 5.86 | win 57.7% | exp ₹1521 | worst ₹-2,200 | losing-months 28% | UW 14d
  - gate failures: losing months 27.8% > 15%
- Top `g8_224` straddle_d456 (score 52.64): net ₹78,182 | DD ₹3,190 | Calmar 17.25 | PF 5.77 | win 55.8% | exp ₹1504 | worst ₹-2,200 | losing-months 28% | UW 14d
  - gate failures: losing months 27.8% > 15%
- Phase B stability audit:
  - `g8_311` straddle_d456 Calmar 19.20 → neighbour mean 9.05, Stability 0.47 ❌ discarded (lucky spike)
  - `g8_186` straddle_d456 Calmar 20.98 → neighbour mean 9.16, Stability 0.44 ❌ discarded (lucky spike)
  - `g8_224` straddle_d456 Calmar 17.25 → neighbour mean 8.51, Stability 0.49 ❌ discarded (lucky spike)
  - `g8_225` straddle_d456 Calmar 9.85 → neighbour mean 5.76, Stability 0.59 ❌ discarded (lucky spike)
  - `g8_269` straddle_d456 Calmar 9.85 → neighbour mean 5.57, Stability 0.57 ❌ discarded (lucky spike)
  - `g8_334` straddle_d456 Calmar 9.85 → neighbour mean 5.57, Stability 0.57 ❌ discarded (lucky spike)
  - `g8_337` straddle_d456 Calmar 9.85 → neighbour mean 5.57, Stability 0.57 ❌ discarded (lucky spike)
  - `g8_327` straddle_d456 Calmar 9.92 → neighbour mean 5.94, Stability 0.60 ❌ discarded (lucky spike)
  - `g8_164` straddle_d456 Calmar 10.05 → neighbour mean 5.83, Stability 0.58 ❌ discarded (lucky spike)
  - `g8_154` strangle_offset_d0 Calmar 9.70 → neighbour mean 5.12, Stability 0.53 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - (no stable candidates)
- Phase D hypotheses:
  - 5/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - Leader worst days: 20250321(dte6,₹-2,755,2SL,TIME), 20241220(dte6,₹-2,502,2SL,TIME), 20240105(dte6,₹-2,432,2SL,TIME), 20240301(dte6,₹-2,069,2SL,TIME), 20250228(dte6,₹-1,044,0SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.43, d01=0.47, d12=0.49, d23=1.18, d456=3.40, d0123=0.44

