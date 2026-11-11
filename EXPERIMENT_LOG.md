# EXPERIMENT_LOG — autonomous discovery of NIFTY intraday non-directional selling strategies

Splits (chronological): train (20240101, 20250616), validation (20250617, 20251124), holdout (20251125, 20260324).

Costs: ₹20/order brokerage, STT 0.1% sell, NSE txn 0.03503%, SEBI 0.0001%, stamp 0.003% buy, GST 18%; slippage 0.3% per market fill (min 0.05), +0.5% on stop fills; lot 65 constant; capital ₹2,00,000 per lot.

## Generation 1  (400 train runs in 0.9s engine time, 4.3s wall)

- Hard-gate passes on train: **0/400**
- Top `g1_381` straddle_d0 (score 1.19): net ₹50,221 | DD ₹7,977 | Calmar 4.43 | PF 2.12 | win 67.1% | exp ₹661 | worst ₹-3,419 | losing-months 22% | UW 9d
  - gate failures: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%
- Top `g1_399` strangle_premium_d0 (score 0.61): net ₹40,020 | DD ₹7,592 | Calmar 3.71 | PF 1.58 | win 55.3% | exp ₹527 | worst ₹-2,565 | losing-months 44% | UW 15d
  - gate failures: losing months 44.4% > 15%
- Top `g1_312` strangle_offset_d0 (score 0.61): net ₹32,661 | DD ₹7,852 | Calmar 2.93 | PF 2.10 | win 63.2% | exp ₹430 | worst ₹-3,389 | losing-months 17% | UW 16d
  - gate failures: thin edge: expectancy ₹430 < ₹450; tail: worst day ₹3389 > 1.5% of capital; losing months 16.7% > 15%
- Phase B stability audit:
  - `g1_381` straddle_d0 Calmar 4.43 → neighbour mean 5.02, Stability 1.13 ✅
  - `g1_399` strangle_premium_d0 Calmar 3.71 → neighbour mean 2.61, Stability 0.70 ❌ discarded (lucky spike)
  - `g1_312` strangle_offset_d0 Calmar 2.93 → neighbour mean 2.63, Stability 0.90 ✅
  - `g1_185` strangle_offset_d456 Calmar 3.23 → neighbour mean 2.88, Stability 0.89 ✅
  - `g1_187` strangle_offset_d456 Calmar 2.48 → neighbour mean 1.99, Stability 0.80 ✅
  - `g1_43` straddle_d456 Calmar 2.56 → neighbour mean 2.48, Stability 0.97 ✅
  - `g1_85` strangle_premium_d456 Calmar 2.41 → neighbour mean 1.52, Stability 0.63 ❌ discarded (lucky spike)
  - `g1_134` strangle_offset_d0 Calmar 3.42 → neighbour mean 2.84, Stability 0.83 ✅
  - `g1_335` strangle_premium_d456 Calmar 2.28 → neighbour mean 0.96, Stability 0.42 ❌ discarded (lucky spike)
  - `g1_220` strangle_premium_d456 Calmar 1.40 → neighbour mean 1.33, Stability 0.95 ✅
- Phase C walk-forward/holdout:
  - `g1_381` straddle_d0: valid Calmar 2.72 PF 1.55 net ₹6,526; holdout not touched → rejected (train hard-gate: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 2.72/PF 1.55)
  - `g1_312` strangle_offset_d0: valid Calmar 1.61 PF 1.47 net ₹3,020; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹430 < ₹450; tail: worst day ₹3389 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar 1.61/PF 1.47)
  - `g1_185` strangle_offset_d456: valid Calmar 0.05 PF 1.01 net ₹188; holdout not touched → rejected (train hard-gate: tail: worst day ₹3179 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar 0.05/PF 1.01)
  - `g1_187` strangle_offset_d456: valid Calmar -0.76 PF 0.85 net ₹-2,137; holdout not touched → rejected (train hard-gate: tail: worst day ₹3145 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.76/PF 0.85)
  - `g1_43` straddle_d456: valid Calmar 1.18 PF 1.24 net ₹2,640; holdout not touched → rejected (train hard-gate: tail: worst day ₹5993 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar 1.18/PF 1.24)
  - `g1_134` strangle_offset_d0: valid Calmar -2.19 PF 0.39 net ₹-5,653; holdout not touched → rejected (train hard-gate: losing months 50.0% > 15%; underwater 30 active days > 25; validation Calmar -2.19/PF 0.39)
  - `g1_220` strangle_premium_d456: valid Calmar -0.16 PF 0.97 net ₹-327; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹166 < ₹450; tail: worst day ₹3645 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.16/PF 0.97)
- Phase D hypotheses:
  - 9/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 4/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 10/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20240808(dte0,₹-3,419,1SL,MAXLOSS), 20240718(dte0,₹-3,298,3SL,MAXLOSS), 20250515(dte0,₹-3,031,2SL,MAXLOSS), 20240912(dte0,₹-2,756,3SL,MAXLOSS), 20240926(dte0,₹-2,692,2SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[0, 1]
- Next-gen bucket weights: d0=1.59, d1=0.40, d01=0.47, d12=0.41, d23=0.44, d456=0.89, d0123=0.43

## Generation 2  (375 train runs in 0.7s engine time, 4.2s wall)

- Hard-gate passes on train: **0/375**
- Top `g2_381` straddle_d456 (score 5.46): net ₹25,980 | DD ₹2,973 | Calmar 6.15 | PF 2.93 | win 82.5% | exp ₹412 | worst ₹-2,815 | losing-months 28% | UW 13d
  - gate failures: thin edge: expectancy ₹412 < ₹450; losing months 27.8% > 15%
- Top `g2_230` straddle_d456 (score 4.64): net ₹86,421 | DD ₹6,200 | Calmar 9.81 | PF 4.49 | win 51.9% | exp ₹1662 | worst ₹-5,886 | losing-months 33% | UW 12d
  - gate failures: tail: worst day ₹5886 > 1.5% of capital; losing months 33.3% > 15%
- Top `g2_234` straddle_d0 (score 4.54): net ₹68,185 | DD ₹6,401 | Calmar 7.50 | PF 2.86 | win 68.4% | exp ₹897 | worst ₹-3,286 | losing-months 22% | UW 8d
  - gate failures: tail: worst day ₹3286 > 1.5% of capital; losing months 22.2% > 15%
- Phase B stability audit:
  - `g2_381` straddle_d456 Calmar 6.15 → neighbour mean 2.99, Stability 0.49 ❌ discarded (lucky spike)
  - `g2_230` straddle_d456 Calmar 9.81 → neighbour mean 6.75, Stability 0.69 ❌ discarded (lucky spike)
  - `g2_234` straddle_d0 Calmar 7.50 → neighbour mean 4.11, Stability 0.55 ❌ discarded (lucky spike)
  - `g2_302` strangle_offset_d456 Calmar 4.31 → neighbour mean 2.70, Stability 0.63 ❌ discarded (lucky spike)
  - `g2_208` straddle_d0 Calmar 5.39 → neighbour mean 4.03, Stability 0.75 ❌ discarded (lucky spike)
  - `g2_238` straddle_d456 Calmar 5.35 → neighbour mean 3.80, Stability 0.71 ❌ discarded (lucky spike)
  - `g2_192` straddle_d0 Calmar 4.84 → neighbour mean 4.92, Stability 1.02 ✅
  - `g2_88` strangle_premium_d0 Calmar 3.19 → neighbour mean 2.16, Stability 0.68 ❌ discarded (lucky spike)
  - `g2_369` strangle_offset_d456 Calmar 3.27 → neighbour mean 2.50, Stability 0.76 ✅
  - `g2_307` strangle_offset_d0 Calmar 3.71 → neighbour mean 2.64, Stability 0.71 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g2_192` straddle_d0: valid Calmar 1.18 PF 1.16 net ₹2,269; holdout not touched → rejected (train hard-gate: tail: worst day ₹3419 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 1.18/PF 1.16)
  - `g2_369` strangle_offset_d456: valid Calmar -0.19 PF 0.97 net ₹-420; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%; validation Calmar -0.19/PF 0.97)
- Phase D hypotheses:
  - 7/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - Leader worst days: 20240119(dte6,₹-2,815,4SL,FLAT), 20240412(dte6,₹-2,218,4SL,FLAT), 20240705(dte6,₹-2,205,2SL,FLAT), 20240823(dte6,₹-1,977,2SL,FLAT), 20250523(dte6,₹-1,544,2SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[1, 2], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49

## Generation 3  (335 train runs in 0.5s engine time, 4.1s wall)

- Hard-gate passes on train: **0/335**
- Top `g3_180` strangle_premium_d0 (score 13.14): net ₹52,199 | DD ₹3,343 | Calmar 10.99 | PF 2.81 | win 75.0% | exp ₹687 | worst ₹-2,243 | losing-months 33% | UW 7d
  - gate failures: losing months 33.3% > 15%
- Top `g3_133` straddle_d456 (score 8.43): net ₹49,591 | DD ₹3,970 | Calmar 8.79 | PF 3.06 | win 66.7% | exp ₹787 | worst ₹-3,863 | losing-months 22% | UW 9d
  - gate failures: tail: worst day ₹3863 > 1.5% of capital; losing months 22.2% > 15%
- Top `g3_316` straddle_d0 (score 7.08): net ₹68,418 | DD ₹7,320 | Calmar 6.58 | PF 2.71 | win 65.8% | exp ₹900 | worst ₹-3,423 | losing-months 11% | UW 9d
  - gate failures: tail: worst day ₹3423 > 1.5% of capital
- Phase B stability audit:
  - `g3_180` strangle_premium_d0 Calmar 10.99 → neighbour mean 6.20, Stability 0.56 ❌ discarded (lucky spike)
  - `g3_133` straddle_d456 Calmar 8.79 → neighbour mean 5.12, Stability 0.58 ❌ discarded (lucky spike)
  - `g3_316` straddle_d0 Calmar 6.58 → neighbour mean 6.02, Stability 0.92 ✅
  - `g3_305` strangle_premium_d0 Calmar 7.86 → neighbour mean 5.77, Stability 0.73 ❌ discarded (lucky spike)
  - `g3_315` strangle_offset_d0 Calmar 6.89 → neighbour mean 2.96, Stability 0.43 ❌ discarded (lucky spike)
  - `g3_288` strangle_premium_d0 Calmar 5.50 → neighbour mean 6.26, Stability 1.14 ✅
  - `g3_194` straddle_d456 Calmar 5.66 → neighbour mean 4.14, Stability 0.73 ❌ discarded (lucky spike)
  - `g3_268` straddle_d456 Calmar 6.24 → neighbour mean 4.75, Stability 0.76 ✅
  - `g3_252` straddle_d0 Calmar 5.78 → neighbour mean 4.60, Stability 0.80 ✅
  - `g3_200` straddle_d0 Calmar 6.01 → neighbour mean 4.67, Stability 0.78 ✅
- Phase C walk-forward/holdout:
  - `g3_316` straddle_d0: valid Calmar 2.45 PF 1.44 net ₹4,455; holdout not touched → rejected (train hard-gate: tail: worst day ₹3423 > 1.5% of capital; validation Calmar 2.45/PF 1.44)
  - `g3_288` strangle_premium_d0: valid Calmar 5.22 PF 1.76 net ₹9,208; holdout not touched → rejected (train hard-gate: losing months 16.7% > 15%)
  - `g3_268` straddle_d456: valid Calmar 3.98 PF 1.61 net ₹4,891; holdout not touched → rejected (train hard-gate: tail: worst day ₹4928 > 1.5% of capital; losing months 33.3% > 15%)
  - `g3_252` straddle_d0: valid Calmar -0.03 PF 0.99 net ₹-80; holdout not touched → rejected (train hard-gate: tail: worst day ₹3494 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -0.03/PF 0.99)
  - `g3_200` straddle_d0: valid Calmar -0.74 PF 0.89 net ₹-1,551; holdout not touched → rejected (train hard-gate: tail: worst day ₹3423 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -0.74/PF 0.89)
- Phase D hypotheses:
  - 10/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 9/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - Leader worst days: 20240321(dte0,₹-2,243,2SL,FLAT), 20240606(dte0,₹-2,118,2SL,FLAT), 20250320(dte0,₹-1,884,2SL,FLAT), 20250213(dte0,₹-1,824,2SL,FLAT), 20240829(dte0,₹-1,809,2SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49

## Generation 4  (359 train runs in 0.5s engine time, 4.0s wall)

- Hard-gate passes on train: **0/359**
- Top `g4_239` strangle_premium_d0 (score 10.05): net ₹52,698 | DD ₹4,607 | Calmar 8.05 | PF 2.49 | win 65.8% | exp ₹693 | worst ₹-2,198 | losing-months 17% | UW 9d
  - gate failures: losing months 16.7% > 15%
- Top `g4_204` straddle_d456 (score 8.39): net ₹52,094 | DD ₹5,241 | Calmar 7.00 | PF 3.33 | win 69.2% | exp ₹1002 | worst ₹-4,631 | losing-months 17% | UW 10d
  - gate failures: tail: worst day ₹4631 > 1.5% of capital; losing months 16.7% > 15%
- Top `g4_351` strangle_premium_d0 (score 8.18): net ₹51,707 | DD ₹5,049 | Calmar 7.21 | PF 2.33 | win 65.8% | exp ₹680 | worst ₹-2,122 | losing-months 17% | UW 6d
  - gate failures: losing months 16.7% > 15%
- Phase B stability audit:
  - `g4_239` strangle_premium_d0 Calmar 8.05 → neighbour mean 5.85, Stability 0.73 ❌ discarded (lucky spike)
  - `g4_204` straddle_d456 Calmar 7.00 → neighbour mean 5.14, Stability 0.73 ❌ discarded (lucky spike)
  - `g4_351` strangle_premium_d0 Calmar 7.21 → neighbour mean 6.36, Stability 0.88 ✅
  - `g4_297` strangle_premium_d0 Calmar 7.35 → neighbour mean 4.78, Stability 0.65 ❌ discarded (lucky spike)
  - `g4_298` straddle_d0 Calmar 6.58 → neighbour mean 6.02, Stability 0.92 ✅
  - `g4_366` straddle_d456 Calmar 6.54 → neighbour mean 4.81, Stability 0.74 ❌ discarded (lucky spike)
  - `g4_345` straddle_d456 Calmar 9.19 → neighbour mean 7.02, Stability 0.76 ✅
  - `g4_212` straddle_d0 Calmar 5.40 → neighbour mean 5.97, Stability 1.11 ✅
  - `g4_327` strangle_offset_d456 Calmar 4.58 → neighbour mean 2.58, Stability 0.56 ❌ discarded (lucky spike)
  - `g4_197` straddle_d0 Calmar 4.74 → neighbour mean 5.05, Stability 1.07 ✅
- Phase C walk-forward/holdout:
  - `g4_351` strangle_premium_d0: valid Calmar 11.00 PF 2.97 net ₹17,074; holdout not touched → rejected (train hard-gate: losing months 16.7% > 15%)
  - `g4_298` straddle_d0: valid Calmar 2.45 PF 1.44 net ₹4,455; holdout not touched → rejected (train hard-gate: tail: worst day ₹3423 > 1.5% of capital; validation Calmar 2.45/PF 1.44)
  - `g4_345` straddle_d456: valid Calmar -0.47 PF 0.92 net ₹-2,308; holdout not touched → rejected (train hard-gate: tail: worst day ₹5773 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.47/PF 0.92)
  - `g4_212` straddle_d0: valid Calmar 2.15 PF 1.23 net ₹2,791; holdout not touched → rejected (train hard-gate: tail: worst day ₹3393 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 2.15/PF 1.23)
  - `g4_197` straddle_d0: valid Calmar 1.56 PF 1.30 net ₹3,685; holdout not touched → rejected (train hard-gate: tail: worst day ₹6560 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar 1.56/PF 1.30)
- Phase D hypotheses:
  - 10/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 7/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - Leader worst days: 20240321(dte0,₹-2,198,2SL,FLAT), 20241003(dte0,₹-1,971,2SL,FLAT), 20240606(dte0,₹-1,813,2SL,FLAT), 20250320(dte0,₹-1,796,2SL,FLAT), 20250213(dte0,₹-1,727,2SL,FLAT)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49

## Generation 5  (341 train runs in 0.6s engine time, 4.2s wall)

- Hard-gate passes on train: **3/341**
- Top `g5_226` strangle_premium_d0 (score 37.87): net ₹60,286 | DD ₹4,480 | Calmar 9.47 | PF 2.59 | win 68.4% | exp ₹793 | worst ₹-2,202 | losing-months 11% | UW 8d
- Top `g5_260` strangle_premium_d0 (score 28.74): net ₹63,190 | DD ₹6,263 | Calmar 7.10 | PF 2.43 | win 63.2% | exp ₹831 | worst ₹-2,127 | losing-months 6% | UW 7d
- Top `g5_282` strangle_premium_d0 (score 28.74): net ₹63,190 | DD ₹6,263 | Calmar 7.10 | PF 2.43 | win 63.2% | exp ₹831 | worst ₹-2,127 | losing-months 6% | UW 7d
- Phase B stability audit:
  - `g5_226` strangle_premium_d0 Calmar 9.47 → neighbour mean 5.62, Stability 0.59 ❌ discarded (lucky spike)
  - `g5_260` strangle_premium_d0 Calmar 7.10 → neighbour mean 6.18, Stability 0.87 ✅
  - `g5_282` strangle_premium_d0 Calmar 7.10 → neighbour mean 6.18, Stability 0.87 ✅
  - `g5_304` straddle_d456 Calmar 12.45 → neighbour mean 8.83, Stability 0.71 ❌ discarded (lucky spike)
  - `g5_199` straddle_d456 Calmar 10.81 → neighbour mean 8.52, Stability 0.79 ✅
  - `g5_342` straddle_d456 Calmar 9.50 → neighbour mean 7.22, Stability 0.76 ✅
  - `g5_341` straddle_d0 Calmar 5.84 → neighbour mean 6.09, Stability 1.04 ✅
  - `g5_339` straddle_d0 Calmar 7.11 → neighbour mean 5.70, Stability 0.80 ✅
  - `g5_262` straddle_d0 Calmar 5.58 → neighbour mean 2.87, Stability 0.51 ❌ discarded (lucky spike)
  - `g5_166` strangle_offset_d456 Calmar 5.30 → neighbour mean 3.26, Stability 0.62 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g5_260` strangle_premium_d0: valid Calmar 2.39 PF 1.30 net ₹4,011; holdout not touched → rejected (validation Calmar 2.39/PF 1.30)
  - `g5_282` strangle_premium_d0: valid Calmar 2.39 PF 1.30 net ₹4,011; holdout not touched → rejected (validation Calmar 2.39/PF 1.30)
  - `g5_199` straddle_d456: valid Calmar -1.97 PF 0.71 net ₹-10,336; holdout not touched → rejected (train hard-gate: tail: worst day ₹4302 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.97/PF 0.71)
  - `g5_342` straddle_d456: valid Calmar -0.51 PF 0.91 net ₹-2,608; holdout not touched → rejected (train hard-gate: tail: worst day ₹5773 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.51/PF 0.91)
  - `g5_341` straddle_d0: valid Calmar 0.17 PF 1.02 net ₹331; holdout not touched → rejected (train hard-gate: tail: worst day ₹6204 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar 0.17/PF 1.02)
  - `g5_339` straddle_d0: valid Calmar 0.65 PF 1.12 net ₹1,403; holdout not touched → rejected (train hard-gate: tail: worst day ₹3423 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 0.65/PF 1.12)
- Phase D hypotheses:
  - 10/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 9/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - Leader worst days: 20241003(dte0,₹-2,202,2SL,FLAT), 20240321(dte0,₹-2,195,2SL,FLAT), 20240627(dte0,₹-2,095,2SL,FLAT), 20240606(dte0,₹-1,969,2SL,FLAT), 20240125(dte0,₹-1,939,2SL,FLAT)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49

## Generation 6  (309 train runs in 0.6s engine time, 4.2s wall)

- Hard-gate passes on train: **1/309**
- Top `g6_190` strangle_premium_d0 (score 61.32): net ₹80,448 | DD ₹4,748 | Calmar 11.93 | PF 3.36 | win 64.5% | exp ₹1059 | worst ₹-1,536 | losing-months 6% | UW 7d
- Top `g6_326` strangle_premium_d0 (score 11.53): net ₹81,169 | DD ₹5,562 | Calmar 10.27 | PF 2.80 | win 64.5% | exp ₹1068 | worst ₹-2,616 | losing-months 17% | UW 7d
  - gate failures: losing months 16.7% > 15%
- Top `g6_290` straddle_d456 (score 10.17): net ₹86,863 | DD ₹4,912 | Calmar 12.45 | PF 4.74 | win 50.0% | exp ₹1670 | worst ₹-4,518 | losing-months 28% | UW 8d
  - gate failures: tail: worst day ₹4518 > 1.5% of capital; losing months 27.8% > 15%
- Phase B stability audit:
  - `g6_190` strangle_premium_d0 Calmar 11.93 → neighbour mean 7.78, Stability 0.65 ❌ discarded (lucky spike)
  - `g6_326` strangle_premium_d0 Calmar 10.27 → neighbour mean 6.86, Stability 0.67 ❌ discarded (lucky spike)
  - `g6_290` straddle_d456 Calmar 12.45 → neighbour mean 8.83, Stability 0.71 ❌ discarded (lucky spike)
  - `g6_263` straddle_d456 Calmar 10.81 → neighbour mean 8.52, Stability 0.79 ✅
  - `g6_317` straddle_d456 Calmar 10.81 → neighbour mean 8.52, Stability 0.79 ✅
  - `g6_288` strangle_premium_d0 Calmar 8.74 → neighbour mean 5.99, Stability 0.69 ❌ discarded (lucky spike)
  - `g6_192` straddle_d0 Calmar 6.24 → neighbour mean 6.13, Stability 0.98 ✅
  - `g6_296` straddle_d0 Calmar 8.66 → neighbour mean 5.40, Stability 0.62 ❌ discarded (lucky spike)
  - `g6_147` straddle_d0 Calmar 7.00 → neighbour mean 5.47, Stability 0.78 ✅
  - `g6_271` strangle_offset_d456 Calmar 3.39 → neighbour mean 2.46, Stability 0.72 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g6_263` straddle_d456: valid Calmar -1.97 PF 0.71 net ₹-10,336; holdout not touched → rejected (train hard-gate: tail: worst day ₹4302 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.97/PF 0.71)
  - `g6_317` straddle_d456: valid Calmar -1.97 PF 0.71 net ₹-10,336; holdout not touched → rejected (train hard-gate: tail: worst day ₹4302 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.97/PF 0.71)
  - `g6_192` straddle_d0: valid Calmar -0.89 PF 0.88 net ₹-1,760; holdout not touched → rejected (train hard-gate: tail: worst day ₹3423 > 1.5% of capital; validation Calmar -0.89/PF 0.88)
  - `g6_147` straddle_d0: valid Calmar 0.33 PF 1.05 net ₹803; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%; validation Calmar 0.33/PF 1.05)
- Phase D hypotheses:
  - 10/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 9/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - Leader worst days: 20240704(dte0,₹-1,536,2SL,FLAT), 20240627(dte0,₹-1,531,2SL,FLAT), 20240808(dte0,₹-1,528,2SL,FLAT), 20241003(dte0,₹-1,518,2SL,FLAT), 20240229(dte0,₹-1,472,2SL,FLAT)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49

## Generation 7  (314 train runs in 0.6s engine time, 4.9s wall)

- Hard-gate passes on train: **7/314**
- Top `g7_276` strangle_premium_d0 (score 39.83): net ₹66,356 | DD ₹4,658 | Calmar 10.03 | PF 2.79 | win 61.8% | exp ₹873 | worst ₹-1,556 | losing-months 11% | UW 8d
- Top `g7_278` strangle_premium_d0 (score 35.90): net ₹65,740 | DD ₹5,432 | Calmar 8.52 | PF 2.57 | win 63.2% | exp ₹865 | worst ₹-2,030 | losing-months 6% | UW 7d
- Top `g7_234` strangle_premium_d0 (score 30.79): net ₹69,655 | DD ₹6,048 | Calmar 8.11 | PF 2.57 | win 63.2% | exp ₹917 | worst ₹-2,127 | losing-months 11% | UW 7d
- Phase B stability audit:
  - `g7_276` strangle_premium_d0 Calmar 10.03 → neighbour mean 7.95, Stability 0.79 ✅
  - `g7_278` strangle_premium_d0 Calmar 8.52 → neighbour mean 6.81, Stability 0.80 ✅
  - `g7_234` strangle_premium_d0 Calmar 8.11 → neighbour mean 7.08, Stability 0.87 ✅
  - `g7_326` straddle_d456 Calmar 12.71 → neighbour mean 7.65, Stability 0.60 ❌ discarded (lucky spike)
  - `g7_253` straddle_d456 Calmar 10.05 → neighbour mean 6.70, Stability 0.67 ❌ discarded (lucky spike)
  - `g7_189` straddle_d456 Calmar 12.45 → neighbour mean 8.83, Stability 0.71 ❌ discarded (lucky spike)
  - `g7_202` straddle_d0 Calmar 7.00 → neighbour mean 5.47, Stability 0.78 ✅
  - `g7_303` straddle_d0 Calmar 7.00 → neighbour mean 5.47, Stability 0.78 ✅
  - `g7_311` straddle_d0 Calmar 7.00 → neighbour mean 5.47, Stability 0.78 ✅
  - `g7_149` strangle_offset_d456 Calmar 4.81 → neighbour mean 2.85, Stability 0.59 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g7_276` strangle_premium_d0: valid Calmar 5.97 PF 1.80 net ₹8,941; holdout Calmar 5.05 PF 1.92 net ₹10,088 → **PROMOTED**
  - `g7_278` strangle_premium_d0: valid Calmar 0.59 PF 1.09 net ₹1,222; holdout not touched → rejected (validation Calmar 0.59/PF 1.09; correlated with an existing winner; duplicate of an existing winner's family/bucket)
  - `g7_234` strangle_premium_d0: valid Calmar 3.81 PF 1.48 net ₹6,383; holdout Calmar 2.16 PF 1.35 net ₹4,083 → rejected (holdout Calmar 2.16/PF 1.35; correlated with an existing winner; duplicate of an existing winner's family/bucket)
  - `g7_202` straddle_d0: valid Calmar 0.33 PF 1.05 net ₹803; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%; validation Calmar 0.33/PF 1.05; correlated with an existing winner)
  - `g7_303` straddle_d0: valid Calmar 0.33 PF 1.05 net ₹803; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%; validation Calmar 0.33/PF 1.05; correlated with an existing winner)
  - `g7_311` straddle_d0: valid Calmar 0.33 PF 1.05 net ₹803; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%; validation Calmar 0.33/PF 1.05; correlated with an existing winner)
- Phase D hypotheses:
  - 10/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 9/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 10/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20240627(dte0,₹-1,556,2SL,MAXLOSS), 20241003(dte0,₹-1,518,2SL,MAXLOSS), 20240125(dte0,₹-1,487,2SL,MAXLOSS), 20240229(dte0,₹-1,477,2SL,MAXLOSS), 20241205(dte0,₹-1,471,2SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49

## Generation 8  (314 train runs in 0.5s engine time, 4.2s wall)

- Hard-gate passes on train: **9/314**
- Top `g8_319` strangle_premium_d0 (score 59.25): net ₹79,997 | DD ₹4,753 | Calmar 11.85 | PF 3.31 | win 64.5% | exp ₹1053 | worst ₹-1,563 | losing-months 6% | UW 7d
- Top `g8_301` strangle_premium_d0 (score 57.44): net ₹79,747 | DD ₹4,850 | Calmar 11.57 | PF 3.29 | win 64.5% | exp ₹1049 | worst ₹-1,563 | losing-months 6% | UW 7d
- Top `g8_158` strangle_premium_d0 (score 51.14): net ₹76,062 | DD ₹4,480 | Calmar 11.95 | PF 2.98 | win 60.5% | exp ₹1001 | worst ₹-1,556 | losing-months 6% | UW 7d
- Phase B stability audit:
  - `g8_319` strangle_premium_d0 Calmar 11.85 → neighbour mean 7.90, Stability 0.67 ❌ discarded (lucky spike)
  - `g8_301` strangle_premium_d0 Calmar 11.57 → neighbour mean 7.83, Stability 0.68 ❌ discarded (lucky spike)
  - `g8_158` strangle_premium_d0 Calmar 11.95 → neighbour mean 8.01, Stability 0.67 ❌ discarded (lucky spike)
  - `g8_286` straddle_d456 Calmar 12.71 → neighbour mean 7.65, Stability 0.60 ❌ discarded (lucky spike)
  - `g8_297` straddle_d456 Calmar 13.04 → neighbour mean 10.14, Stability 0.78 ✅
  - `g8_292` straddle_d456 Calmar 9.17 → neighbour mean 5.50, Stability 0.60 ❌ discarded (lucky spike)
  - `g8_267` straddle_d0 Calmar 8.89 → neighbour mean 5.32, Stability 0.60 ❌ discarded (lucky spike)
  - `g8_183` straddle_d0 Calmar 8.66 → neighbour mean 5.40, Stability 0.62 ❌ discarded (lucky spike)
  - `g8_205` straddle_d0 Calmar 8.66 → neighbour mean 5.40, Stability 0.62 ❌ discarded (lucky spike)
  - `g8_223` strangle_offset_d456 Calmar 5.33 → neighbour mean 3.22, Stability 0.61 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g8_297` straddle_d456: valid Calmar -0.93 PF 0.82 net ₹-5,542; holdout not touched → rejected (train hard-gate: tail: worst day ₹4303 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar -0.93/PF 0.82)
- Phase D hypotheses:
  - 9/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 8/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 10/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20240627(dte0,₹-1,563,2SL,MAXLOSS), 20241003(dte0,₹-1,553,2SL,MAXLOSS), 20240229(dte0,₹-1,504,2SL,MAXLOSS), 20240620(dte0,₹-1,486,2SL,MAXLOSS), 20240307(dte0,₹-1,482,2SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[0, 1], straddle/DTE[0, 1, 2, 3], straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[0, 1], strangle_offset/DTE[0, 1, 2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[2, 3], strangle_premium/DTE[0, 1], strangle_premium/DTE[0, 1, 2, 3], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d0=3.40, d1=0.40, d01=0.48, d12=0.44, d23=0.50, d456=3.40, d0123=0.49


# Run v3 (seed 11, pop 400)

Splits (chronological): train (20240101, 20250616), validation (20250617, 20251124), holdout (20251125, 20260324).

Costs: ₹20/order brokerage, STT 0.1% sell, NSE txn 0.03503%, SEBI 0.0001%, stamp 0.003% buy, GST 18%; slippage 0.3% per market fill (min 0.05), +0.5% on stop fills; lot 65 constant; capital ₹2,00,000 per lot.

## Generation 1  (400 train runs in 0.8s engine time, 4.5s wall)

- Hard-gate passes on train: **0/400**
- Top `g1_11` straddle_d456 (score 0.86): net ₹37,417 | DD ₹6,920 | Calmar 3.81 | PF 1.86 | win 65.4% | exp ₹720 | worst ₹-4,972 | losing-months 33% | UW 8d
  - gate failures: tail: worst day ₹4972 > 1.5% of capital; losing months 33.3% > 15%
- Top `g1_125` strangle_offset_d23 (score 0.72): net ₹71,792 | DD ₹11,256 | Calmar 4.49 | PF 1.73 | win 63.6% | exp ₹502 | worst ₹-8,704 | losing-months 28% | UW 29d
  - gate failures: tail: worst day ₹8704 > 1.5% of capital; losing months 27.8% > 15%; underwater 29 active days > 25
- Top `g1_239` strangle_offset_d456 (score 0.46): net ₹27,130 | DD ₹10,222 | Calmar 1.87 | PF 1.87 | win 61.9% | exp ₹431 | worst ₹-3,684 | losing-months 22% | UW 17d
  - gate failures: thin edge: expectancy ₹431 < ₹450; tail: worst day ₹3684 > 1.5% of capital; losing months 22.2% > 15%
- Phase B stability audit:
  - `g1_11` straddle_d456 Calmar 3.81 → neighbour mean 2.91, Stability 0.76 ✅
  - `g1_125` strangle_offset_d23 Calmar 4.49 → neighbour mean 2.88, Stability 0.64 ❌ discarded (lucky spike)
  - `g1_239` strangle_offset_d456 Calmar 1.87 → neighbour mean 2.00, Stability 1.07 ✅
  - `g1_262` strangle_premium_d456 Calmar 2.69 → neighbour mean 2.32, Stability 0.86 ✅
  - `g1_330` strangle_premium_d456 Calmar 2.72 → neighbour mean 2.55, Stability 0.94 ✅
  - `g1_22` strangle_offset_d456 Calmar 2.41 → neighbour mean 2.54, Stability 1.05 ✅
  - `g1_49` straddle_d456 Calmar 2.13 → neighbour mean 1.78, Stability 0.84 ✅
  - `g1_28` strangle_premium_d456 Calmar 2.08 → neighbour mean 1.81, Stability 0.87 ✅
  - `g1_160` strangle_offset_d456 Calmar 1.38 → neighbour mean 1.62, Stability 1.17 ✅
  - `g1_154` strangle_offset_d23 Calmar 2.02 → neighbour mean 2.10, Stability 1.04 ✅
- Phase C walk-forward/holdout:
  - `g1_11` straddle_d456: valid Calmar 0.08 PF 1.01 net ₹398; holdout not touched → rejected (train hard-gate: tail: worst day ₹4972 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar 0.08/PF 1.01)
  - `g1_239` strangle_offset_d456: valid Calmar -1.69 PF 0.47 net ₹-8,266; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹431 < ₹450; tail: worst day ₹3684 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.69/PF 0.47)
  - `g1_262` strangle_premium_d456: valid Calmar 3.31 PF 1.42 net ₹5,677; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹284 < ₹450; losing months 27.8% > 15%; validation Calmar 3.31/PF 1.42)
  - `g1_330` strangle_premium_d456: valid Calmar 12.63 PF 2.11 net ₹15,094; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹376 < ₹450; losing months 33.3% > 15%)
  - `g1_22` strangle_offset_d456: valid Calmar -0.24 PF 0.93 net ₹-417; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹335 < ₹450; tail: worst day ₹3644 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.24/PF 0.93)
  - `g1_49` straddle_d456: valid Calmar 10.76 PF 2.61 net ₹22,745; holdout not touched → rejected (train hard-gate: tail: worst day ₹4018 > 1.5% of capital; losing months 27.8% > 15%)
  - `g1_28` strangle_premium_d456: valid Calmar -0.68 PF 0.88 net ₹-2,878; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹299 < ₹450; losing months 27.8% > 15%; validation Calmar -0.68/PF 0.88)
  - `g1_160` strangle_offset_d456: valid Calmar -0.59 PF 0.91 net ₹-1,013; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹310 < ₹450; losing months 33.3% > 15%; validation Calmar -0.59/PF 0.91)
  - `g1_154` strangle_offset_d23: valid Calmar 4.44 PF 1.73 net ₹7,171; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹263 < ₹450; tail: worst day ₹4774 > 1.5% of capital; losing months 27.8% > 15%; underwater 28 active days > 25)
- Phase D hypotheses:
  - 5/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 10/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241220(dte6,₹-4,972,0SL,MAXLOSS), 20250606(dte6,₹-3,927,0SL,MAXLOSS), 20250509(dte6,₹-3,696,0SL,MAXLOSS), 20250117(dte6,₹-3,588,1SL,MAXLOSS), 20240712(dte6,₹-3,526,0SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=1.12, d456=1.26

## Generation 2  (146 train runs in 0.3s engine time, 3.8s wall)

- Hard-gate passes on train: **0/146**
- Top `g2_75` straddle_d456 (score 1.34): net ₹27,523 | DD ₹5,177 | Calmar 3.74 | PF 2.10 | win 78.6% | exp ₹393 | worst ₹-3,783 | losing-months 22% | UW 14d
  - gate failures: thin edge: expectancy ₹393 < ₹450; tail: worst day ₹3783 > 1.5% of capital; losing months 22.2% > 15%
- Top `g2_137` straddle_d456 (score 1.16): net ₹40,446 | DD ₹6,789 | Calmar 4.19 | PF 2.13 | win 73.1% | exp ₹778 | worst ₹-3,454 | losing-months 22% | UW 17d
  - gate failures: tail: worst day ₹3454 > 1.5% of capital; losing months 22.2% > 15%
- Top `g2_83` straddle_d456 (score 0.86): net ₹37,417 | DD ₹6,920 | Calmar 3.81 | PF 1.86 | win 65.4% | exp ₹720 | worst ₹-4,972 | losing-months 33% | UW 8d
  - gate failures: tail: worst day ₹4972 > 1.5% of capital; losing months 33.3% > 15%
- Phase B stability audit:
  - `g2_75` straddle_d456 Calmar 3.74 → neighbour mean 2.18, Stability 0.58 ❌ discarded (lucky spike)
  - `g2_137` straddle_d456 Calmar 4.19 → neighbour mean 3.80, Stability 0.91 ✅
  - `g2_83` straddle_d456 Calmar 3.81 → neighbour mean 2.91, Stability 0.76 ✅
  - `g2_104` strangle_offset_d456 Calmar 3.49 → neighbour mean 3.14, Stability 0.90 ✅
  - `g2_80` strangle_offset_d456 Calmar 1.93 → neighbour mean 1.94, Stability 1.00 ✅
  - `g2_78` strangle_offset_d23 Calmar 3.21 → neighbour mean 2.55, Stability 0.79 ✅
  - `g2_109` strangle_offset_d23 Calmar 2.82 → neighbour mean 2.36, Stability 0.84 ✅
  - `g2_131` strangle_offset_d23 Calmar 1.94 → neighbour mean 1.81, Stability 0.93 ✅
  - `g2_92` straddle_d23 Calmar 1.29 → neighbour mean 1.17, Stability 0.91 ✅
  - `g2_103` straddle_d23 Calmar 1.29 → neighbour mean 1.17, Stability 0.91 ✅
- Phase C walk-forward/holdout:
  - `g2_137` straddle_d456: valid Calmar -0.43 PF 0.90 net ₹-2,150; holdout not touched → rejected (train hard-gate: tail: worst day ₹3454 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -0.43/PF 0.90)
  - `g2_83` straddle_d456: valid Calmar 0.08 PF 1.01 net ₹398; holdout not touched → rejected (train hard-gate: tail: worst day ₹4972 > 1.5% of capital; losing months 33.3% > 15%; validation Calmar 0.08/PF 1.01)
  - `g2_104` strangle_offset_d456: valid Calmar -1.71 PF 0.40 net ₹-13,344; holdout not touched → rejected (train hard-gate: tail: worst day ₹5951 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -1.71/PF 0.40)
  - `g2_80` strangle_offset_d456: valid Calmar -1.81 PF 0.40 net ₹-9,524; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹406 < ₹450; tail: worst day ₹3565 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.81/PF 0.40)
  - `g2_78` strangle_offset_d23: valid Calmar 3.69 PF 1.62 net ₹5,666; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹256 < ₹450; tail: worst day ₹3852 > 1.5% of capital; losing months 33.3% > 15%)
  - `g2_109` strangle_offset_d23: valid Calmar 1.97 PF 1.43 net ₹4,462; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹225 < ₹450; tail: worst day ₹3380 > 1.5% of capital; losing months 38.9% > 15%; underwater 27 active days > 25; validation Calmar 1.97/PF 1.43)
  - `g2_131` strangle_offset_d23: valid Calmar 4.23 PF 1.70 net ₹5,998; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹219 < ₹450; tail: worst day ₹3983 > 1.5% of capital; losing months 22.2% > 15%; underwater 44 active days > 25)
  - `g2_92` straddle_d23: valid Calmar 0.44 PF 1.11 net ₹1,522; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹200 < ₹450; losing months 38.9% > 15%; underwater 86 active days > 25; validation Calmar 0.44/PF 1.11)
  - `g2_103` straddle_d23: valid Calmar 0.44 PF 1.11 net ₹1,522; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹200 < ₹450; losing months 38.9% > 15%; underwater 86 active days > 25; validation Calmar 0.44/PF 1.11)
- Phase D hypotheses:
  - 6/10 worst days were double-SL whipsaws → raising move-SL-to-cost and 1-time re-entry probability.
  - 6/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20250509(dte6,₹-3,784,0SL,MAXLOSS), 20250103(dte6,₹-3,103,2SL,MAXLOSS), 20250124(dte6,₹-3,075,2SL,MAXLOSS), 20240315(dte6,₹-2,846,2SL,MAXLOSS), 20240705(dte6,₹-2,745,2SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=1.12, d456=1.74

## Generation 3  (166 train runs in 0.3s engine time, 3.8s wall)

- Hard-gate passes on train: **0/166**
- Top `g3_154` straddle_d456 (score 4.72): net ₹49,484 | DD ₹6,789 | Calmar 5.13 | PF 2.75 | win 76.9% | exp ₹952 | worst ₹-3,454 | losing-months 11% | UW 10d
  - gate failures: tail: worst day ₹3454 > 1.5% of capital
- Top `g3_103` straddle_d456 (score 4.46): net ₹50,410 | DD ₹5,603 | Calmar 6.33 | PF 3.15 | win 67.3% | exp ₹969 | worst ₹-3,874 | losing-months 33% | UW 8d
  - gate failures: tail: worst day ₹3874 > 1.5% of capital; losing months 33.3% > 15%
- Top `g3_166` straddle_d456 (score 2.92): net ₹50,033 | DD ₹6,524 | Calmar 5.40 | PF 2.57 | win 73.1% | exp ₹962 | worst ₹-3,383 | losing-months 22% | UW 14d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital; losing months 22.2% > 15%
- Phase B stability audit:
  - `g3_154` straddle_d456 Calmar 5.13 → neighbour mean 4.70, Stability 0.92 ✅
  - `g3_103` straddle_d456 Calmar 6.33 → neighbour mean 5.45, Stability 0.86 ✅
  - `g3_166` straddle_d456 Calmar 5.40 → neighbour mean 4.49, Stability 0.83 ✅
  - `g3_129` strangle_premium_d456 Calmar 4.51 → neighbour mean 2.95, Stability 0.65 ❌ discarded (lucky spike)
  - `g3_163` strangle_offset_d23 Calmar 3.56 → neighbour mean 2.55, Stability 0.72 ❌ discarded (lucky spike)
  - `g3_89` strangle_offset_d456 Calmar 2.78 → neighbour mean 1.68, Stability 0.61 ❌ discarded (lucky spike)
  - `g3_143` strangle_offset_d23 Calmar 3.30 → neighbour mean 2.76, Stability 0.83 ✅
  - `g3_147` strangle_offset_d456 Calmar 1.87 → neighbour mean 2.04, Stability 1.09 ✅
  - `g3_122` strangle_offset_d23 Calmar 3.30 → neighbour mean 2.48, Stability 0.75 ✅
  - `g3_117` strangle_offset_d456 Calmar 2.42 → neighbour mean 2.33, Stability 0.96 ✅
- Phase C walk-forward/holdout:
  - `g3_154` straddle_d456: valid Calmar -0.28 PF 0.94 net ₹-1,385; holdout not touched → rejected (train hard-gate: tail: worst day ₹3454 > 1.5% of capital; validation Calmar -0.28/PF 0.94)
  - `g3_103` straddle_d456: valid Calmar 3.59 PF 1.55 net ₹12,141; holdout not touched → rejected (train hard-gate: tail: worst day ₹3874 > 1.5% of capital; losing months 33.3% > 15%)
  - `g3_166` straddle_d456: valid Calmar 2.04 PF 1.37 net ₹6,729; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar 2.04/PF 1.37)
  - `g3_143` strangle_offset_d23: valid Calmar 4.66 PF 2.65 net ₹11,199; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹332 < ₹450; tail: worst day ₹5150 > 1.5% of capital; losing months 27.8% > 15%)
  - `g3_147` strangle_offset_d456: valid Calmar -1.69 PF 0.47 net ₹-8,266; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹431 < ₹450; tail: worst day ₹3684 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.69/PF 0.47)
  - `g3_122` strangle_offset_d23: valid Calmar 3.12 PF 2.02 net ₹8,326; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹286 < ₹450; tail: worst day ₹4298 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar 3.12/PF 2.02)
  - `g3_117` strangle_offset_d456: valid Calmar -1.54 PF 0.58 net ₹-2,904; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹288 < ₹450; tail: worst day ₹3151 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -1.54/PF 0.58)
- Phase D hypotheses:
  - 3/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 7/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20250110(dte6,₹-3,454,1SL,MAXLOSS), 20241220(dte6,₹-3,452,1SL,MAXLOSS), 20240816(dte6,₹-3,389,1SL,MAXLOSS), 20240315(dte6,₹-3,340,1SL,MAXLOSS), 20250117(dte6,₹-3,335,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=1.12, d456=3.40

## Generation 4  (184 train runs in 0.3s engine time, 3.9s wall)

- Hard-gate passes on train: **0/184**
- Top `g4_91` straddle_d456 (score 9.02): net ₹54,488 | DD ₹6,566 | Calmar 5.84 | PF 2.90 | win 75.0% | exp ₹1048 | worst ₹-3,383 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital
- Top `g4_134` straddle_d456 (score 9.02): net ₹54,488 | DD ₹6,566 | Calmar 5.84 | PF 2.90 | win 75.0% | exp ₹1048 | worst ₹-3,383 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital
- Top `g4_174` straddle_d456 (score 9.02): net ₹54,488 | DD ₹6,566 | Calmar 5.84 | PF 2.90 | win 75.0% | exp ₹1048 | worst ₹-3,383 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital
- Phase B stability audit:
  - `g4_91` straddle_d456 Calmar 5.84 → neighbour mean 5.30, Stability 0.91 ✅
  - `g4_134` straddle_d456 Calmar 5.84 → neighbour mean 5.30, Stability 0.91 ✅
  - `g4_174` straddle_d456 Calmar 5.84 → neighbour mean 5.30, Stability 0.91 ✅
  - `g4_131` strangle_offset_d23 Calmar 5.64 → neighbour mean 4.67, Stability 0.83 ✅
  - `g4_178` strangle_offset_d23 Calmar 5.39 → neighbour mean 4.59, Stability 0.85 ✅
  - `g4_99` strangle_offset_d456 Calmar 3.15 → neighbour mean 2.78, Stability 0.88 ✅
  - `g4_105` strangle_offset_d23 Calmar 4.94 → neighbour mean 3.54, Stability 0.72 ❌ discarded (lucky spike)
  - `g4_156` strangle_offset_d456 Calmar 2.04 → neighbour mean 2.16, Stability 1.06 ✅
  - `g4_114` strangle_premium_d456 Calmar 2.60 → neighbour mean 2.25, Stability 0.87 ✅
  - `g4_172` strangle_premium_d456 Calmar 2.67 → neighbour mean 1.77, Stability 0.66 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g4_91` straddle_d456: valid Calmar 2.36 PF 1.52 net ₹8,466; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; validation Calmar 2.36/PF 1.52)
  - `g4_134` straddle_d456: valid Calmar 2.36 PF 1.52 net ₹8,466; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; validation Calmar 2.36/PF 1.52)
  - `g4_174` straddle_d456: valid Calmar 2.36 PF 1.52 net ₹8,466; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; validation Calmar 2.36/PF 1.52)
  - `g4_131` strangle_offset_d23: valid Calmar 20.10 PF 3.96 net ₹11,656; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹421 < ₹450; losing months 27.8% > 15%)
  - `g4_178` strangle_offset_d23: valid Calmar 16.75 PF 3.54 net ₹11,953; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹410 < ₹450; losing months 27.8% > 15%)
  - `g4_99` strangle_offset_d456: valid Calmar -1.52 PF 0.58 net ₹-5,539; holdout not touched → rejected (train hard-gate: tail: worst day ₹3565 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar -1.52/PF 0.58)
  - `g4_156` strangle_offset_d456: valid Calmar -0.24 PF 0.93 net ₹-417; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹383 < ₹450; tail: worst day ₹3644 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -0.24/PF 0.93)
  - `g4_114` strangle_premium_d456: valid Calmar 3.31 PF 1.42 net ₹5,677; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹274 < ₹450; losing months 27.8% > 15%; validation Calmar 3.31/PF 1.42)
- Phase D hypotheses:
  - 6/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241220(dte6,₹-3,383,1SL,MAXLOSS), 20240816(dte6,₹-3,347,1SL,MAXLOSS), 20240802(dte6,₹-3,308,1SL,MAXLOSS), 20250110(dte6,₹-3,294,1SL,MAXLOSS), 20250307(dte6,₹-3,281,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=2.52, d456=3.40

## Generation 5  (180 train runs in 0.4s engine time, 3.9s wall)

- Hard-gate passes on train: **1/180**
- Top `g5_161` straddle_d456 (score 31.65): net ₹54,801 | DD ₹5,702 | Calmar 6.77 | PF 2.93 | win 75.0% | exp ₹1054 | worst ₹-2,955 | losing-months 11% | UW 6d
- Top `g5_106` straddle_d456 (score 9.02): net ₹54,488 | DD ₹6,566 | Calmar 5.84 | PF 2.90 | win 75.0% | exp ₹1048 | worst ₹-3,383 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital
- Top `g5_117` straddle_d456 (score 9.02): net ₹54,488 | DD ₹6,566 | Calmar 5.84 | PF 2.90 | win 75.0% | exp ₹1048 | worst ₹-3,383 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital
- Phase B stability audit:
  - `g5_161` straddle_d456 Calmar 6.77 → neighbour mean 5.90, Stability 0.87 ✅
  - `g5_106` straddle_d456 Calmar 5.84 → neighbour mean 5.58, Stability 0.96 ✅
  - `g5_117` straddle_d456 Calmar 5.84 → neighbour mean 5.30, Stability 0.91 ✅
  - `g5_91` strangle_offset_d456 Calmar 3.02 → neighbour mean 3.04, Stability 1.01 ✅
  - `g5_157` strangle_offset_d23 Calmar 3.21 → neighbour mean 3.32, Stability 1.03 ✅
  - `g5_129` strangle_offset_d23 Calmar 3.25 → neighbour mean 3.43, Stability 1.06 ✅
  - `g5_13` strangle_offset_d456 Calmar 3.56 → neighbour mean 3.24, Stability 0.91 ✅
  - `g5_110` strangle_offset_d23 Calmar 3.30 → neighbour mean 2.76, Stability 0.83 ✅
  - `g5_120` strangle_premium_d456 Calmar 2.76 → neighbour mean 2.51, Stability 0.91 ✅
  - `g5_164` strangle_offset_d456 Calmar 2.06 → neighbour mean 2.12, Stability 1.03 ✅
- Phase C walk-forward/holdout:
  - `g5_161` straddle_d456: valid Calmar 1.85 PF 1.37 net ₹6,633; holdout not touched → rejected (validation Calmar 1.85/PF 1.37)
  - `g5_106` straddle_d456: valid Calmar 2.54 PF 1.57 net ₹9,125; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; validation Calmar 2.54/PF 1.57)
  - `g5_117` straddle_d456: valid Calmar 2.36 PF 1.52 net ₹8,466; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; validation Calmar 2.36/PF 1.52)
  - `g5_91` strangle_offset_d456: valid Calmar -1.97 PF 0.32 net ₹-14,763; holdout not touched → rejected (train hard-gate: tail: worst day ₹5599 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.97/PF 0.32)
  - `g5_157` strangle_offset_d23: valid Calmar 4.34 PF 2.59 net ₹8,483; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹276 < ₹450; tail: worst day ₹4260 > 1.5% of capital; losing months 27.8% > 15%)
  - `g5_129` strangle_offset_d23: valid Calmar 4.11 PF 2.52 net ₹10,024; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹306 < ₹450; tail: worst day ₹5352 > 1.5% of capital; losing months 22.2% > 15%)
  - `g5_13` strangle_offset_d456: valid Calmar 0.74 PF 1.11 net ₹1,138; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹387 < ₹450; losing months 27.8% > 15%; validation Calmar 0.74/PF 1.11)
  - `g5_110` strangle_offset_d23: valid Calmar 4.66 PF 2.65 net ₹11,199; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹332 < ₹450; tail: worst day ₹5150 > 1.5% of capital; losing months 27.8% > 15%)
  - `g5_120` strangle_premium_d456: valid Calmar -0.75 PF 0.87 net ₹-3,325; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹431 < ₹450; losing months 22.2% > 15%; validation Calmar -0.75/PF 0.87)
  - `g5_164` strangle_offset_d456: valid Calmar -1.66 PF 0.43 net ₹-11,937; holdout not touched → rejected (train hard-gate: tail: worst day ₹7723 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.66/PF 0.43)
- Phase D hypotheses:
  - 3/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 8/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20250221(dte6,₹-2,955,1SL,MAXLOSS), 20250110(dte6,₹-2,908,1SL,MAXLOSS), 20241220(dte6,₹-2,836,1SL,MAXLOSS), 20240816(dte6,₹-2,835,1SL,MAXLOSS), 20250117(dte6,₹-2,793,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=2.52, d456=3.40

## Generation 6  (159 train runs in 0.3s engine time, 3.6s wall)

- Hard-gate passes on train: **2/159**
- Top `g6_120` straddle_d456 (score 29.65): net ₹52,814 | DD ₹5,480 | Calmar 6.78 | PF 2.74 | win 73.1% | exp ₹1016 | worst ₹-2,836 | losing-months 11% | UW 6d
- Top `g6_160` straddle_d456 (score 24.23): net ₹40,166 | DD ₹5,702 | Calmar 4.96 | PF 2.54 | win 73.1% | exp ₹772 | worst ₹-2,955 | losing-months 11% | UW 7d
- Top `g6_167` straddle_d456 (score 9.31): net ₹53,583 | DD ₹6,566 | Calmar 5.74 | PF 3.00 | win 71.2% | exp ₹1030 | worst ₹-3,383 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3383 > 1.5% of capital
- Phase B stability audit:
  - `g6_120` straddle_d456 Calmar 6.78 → neighbour mean 5.45, Stability 0.80 ✅
  - `g6_160` straddle_d456 Calmar 4.96 → neighbour mean 5.24, Stability 1.06 ✅
  - `g6_167` straddle_d456 Calmar 5.74 → neighbour mean 5.33, Stability 0.93 ✅
  - `g6_124` strangle_offset_d23 Calmar 5.81 → neighbour mean 5.21, Stability 0.90 ✅
  - `g6_93` strangle_offset_d23 Calmar 5.64 → neighbour mean 4.67, Stability 0.83 ✅
  - `g6_134` strangle_offset_d23 Calmar 5.64 → neighbour mean 4.67, Stability 0.83 ✅
  - `g6_169` strangle_offset_d456 Calmar 2.41 → neighbour mean 2.56, Stability 1.06 ✅
  - `g6_161` strangle_offset_d456 Calmar 2.74 → neighbour mean 2.60, Stability 0.95 ✅
  - `g6_143` strangle_offset_d456 Calmar 3.58 → neighbour mean 2.76, Stability 0.77 ✅
  - `g6_68` strangle_premium_d456 Calmar 0.66 → neighbour mean 0.28, Stability 0.42 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g6_120` straddle_d456: valid Calmar 1.95 PF 1.39 net ₹6,936; holdout not touched → rejected (validation Calmar 1.95/PF 1.39)
  - `g6_160` straddle_d456: valid Calmar 0.35 PF 1.08 net ₹1,319; holdout not touched → rejected (validation Calmar 0.35/PF 1.08)
  - `g6_167` straddle_d456: valid Calmar 2.50 PF 1.60 net ₹9,656; holdout not touched → rejected (train hard-gate: tail: worst day ₹3383 > 1.5% of capital; validation Calmar 2.50/PF 1.60)
  - `g6_124` strangle_offset_d23: valid Calmar 15.83 PF 3.37 net ₹9,683; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹337 < ₹450; losing months 16.7% > 15%)
  - `g6_93` strangle_offset_d23: valid Calmar 20.10 PF 3.96 net ₹11,656; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹421 < ₹450; losing months 27.8% > 15%)
  - `g6_134` strangle_offset_d23: valid Calmar 20.10 PF 3.96 net ₹11,656; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹421 < ₹450; losing months 27.8% > 15%)
  - `g6_169` strangle_offset_d456: valid Calmar -1.70 PF 0.45 net ₹-9,466; holdout not touched → rejected (train hard-gate: tail: worst day ₹3485 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.70/PF 0.45)
  - `g6_161` strangle_offset_d456: valid Calmar -0.24 PF 0.93 net ₹-417; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹343 < ₹450; losing months 16.7% > 15%; validation Calmar -0.24/PF 0.93)
  - `g6_143` strangle_offset_d456: valid Calmar -1.58 PF 0.47 net ₹-10,921; holdout not touched → rejected (train hard-gate: tail: worst day ₹5951 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.58/PF 0.47)
- Phase D hypotheses:
  - 3/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 9/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241220(dte6,₹-2,836,1SL,MAXLOSS), 20250117(dte6,₹-2,793,1SL,MAXLOSS), 20240315(dte6,₹-2,784,1SL,MAXLOSS), 20250307(dte6,₹-2,747,1SL,MAXLOSS), 20240802(dte6,₹-2,701,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=3.40, d456=3.40

## Generation 7  (169 train runs in 0.3s engine time, 3.9s wall)

- Hard-gate passes on train: **6/169**
- Top `g7_149` straddle_d456 (score 30.10): net ₹53,510 | DD ₹5,480 | Calmar 6.87 | PF 2.77 | win 73.1% | exp ₹1029 | worst ₹-2,836 | losing-months 11% | UW 6d
- Top `g7_107` straddle_d456 (score 29.65): net ₹52,814 | DD ₹5,480 | Calmar 6.78 | PF 2.74 | win 73.1% | exp ₹1016 | worst ₹-2,836 | losing-months 11% | UW 6d
- Top `g7_130` straddle_d456 (score 24.23): net ₹40,166 | DD ₹5,702 | Calmar 4.96 | PF 2.54 | win 73.1% | exp ₹772 | worst ₹-2,955 | losing-months 11% | UW 7d
- Phase B stability audit:
  - `g7_149` straddle_d456 Calmar 6.87 → neighbour mean 5.38, Stability 0.78 ✅
  - `g7_107` straddle_d456 Calmar 6.78 → neighbour mean 5.45, Stability 0.80 ✅
  - `g7_130` straddle_d456 Calmar 4.96 → neighbour mean 5.19, Stability 1.05 ✅
  - `g7_165` strangle_offset_d23 Calmar 6.66 → neighbour mean 3.97, Stability 0.60 ❌ discarded (lucky spike)
  - `g7_162` strangle_offset_d23 Calmar 5.27 → neighbour mean 3.38, Stability 0.64 ❌ discarded (lucky spike)
  - `g7_110` strangle_offset_d23 Calmar 4.85 → neighbour mean 3.98, Stability 0.82 ✅
  - `g7_126` strangle_premium_d456 Calmar 4.05 → neighbour mean 2.66, Stability 0.66 ❌ discarded (lucky spike)
  - `g7_152` strangle_offset_d456 Calmar 3.58 → neighbour mean 3.67, Stability 1.03 ✅
  - `g7_96` strangle_offset_d456 Calmar 2.13 → neighbour mean 1.45, Stability 0.68 ❌ discarded (lucky spike)
  - `g7_70` strangle_premium_d456 Calmar 2.28 → neighbour mean 1.50, Stability 0.66 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g7_149` straddle_d456: valid Calmar 1.95 PF 1.39 net ₹6,936; holdout not touched → rejected (validation Calmar 1.95/PF 1.39)
  - `g7_107` straddle_d456: valid Calmar 1.86 PF 1.37 net ₹6,621; holdout not touched → rejected (validation Calmar 1.86/PF 1.37)
  - `g7_130` straddle_d456: valid Calmar -0.36 PF 0.91 net ₹-1,766; holdout not touched → rejected (validation Calmar -0.36/PF 0.91)
  - `g7_110` strangle_offset_d23: valid Calmar 11.65 PF 3.05 net ₹10,566; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹420 < ₹450; underwater 29 active days > 25)
  - `g7_152` strangle_offset_d456: valid Calmar -1.62 PF 0.50 net ₹-12,291; holdout not touched → rejected (train hard-gate: tail: worst day ₹6312 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -1.62/PF 0.50)
- Phase D hypotheses:
  - 3/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 9/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241220(dte6,₹-2,836,1SL,MAXLOSS), 20250117(dte6,₹-2,793,1SL,MAXLOSS), 20240315(dte6,₹-2,784,1SL,MAXLOSS), 20250307(dte6,₹-2,747,1SL,MAXLOSS), 20240802(dte6,₹-2,701,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=3.40, d456=3.40

## Generation 8  (158 train runs in 0.3s engine time, 3.7s wall)

- Hard-gate passes on train: **9/158**
- Top `g8_122` straddle_d456 (score 33.70): net ₹56,489 | DD ₹5,608 | Calmar 7.09 | PF 3.01 | win 75.0% | exp ₹1086 | worst ₹-2,913 | losing-months 11% | UW 6d
- Top `g8_85` straddle_d456 (score 31.65): net ₹54,801 | DD ₹5,702 | Calmar 6.77 | PF 2.93 | win 75.0% | exp ₹1054 | worst ₹-2,955 | losing-months 11% | UW 6d
- Top `g8_86` straddle_d456 (score 31.65): net ₹54,801 | DD ₹5,702 | Calmar 6.77 | PF 2.93 | win 75.0% | exp ₹1054 | worst ₹-2,955 | losing-months 11% | UW 6d
- Phase B stability audit:
  - `g8_122` straddle_d456 Calmar 7.09 → neighbour mean 5.97, Stability 0.84 ✅
  - `g8_85` straddle_d456 Calmar 6.77 → neighbour mean 5.90, Stability 0.87 ✅
  - `g8_86` straddle_d456 Calmar 6.77 → neighbour mean 5.90, Stability 0.87 ✅
  - `g8_97` strangle_offset_d23 Calmar 5.81 → neighbour mean 5.21, Stability 0.90 ✅
  - `g8_102` strangle_offset_d23 Calmar 5.02 → neighbour mean 2.79, Stability 0.56 ❌ discarded (lucky spike)
  - `g8_106` strangle_offset_d23 Calmar 6.17 → neighbour mean 4.67, Stability 0.76 ✅
  - `g8_157` strangle_premium_d456 Calmar 3.92 → neighbour mean 3.52, Stability 0.90 ✅
  - `g8_145` strangle_offset_d456 Calmar 2.64 → neighbour mean 2.62, Stability 0.99 ✅
  - `g8_82` strangle_premium_d456 Calmar 2.52 → neighbour mean 2.36, Stability 0.94 ✅
  - `g8_158` strangle_premium_d456 Calmar 2.10 → neighbour mean 1.81, Stability 0.86 ✅
- Phase C walk-forward/holdout:
  - `g8_122` straddle_d456: valid Calmar 1.94 PF 1.38 net ₹6,793; holdout not touched → rejected (validation Calmar 1.94/PF 1.38)
  - `g8_85` straddle_d456: valid Calmar 1.85 PF 1.37 net ₹6,633; holdout not touched → rejected (validation Calmar 1.85/PF 1.37)
  - `g8_86` straddle_d456: valid Calmar 1.85 PF 1.37 net ₹6,633; holdout not touched → rejected (validation Calmar 1.85/PF 1.37)
  - `g8_97` strangle_offset_d23: valid Calmar 15.83 PF 3.37 net ₹9,683; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹337 < ₹450; losing months 16.7% > 15%)
  - `g8_106` strangle_offset_d23: valid Calmar 18.45 PF 3.72 net ₹9,318; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹333 < ₹450; losing months 27.8% > 15%; underwater 31 active days > 25)
  - `g8_157` strangle_premium_d456: valid Calmar 12.86 PF 2.16 net ₹32,084; holdout not touched → rejected (train hard-gate: tail: worst day ₹3541 > 1.5% of capital; losing months 33.3% > 15%)
  - `g8_145` strangle_offset_d456: valid Calmar -0.24 PF 0.93 net ₹-417; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹383 < ₹450; tail: worst day ₹3644 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -0.24/PF 0.93)
  - `g8_82` strangle_premium_d456: valid Calmar 7.74 PF 1.88 net ₹11,989; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹445 < ₹450; tail: worst day ₹3069 > 1.5% of capital; losing months 33.3% > 15%)
  - `g8_158` strangle_premium_d456: valid Calmar -0.68 PF 0.87 net ₹-3,020; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹296 < ₹450; losing months 33.3% > 15%; validation Calmar -0.68/PF 0.87)
- Phase D hypotheses:
  - 3/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 8/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20250221(dte6,₹-2,913,1SL,MAXLOSS), 20250110(dte6,₹-2,808,1SL,MAXLOSS), 20250117(dte6,₹-2,800,1SL,MAXLOSS), 20241220(dte6,₹-2,800,1SL,MAXLOSS), 20240315(dte6,₹-2,787,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[1], straddle/DTE[1, 2], straddle/DTE[2, 3], strangle_offset/DTE[1], strangle_offset/DTE[1, 2], strangle_offset/DTE[4, 5, 6, 7], strangle_premium/DTE[1], strangle_premium/DTE[1, 2], strangle_premium/DTE[2, 3], strangle_premium/DTE[4, 5, 6, 7]
- Next-gen bucket weights: d1=0.40, d12=0.41, d23=3.40, d456=3.40


# Run v4 (seed 23, pop 400)

Splits (chronological): train (20240101, 20250616), validation (20250617, 20251124), holdout (20251125, 20260324).

Costs: ₹20/order brokerage, STT 0.1% sell, NSE txn 0.03503%, SEBI 0.0001%, stamp 0.003% buy, GST 18%; slippage 0.3% per market fill (min 0.05), +0.5% on stop fills; lot 65 constant; capital ₹2,00,000 per lot.

## Generation 1  (400 train runs in 0.8s engine time, 4.5s wall)

- Hard-gate passes on train: **13/400**
- Top `g1_347` straddle_d456 (score 33.70): net ₹56,489 | DD ₹5,608 | Calmar 7.09 | PF 3.01 | win 75.0% | exp ₹1086 | worst ₹-2,913 | losing-months 11% | UW 6d
- Top `g1_380` straddle_d456 (score 31.65): net ₹54,801 | DD ₹5,702 | Calmar 6.77 | PF 2.93 | win 75.0% | exp ₹1054 | worst ₹-2,955 | losing-months 11% | UW 6d
- Top `g1_312` straddle_d456 (score 28.68): net ₹40,508 | DD ₹4,922 | Calmar 5.79 | PF 2.58 | win 73.1% | exp ₹779 | worst ₹-2,836 | losing-months 11% | UW 6d
- Phase B stability audit:
  - `g1_347` straddle_d456 Calmar 7.09 → neighbour mean 5.97, Stability 0.84 ✅
  - `g1_380` straddle_d456 Calmar 6.77 → neighbour mean 5.90, Stability 0.87 ✅
  - `g1_312` straddle_d456 Calmar 5.79 → neighbour mean 5.02, Stability 0.87 ✅
  - `g1_342` strangle_offset_d23 Calmar 6.96 → neighbour mean 4.00, Stability 0.57 ❌ discarded (lucky spike)
  - `g1_358` strangle_offset_d23 Calmar 6.38 → neighbour mean 5.19, Stability 0.81 ✅
  - `g1_328` strangle_offset_d23 Calmar 4.92 → neighbour mean 4.18, Stability 0.85 ✅
  - `g1_362` strangle_premium_d456 Calmar 3.54 → neighbour mean 3.09, Stability 0.87 ✅
  - `g1_344` strangle_offset_d456 Calmar 3.74 → neighbour mean 2.29, Stability 0.61 ❌ discarded (lucky spike)
  - `g1_223` strangle_offset_d456 Calmar 2.89 → neighbour mean 2.99, Stability 1.03 ✅
  - `g1_370` strangle_offset_d456 Calmar 4.00 → neighbour mean 4.06, Stability 1.01 ✅
- Phase C walk-forward/holdout:
  - `g1_347` straddle_d456: valid Calmar 1.94 PF 1.38 net ₹6,793; holdout not touched → rejected (validation Calmar 1.94/PF 1.38)
  - `g1_380` straddle_d456: valid Calmar 1.85 PF 1.37 net ₹6,633; holdout not touched → rejected (validation Calmar 1.85/PF 1.37)
  - `g1_312` straddle_d456: valid Calmar -0.07 PF 0.98 net ₹-304; holdout not touched → rejected (validation Calmar -0.07/PF 0.98)
  - `g1_358` strangle_offset_d23: valid Calmar 12.49 PF 3.42 net ₹10,019; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹353 < ₹450; losing months 16.7% > 15%)
  - `g1_328` strangle_offset_d23: valid Calmar 15.83 PF 3.37 net ₹9,683; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹285 < ₹450; losing months 16.7% > 15%)
  - `g1_362` strangle_premium_d456: valid Calmar 2.22 PF 1.44 net ₹6,070; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹404 < ₹450; losing months 22.2% > 15%; validation Calmar 2.22/PF 1.44)
  - `g1_223` strangle_offset_d456: valid Calmar -1.49 PF 0.59 net ₹-7,037; holdout not touched → rejected (train hard-gate: tail: worst day ₹3500 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar -1.49/PF 0.59)
  - `g1_370` strangle_offset_d456: valid Calmar -1.70 PF 0.46 net ₹-13,611; holdout not touched → rejected (train hard-gate: tail: worst day ₹5606 > 1.5% of capital; losing months 16.7% > 15%; validation Calmar -1.70/PF 0.46)
- Phase D hypotheses:
  - 3/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 8/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20250221(dte6,₹-2,913,1SL,MAXLOSS), 20250110(dte6,₹-2,808,1SL,MAXLOSS), 20250117(dte6,₹-2,800,1SL,MAXLOSS), 20241220(dte6,₹-2,800,1SL,MAXLOSS), 20240315(dte6,₹-2,787,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 2  (322 train runs in 0.5s engine time, 3.9s wall)

- Hard-gate passes on train: **14/322**
- Top `g2_165` straddle_d456 (score 28.68): net ₹40,508 | DD ₹4,922 | Calmar 5.79 | PF 2.58 | win 73.1% | exp ₹779 | worst ₹-2,836 | losing-months 11% | UW 6d
- Top `g2_166` straddle_d456 (score 28.68): net ₹40,508 | DD ₹4,922 | Calmar 5.79 | PF 2.58 | win 73.1% | exp ₹779 | worst ₹-2,836 | losing-months 11% | UW 6d
- Top `g2_184` straddle_d456 (score 28.68): net ₹40,508 | DD ₹4,922 | Calmar 5.79 | PF 2.58 | win 73.1% | exp ₹779 | worst ₹-2,836 | losing-months 11% | UW 6d
- Phase B stability audit:
  - `g2_165` straddle_d456 Calmar 5.79 → neighbour mean 5.02, Stability 0.87 ✅
  - `g2_166` straddle_d456 Calmar 5.79 → neighbour mean 5.02, Stability 0.87 ✅
  - `g2_184` straddle_d456 Calmar 5.79 → neighbour mean 5.09, Stability 0.88 ✅
  - `g2_245` strangle_offset_d456 Calmar 4.53 → neighbour mean 3.98, Stability 0.88 ✅
  - `g2_190` strangle_premium_d456 Calmar 4.23 → neighbour mean 3.84, Stability 0.91 ✅
  - `g2_285` strangle_offset_d23 Calmar 6.38 → neighbour mean 5.19, Stability 0.81 ✅
  - `g2_286` strangle_offset_d23 Calmar 5.81 → neighbour mean 5.21, Stability 0.90 ✅
  - `g2_238` strangle_offset_d23 Calmar 5.11 → neighbour mean 4.21, Stability 0.82 ✅
  - `g2_281` strangle_offset_d456 Calmar 3.99 → neighbour mean 1.86, Stability 0.47 ❌ discarded (lucky spike)
  - `g2_59` strangle_premium_d456 Calmar 3.36 → neighbour mean 2.50, Stability 0.75 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g2_165` straddle_d456: valid Calmar -0.08 PF 0.98 net ₹-369; holdout not touched → rejected (validation Calmar -0.08/PF 0.98)
  - `g2_166` straddle_d456: valid Calmar -0.07 PF 0.98 net ₹-304; holdout not touched → rejected (validation Calmar -0.07/PF 0.98)
  - `g2_184` straddle_d456: valid Calmar 0.67 PF 1.15 net ₹2,356; holdout not touched → rejected (validation Calmar 0.67/PF 1.15)
  - `g2_245` strangle_offset_d456: valid Calmar -1.79 PF 0.43 net ₹-8,741; holdout not touched → rejected (train hard-gate: losing months 16.7% > 15%; validation Calmar -1.79/PF 0.43)
  - `g2_190` strangle_premium_d456: valid Calmar 14.14 PF 3.10 net ₹14,930; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%)
  - `g2_285` strangle_offset_d23: valid Calmar 12.49 PF 3.42 net ₹10,019; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹353 < ₹450; losing months 16.7% > 15%)
  - `g2_286` strangle_offset_d23: valid Calmar 15.83 PF 3.37 net ₹9,683; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹337 < ₹450; losing months 16.7% > 15%)
  - `g2_238` strangle_offset_d23: valid Calmar 14.78 PF 3.21 net ₹9,231; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹329 < ₹450; losing months 16.7% > 15%; underwater 31 active days > 25)
- Phase D hypotheses:
  - 4/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 9/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241220(dte6,₹-2,836,1SL,MAXLOSS), 20250307(dte6,₹-2,576,1SL,MAXLOSS), 20250221(dte6,₹-2,572,0SL,MAXLOSS), 20240315(dte6,₹-2,539,1SL,MAXLOSS), 20240712(dte6,₹-2,534,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 3  (320 train runs in 0.6s engine time, 4.1s wall)

- Hard-gate passes on train: **12/320**
- Top `g3_232` straddle_d456 (score 36.47): net ₹45,412 | DD ₹4,990 | Calmar 6.41 | PF 3.00 | win 75.0% | exp ₹873 | worst ₹-2,569 | losing-months 11% | UW 6d
- Top `g3_328` straddle_d456 (score 34.29): net ₹57,298 | DD ₹5,608 | Calmar 7.19 | PF 3.04 | win 75.0% | exp ₹1102 | worst ₹-2,913 | losing-months 11% | UW 6d
- Top `g3_145` straddle_d456 (score 28.68): net ₹40,508 | DD ₹4,922 | Calmar 5.79 | PF 2.58 | win 73.1% | exp ₹779 | worst ₹-2,836 | losing-months 11% | UW 6d
- Phase B stability audit:
  - `g3_232` straddle_d456 Calmar 6.41 → neighbour mean 4.81, Stability 0.75 ✅
  - `g3_328` straddle_d456 Calmar 7.19 → neighbour mean 6.68, Stability 0.93 ✅
  - `g3_145` straddle_d456 Calmar 5.79 → neighbour mean 5.09, Stability 0.88 ✅
  - `g3_212` strangle_offset_d456 Calmar 4.05 → neighbour mean 3.53, Stability 0.87 ✅
  - `g3_296` strangle_offset_d456 Calmar 4.56 → neighbour mean 4.02, Stability 0.88 ✅
  - `g3_316` strangle_offset_d456 Calmar 4.56 → neighbour mean 4.02, Stability 0.88 ✅
  - `g3_160` strangle_offset_d23 Calmar 6.38 → neighbour mean 5.19, Stability 0.81 ✅
  - `g3_256` strangle_offset_d23 Calmar 6.66 → neighbour mean 3.97, Stability 0.60 ❌ discarded (lucky spike)
  - `g3_159` strangle_premium_d456 Calmar 4.36 → neighbour mean 3.84, Stability 0.88 ✅
  - `g3_331` strangle_premium_d456 Calmar 4.97 → neighbour mean 3.93, Stability 0.79 ✅
- Phase C walk-forward/holdout:
  - `g3_232` straddle_d456: valid Calmar 1.24 PF 1.28 net ₹4,256; holdout not touched → rejected (validation Calmar 1.24/PF 1.28)
  - `g3_328` straddle_d456: valid Calmar 2.16 PF 1.43 net ₹7,591; holdout not touched → rejected (validation Calmar 2.16/PF 1.43)
  - `g3_145` straddle_d456: valid Calmar 0.67 PF 1.15 net ₹2,356; holdout not touched → rejected (validation Calmar 0.67/PF 1.15)
  - `g3_212` strangle_offset_d456: valid Calmar -1.65 PF 0.56 net ₹-5,848; holdout not touched → rejected (validation Calmar -1.65/PF 0.56)
  - `g3_296` strangle_offset_d456: valid Calmar -1.84 PF 0.45 net ₹-8,617; holdout not touched → rejected (validation Calmar -1.84/PF 0.45)
  - `g3_316` strangle_offset_d456: valid Calmar -1.84 PF 0.45 net ₹-8,617; holdout not touched → rejected (validation Calmar -1.84/PF 0.45)
  - `g3_160` strangle_offset_d23: valid Calmar 12.49 PF 3.42 net ₹10,019; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹353 < ₹450; losing months 16.7% > 15%)
  - `g3_159` strangle_premium_d456: valid Calmar 19.25 PF 3.00 net ₹13,693; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹427 < ₹450; losing months 22.2% > 15%)
  - `g3_331` strangle_premium_d456: valid Calmar 9.94 PF 2.61 net ₹13,763; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹410 < ₹450; losing months 27.8% > 15%)
- Phase D hypotheses:
  - 4/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - 8/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20241220(dte6,₹-2,569,1SL,MAXLOSS), 20250117(dte6,₹-2,568,1SL,MAXLOSS), 20240315(dte6,₹-2,556,1SL,MAXLOSS), 20250307(dte6,₹-2,548,1SL,MAXLOSS), 20240802(dte6,₹-2,494,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 4  (320 train runs in 0.7s engine time, 4.4s wall)

- Hard-gate passes on train: **15/320**
- Top `g4_186` straddle_d456 (score 49.16): net ₹50,050 | DD ₹5,602 | Calmar 6.29 | PF 3.56 | win 67.3% | exp ₹963 | worst ₹-2,984 | losing-months 6% | UW 3d
- Top `g4_304` straddle_d456 (score 36.47): net ₹45,412 | DD ₹4,990 | Calmar 6.41 | PF 3.00 | win 75.0% | exp ₹873 | worst ₹-2,569 | losing-months 11% | UW 6d
- Top `g4_171` straddle_d456 (score 34.29): net ₹57,298 | DD ₹5,608 | Calmar 7.19 | PF 3.04 | win 75.0% | exp ₹1102 | worst ₹-2,913 | losing-months 11% | UW 6d
- Phase B stability audit:
  - `g4_186` straddle_d456 Calmar 6.29 → neighbour mean 4.08, Stability 0.65 ❌ discarded (lucky spike)
  - `g4_304` straddle_d456 Calmar 6.41 → neighbour mean 4.89, Stability 0.76 ✅
  - `g4_171` straddle_d456 Calmar 7.19 → neighbour mean 6.68, Stability 0.93 ✅
  - `g4_188` strangle_offset_d456 Calmar 3.84 → neighbour mean 3.45, Stability 0.90 ✅
  - `g4_157` strangle_offset_d456 Calmar 4.56 → neighbour mean 4.02, Stability 0.88 ✅
  - `g4_240` strangle_offset_d456 Calmar 4.56 → neighbour mean 4.01, Stability 0.88 ✅
  - `g4_93` strangle_premium_d456 Calmar 8.91 → neighbour mean 8.70, Stability 0.98 ✅
  - `g4_204` strangle_premium_d456 Calmar 5.76 → neighbour mean 4.65, Stability 0.81 ✅
  - `g4_211` strangle_premium_d456 Calmar 4.46 → neighbour mean 3.78, Stability 0.85 ✅
  - `g4_180` strangle_offset_d23 Calmar 6.02 → neighbour mean 5.08, Stability 0.84 ✅
- Phase C walk-forward/holdout:
  - `g4_304` straddle_d456: valid Calmar 0.36 PF 1.09 net ₹1,567; holdout not touched → rejected (validation Calmar 0.36/PF 1.09)
  - `g4_171` straddle_d456: valid Calmar 2.16 PF 1.43 net ₹7,591; holdout not touched → rejected (validation Calmar 2.16/PF 1.43)
  - `g4_188` strangle_offset_d456: valid Calmar -1.45 PF 0.67 net ₹-3,903; holdout not touched → rejected (validation Calmar -1.45/PF 0.67)
  - `g4_157` strangle_offset_d456: valid Calmar -1.84 PF 0.45 net ₹-8,617; holdout not touched → rejected (validation Calmar -1.84/PF 0.45)
  - `g4_240` strangle_offset_d456: valid Calmar -1.84 PF 0.45 net ₹-8,617; holdout not touched → rejected (validation Calmar -1.84/PF 0.45)
  - `g4_93` strangle_premium_d456: valid Calmar -1.22 PF 0.82 net ₹-4,739; holdout not touched → rejected (train hard-gate: tail: worst day ₹4030 > 1.5% of capital; losing months 27.8% > 15%; validation Calmar -1.22/PF 0.82)
  - `g4_204` strangle_premium_d456: valid Calmar 10.68 PF 2.15 net ₹12,472; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%)
  - `g4_211` strangle_premium_d456: valid Calmar 24.13 PF 2.91 net ₹13,772; holdout not touched → rejected (train hard-gate: losing months 22.2% > 15%)
  - `g4_180` strangle_offset_d23: valid Calmar 12.02 PF 3.32 net ₹9,866; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹343 < ₹450; losing months 16.7% > 15%)
- Phase D hypotheses:
  - 5/10 worst days hit the portfolio max-loss → keep hard max-loss, tighten leg SL range.
  - Leader worst days: 20250307(dte6,₹-2,984,1SL,MAXLOSS), 20241220(dte6,₹-2,859,1SL,MAXLOSS), 20250117(dte6,₹-2,856,1SL,MAXLOSS), 20240802(dte6,₹-2,757,1SL,MAXLOSS), 20250110(dte6,₹-2,746,1SL,MAXLOSS)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 5  (317 train runs in 0.6s engine time, 4.1s wall)

- Hard-gate passes on train: **16/317**
- Top `g5_73` straddle_d456 (score 66.69): net ₹48,273 | DD ₹3,348 | Calmar 10.15 | PF 5.97 | win 79.4% | exp ₹766 | worst ₹-3,348 | losing-months 11% | UW 5d
  - gate failures: tail: worst day ₹3348 > 1.5% of capital
- Top `g5_324` strangle_premium_d456 (score 45.84): net ₹42,745 | DD ₹1,980 | Calmar 15.20 | PF 5.46 | win 46.2% | exp ₹822 | worst ₹-1,306 | losing-months 39% | UW 10d
  - gate failures: losing months 38.9% > 15%
- Top `g5_142` straddle_d456 (score 36.47): net ₹45,412 | DD ₹4,990 | Calmar 6.41 | PF 3.00 | win 75.0% | exp ₹873 | worst ₹-2,569 | losing-months 11% | UW 6d
- Phase B stability audit:
  - `g5_73` straddle_d456 Calmar 10.15 → neighbour mean 4.26, Stability 0.42 ❌ discarded (lucky spike)
  - `g5_324` strangle_premium_d456 Calmar 15.20 → neighbour mean 12.63, Stability 0.83 ✅
  - `g5_142` straddle_d456 Calmar 6.41 → neighbour mean 4.81, Stability 0.75 ✅
  - `g5_279` straddle_d456 Calmar 6.16 → neighbour mean 5.51, Stability 0.89 ✅
  - `g5_161` strangle_premium_d456 Calmar 9.20 → neighbour mean 11.46, Stability 1.24 ✅
  - `g5_260` strangle_premium_d456 Calmar 11.34 → neighbour mean 8.65, Stability 0.76 ✅
  - `g5_327` strangle_offset_d456 Calmar 4.76 → neighbour mean 4.20, Stability 0.88 ✅
  - `g5_165` strangle_offset_d456 Calmar 4.76 → neighbour mean 4.14, Stability 0.87 ✅
  - `g5_148` strangle_offset_d456 Calmar 4.05 → neighbour mean 3.53, Stability 0.87 ✅
  - `g5_187` strangle_offset_d23 Calmar 6.06 → neighbour mean 4.61, Stability 0.76 ✅
- Phase C walk-forward/holdout:
  - `g5_324` strangle_premium_d456: valid Calmar -1.22 PF 0.82 net ₹-4,739; holdout not touched → rejected (train hard-gate: losing months 38.9% > 15%; validation Calmar -1.22/PF 0.82)
  - `g5_142` straddle_d456: valid Calmar 1.24 PF 1.28 net ₹4,256; holdout not touched → rejected (validation Calmar 1.24/PF 1.28)
  - `g5_279` straddle_d456: valid Calmar 0.41 PF 1.08 net ₹1,464; holdout not touched → rejected (validation Calmar 0.41/PF 1.08)
  - `g5_161` strangle_premium_d456: valid Calmar -1.47 PF 0.78 net ₹-6,093; holdout not touched → rejected (train hard-gate: tail: worst day ₹4192 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.47/PF 0.78)
  - `g5_260` strangle_premium_d456: valid Calmar -1.10 PF 0.82 net ₹-4,860; holdout not touched → rejected (train hard-gate: tail: worst day ₹4067 > 1.5% of capital; losing months 22.2% > 15%; validation Calmar -1.10/PF 0.82)
  - `g5_327` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g5_165` strangle_offset_d456: valid Calmar -1.82 PF 0.46 net ₹-8,198; holdout not touched → rejected (validation Calmar -1.82/PF 0.46)
  - `g5_148` strangle_offset_d456: valid Calmar -1.65 PF 0.56 net ₹-5,848; holdout not touched → rejected (validation Calmar -1.65/PF 0.56)
  - `g5_187` strangle_offset_d23: valid Calmar 12.50 PF 2.88 net ₹8,779; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹318 < ₹450; losing months 22.2% > 15%)
- Phase D hypotheses:
  - 4/10 worst days were decided before 10:30 (gap-and-go) → enabling opening-range filter more often and later entries.
  - Leader worst days: 20240105(dte6,₹-3,348,2SL,TIME), 20250523(dte6,₹-2,658,1SL,TIME), 20250117(dte6,₹-742,0SL,LOCK), 20240823(dte6,₹-724,0SL,LOCK), 20250530(dte6,₹-532,0SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 6  (319 train runs in 0.6s engine time, 4.1s wall)

- Hard-gate passes on train: **20/319**
- Top `g6_199` strangle_premium_d456 (score 251.51): net ₹57,837 | DD ₹1,512 | Calmar 26.92 | PF 8.02 | win 43.3% | exp ₹863 | worst ₹-1,001 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Top `g6_200` strangle_premium_d456 (score 218.17): net ₹63,029 | DD ₹1,905 | Calmar 23.29 | PF 7.19 | win 50.7% | exp ₹941 | worst ₹-1,472 | losing-months 17% | UW 8d
  - gate failures: losing months 16.7% > 15%
- Top `g6_310` strangle_premium_d456 (score 163.22): net ₹54,158 | DD ₹1,750 | Calmar 21.79 | PF 6.36 | win 49.3% | exp ₹808 | worst ₹-1,327 | losing-months 22% | UW 8d
  - gate failures: losing months 22.2% > 15%
- Phase B stability audit:
  - `g6_199` strangle_premium_d456 Calmar 26.92 → neighbour mean 11.23, Stability 0.42 ❌ discarded (lucky spike)
  - `g6_200` strangle_premium_d456 Calmar 23.29 → neighbour mean 11.10, Stability 0.48 ❌ discarded (lucky spike)
  - `g6_310` strangle_premium_d456 Calmar 21.79 → neighbour mean 7.92, Stability 0.36 ❌ discarded (lucky spike)
  - `g6_289` straddle_d456 Calmar 5.77 → neighbour mean 5.71, Stability 0.99 ✅
  - `g6_252` strangle_offset_d456 Calmar 4.76 → neighbour mean 4.18, Stability 0.88 ✅
  - `g6_272` straddle_d456 Calmar 5.52 → neighbour mean 5.08, Stability 0.92 ✅
  - `g6_261` straddle_d456 Calmar 5.39 → neighbour mean 5.20, Stability 0.97 ✅
  - `g6_166` strangle_offset_d456 Calmar 4.56 → neighbour mean 4.01, Stability 0.88 ✅
  - `g6_276` strangle_offset_d456 Calmar 4.56 → neighbour mean 4.02, Stability 0.88 ✅
  - `g6_256` strangle_offset_d23 Calmar 6.65 → neighbour mean 4.04, Stability 0.61 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g6_289` straddle_d456: valid Calmar 0.24 PF 1.05 net ₹858; holdout not touched → rejected (validation Calmar 0.24/PF 1.05)
  - `g6_252` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g6_272` straddle_d456: valid Calmar 0.88 PF 1.17 net ₹3,085; holdout not touched → rejected (validation Calmar 0.88/PF 1.17)
  - `g6_261` straddle_d456: valid Calmar 0.87 PF 1.17 net ₹3,063; holdout not touched → rejected (validation Calmar 0.87/PF 1.17)
  - `g6_166` strangle_offset_d456: valid Calmar -1.84 PF 0.45 net ₹-8,617; holdout not touched → rejected (validation Calmar -1.84/PF 0.45)
  - `g6_276` strangle_offset_d456: valid Calmar -1.84 PF 0.45 net ₹-8,617; holdout not touched → rejected (validation Calmar -1.84/PF 0.45)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20240809(dte5,₹-1,001,1SL,TIME), 20240216(dte6,₹-784,1SL,TIME), 20250613(dte6,₹-782,1SL,TIME), 20240830(dte6,₹-686,0SL,TIME), 20250228(dte6,₹-401,1SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 7  (311 train runs in 0.5s engine time, 4.2s wall)

- Hard-gate passes on train: **9/311**
- Top `g7_205` strangle_premium_d456 (score 1123.75): net ₹53,679 | DD ₹822 | Calmar 45.98 | PF 12.48 | win 46.3% | exp ₹801 | worst ₹-645 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Top `g7_275` strangle_premium_d456 (score 253.87): net ₹57,989 | DD ₹1,541 | Calmar 26.49 | PF 8.17 | win 43.3% | exp ₹866 | worst ₹-969 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Top `g7_304` strangle_premium_d456 (score 120.09): net ₹69,787 | DD ₹2,076 | Calmar 23.66 | PF 5.80 | win 40.3% | exp ₹1042 | worst ₹-2,018 | losing-months 22% | UW 7d
  - gate failures: losing months 22.2% > 15%
- Phase B stability audit:
  - `g7_205` strangle_premium_d456 Calmar 45.98 → neighbour mean 15.63, Stability 0.34 ❌ discarded (lucky spike)
  - `g7_275` strangle_premium_d456 Calmar 26.49 → neighbour mean 11.61, Stability 0.44 ❌ discarded (lucky spike)
  - `g7_304` strangle_premium_d456 Calmar 23.66 → neighbour mean 11.53, Stability 0.49 ❌ discarded (lucky spike)
  - `g7_248` straddle_d456 Calmar 5.77 → neighbour mean 5.71, Stability 0.99 ✅
  - `g7_219` strangle_offset_d456 Calmar 4.76 → neighbour mean 4.20, Stability 0.88 ✅
  - `g7_303` strangle_offset_d456 Calmar 4.76 → neighbour mean 4.20, Stability 0.88 ✅
  - `g7_188` strangle_offset_d456 Calmar 3.84 → neighbour mean 3.45, Stability 0.90 ✅
  - `g7_296` straddle_d456 Calmar 5.75 → neighbour mean 5.54, Stability 0.96 ✅
  - `g7_300` straddle_d456 Calmar 5.75 → neighbour mean 5.47, Stability 0.95 ✅
  - `g7_225` strangle_offset_d23 Calmar 6.71 → neighbour mean 4.62, Stability 0.69 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g7_248` straddle_d456: valid Calmar 0.24 PF 1.05 net ₹858; holdout not touched → rejected (validation Calmar 0.24/PF 1.05)
  - `g7_219` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g7_303` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g7_188` strangle_offset_d456: valid Calmar -1.45 PF 0.67 net ₹-3,903; holdout not touched → rejected (validation Calmar -1.45/PF 0.67)
  - `g7_296` straddle_d456: valid Calmar 0.28 PF 1.06 net ₹953; holdout not touched → rejected (validation Calmar 0.28/PF 1.06)
  - `g7_300` straddle_d456: valid Calmar -0.46 PF 0.91 net ₹-1,867; holdout not touched → rejected (validation Calmar -0.46/PF 0.91)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20250613(dte6,₹-645,1SL,TIME), 20240830(dte6,₹-512,0SL,TIME), 20240216(dte6,₹-452,1SL,TIME), 20240816(dte6,₹-363,0SL,LOCK), 20240202(dte6,₹-235,0SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 8  (309 train runs in 0.6s engine time, 4.1s wall)

- Hard-gate passes on train: **17/309**
- Top `g8_182` strangle_premium_d456 (score 457.25): net ₹59,418 | DD ₹1,278 | Calmar 32.72 | PF 9.74 | win 44.8% | exp ₹887 | worst ₹-782 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Top `g8_227` strangle_premium_d456 (score 364.52): net ₹48,569 | DD ₹1,469 | Calmar 23.27 | PF 7.88 | win 53.7% | exp ₹725 | worst ₹-1,162 | losing-months 17% | UW 7d
  - gate failures: losing months 16.7% > 15%
- Top `g8_146` strangle_premium_d456 (score 137.51): net ₹58,014 | DD ₹2,255 | Calmar 18.11 | PF 6.64 | win 44.8% | exp ₹866 | worst ₹-1,081 | losing-months 22% | UW 8d
  - gate failures: losing months 22.2% > 15%
- Phase B stability audit:
  - `g8_182` strangle_premium_d456 Calmar 32.72 → neighbour mean 11.16, Stability 0.34 ❌ discarded (lucky spike)
  - `g8_227` strangle_premium_d456 Calmar 23.27 → neighbour mean 11.26, Stability 0.48 ❌ discarded (lucky spike)
  - `g8_146` strangle_premium_d456 Calmar 18.11 → neighbour mean 9.66, Stability 0.53 ❌ discarded (lucky spike)
  - `g8_166` straddle_d456 Calmar 5.77 → neighbour mean 5.71, Stability 0.99 ✅
  - `g8_180` straddle_d456 Calmar 5.77 → neighbour mean 5.71, Stability 0.99 ✅
  - `g8_284` straddle_d456 Calmar 5.77 → neighbour mean 5.57, Stability 0.97 ✅
  - `g8_291` strangle_offset_d456 Calmar 5.08 → neighbour mean 4.36, Stability 0.86 ✅
  - `g8_150` strangle_offset_d456 Calmar 4.50 → neighbour mean 4.02, Stability 0.89 ✅
  - `g8_309` strangle_offset_d456 Calmar 4.95 → neighbour mean 4.31, Stability 0.87 ✅
  - `g8_163` strangle_offset_d23 Calmar 6.22 → neighbour mean 4.90, Stability 0.79 ✅
- Phase C walk-forward/holdout:
  - `g8_166` straddle_d456: valid Calmar 0.24 PF 1.05 net ₹858; holdout not touched → rejected (validation Calmar 0.24/PF 1.05)
  - `g8_180` straddle_d456: valid Calmar 0.24 PF 1.05 net ₹858; holdout not touched → rejected (validation Calmar 0.24/PF 1.05)
  - `g8_284` straddle_d456: valid Calmar -0.47 PF 0.89 net ₹-2,044; holdout not touched → rejected (validation Calmar -0.47/PF 0.89)
  - `g8_291` strangle_offset_d456: valid Calmar -1.88 PF 0.41 net ₹-9,857; holdout not touched → rejected (validation Calmar -1.88/PF 0.41)
  - `g8_150` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g8_309` strangle_offset_d456: valid Calmar -1.80 PF 0.48 net ₹-7,889; holdout not touched → rejected (validation Calmar -1.80/PF 0.48)
  - `g8_163` strangle_offset_d23: valid Calmar 12.49 PF 3.42 net ₹10,019; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹344 < ₹450; losing months 16.7% > 15%)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20240809(dte5,₹-782,1SL,TIME), 20240216(dte6,₹-696,1SL,TIME), 20250613(dte6,₹-666,1SL,TIME), 20240830(dte6,₹-627,0SL,TIME), 20250228(dte6,₹-352,1SL,LOCK)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 9  (305 train runs in 0.5s engine time, 4.1s wall)

- Hard-gate passes on train: **15/305**
- Top `g9_276` strangle_premium_d456 (score 305.86): net ₹57,912 | DD ₹1,588 | Calmar 25.67 | PF 8.45 | win 47.8% | exp ₹864 | worst ₹-1,377 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Top `g9_146` strangle_premium_d456 (score 95.44): net ₹56,793 | DD ₹2,158 | Calmar 18.53 | PF 5.91 | win 46.3% | exp ₹848 | worst ₹-1,306 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Top `g9_138` strangle_premium_d456 (score 81.60): net ₹53,215 | DD ₹2,405 | Calmar 15.57 | PF 5.61 | win 44.8% | exp ₹794 | worst ₹-1,377 | losing-months 28% | UW 8d
  - gate failures: losing months 27.8% > 15%
- Phase B stability audit:
  - `g9_276` strangle_premium_d456 Calmar 25.67 → neighbour mean 9.70, Stability 0.38 ❌ discarded (lucky spike)
  - `g9_146` strangle_premium_d456 Calmar 18.53 → neighbour mean 11.58, Stability 0.63 ❌ discarded (lucky spike)
  - `g9_138` strangle_premium_d456 Calmar 15.57 → neighbour mean 13.12, Stability 0.84 ✅
  - `g9_182` strangle_offset_d456 Calmar 4.66 → neighbour mean 4.06, Stability 0.87 ✅
  - `g9_175` strangle_offset_d456 Calmar 4.50 → neighbour mean 4.02, Stability 0.89 ✅
  - `g9_207` strangle_offset_d456 Calmar 4.50 → neighbour mean 3.96, Stability 0.88 ✅
  - `g9_294` straddle_d456 Calmar 5.45 → neighbour mean 5.00, Stability 0.92 ✅
  - `g9_242` straddle_d456 Calmar 4.04 → neighbour mean 3.86, Stability 0.96 ✅
  - `g9_229` straddle_d456 Calmar 5.74 → neighbour mean 5.31, Stability 0.93 ✅
  - `g9_174` strangle_offset_d23 Calmar 7.52 → neighbour mean 4.43, Stability 0.59 ❌ discarded (lucky spike)
- Phase C walk-forward/holdout:
  - `g9_138` strangle_premium_d456: valid Calmar -1.01 PF 0.84 net ₹-3,905; holdout not touched → rejected (train hard-gate: losing months 27.8% > 15%; validation Calmar -1.01/PF 0.84)
  - `g9_182` strangle_offset_d456: valid Calmar -1.80 PF 0.48 net ₹-7,889; holdout not touched → rejected (validation Calmar -1.80/PF 0.48)
  - `g9_175` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g9_207` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g9_294` straddle_d456: valid Calmar -0.13 PF 0.97 net ₹-463; holdout not touched → rejected (validation Calmar -0.13/PF 0.97)
  - `g9_242` straddle_d456: valid Calmar 1.84 PF 1.31 net ₹5,183; holdout not touched → rejected (validation Calmar 1.84/PF 1.31)
  - `g9_229` straddle_d456: valid Calmar -0.55 PF 0.88 net ₹-2,283; holdout not touched → rejected (validation Calmar -0.55/PF 0.88)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20240712(dte6,₹-1,377,0SL,LOCK), 20240809(dte5,₹-759,1SL,TIME), 20240216(dte6,₹-666,1SL,TIME), 20250613(dte6,₹-659,1SL,TIME), 20240830(dte6,₹-588,0SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40

## Generation 10  (314 train runs in 0.6s engine time, 4.2s wall)

- Hard-gate passes on train: **21/314**
- Top `g10_325` strangle_premium_d456 (score 132.64): net ₹64,992 | DD ₹2,853 | Calmar 16.04 | PF 6.14 | win 47.8% | exp ₹970 | worst ₹-1,599 | losing-months 17% | UW 7d
  - gate failures: losing months 16.7% > 15%
- Top `g10_167` strangle_premium_d456 (score 127.43): net ₹62,381 | DD ₹1,998 | Calmar 21.98 | PF 5.47 | win 49.3% | exp ₹931 | worst ₹-1,566 | losing-months 17% | UW 7d
  - gate failures: losing months 16.7% > 15%
- Top `g10_185` strangle_premium_d456 (score 103.17): net ₹61,585 | DD ₹2,476 | Calmar 17.51 | PF 5.94 | win 76.1% | exp ₹919 | worst ₹-2,114 | losing-months 22% | UW 4d
  - gate failures: losing months 22.2% > 15%
- Phase B stability audit:
  - `g10_325` strangle_premium_d456 Calmar 16.04 → neighbour mean 10.49, Stability 0.65 ❌ discarded (lucky spike)
  - `g10_167` strangle_premium_d456 Calmar 21.98 → neighbour mean 12.39, Stability 0.56 ❌ discarded (lucky spike)
  - `g10_185` strangle_premium_d456 Calmar 17.51 → neighbour mean 11.76, Stability 0.67 ❌ discarded (lucky spike)
  - `g10_283` straddle_d456 Calmar 7.17 → neighbour mean 5.12, Stability 0.71 ❌ discarded (lucky spike)
  - `g10_252` strangle_offset_d456 Calmar 5.22 → neighbour mean 4.56, Stability 0.87 ✅
  - `g10_245` strangle_offset_d456 Calmar 4.66 → neighbour mean 4.06, Stability 0.87 ✅
  - `g10_279` strangle_offset_d456 Calmar 4.50 → neighbour mean 4.02, Stability 0.89 ✅
  - `g10_229` straddle_d456 Calmar 5.45 → neighbour mean 5.00, Stability 0.92 ✅
  - `g10_189` straddle_d456 Calmar 5.74 → neighbour mean 5.38, Stability 0.94 ✅
  - `g10_195` strangle_offset_d23 Calmar 6.38 → neighbour mean 5.19, Stability 0.81 ✅
- Phase C walk-forward/holdout:
  - `g10_252` strangle_offset_d456: valid Calmar -2.03 PF 0.43 net ₹-8,535; holdout not touched → rejected (validation Calmar -2.03/PF 0.43)
  - `g10_245` strangle_offset_d456: valid Calmar -1.80 PF 0.48 net ₹-7,889; holdout not touched → rejected (validation Calmar -1.80/PF 0.48)
  - `g10_279` strangle_offset_d456: valid Calmar -1.83 PF 0.46 net ₹-8,307; holdout not touched → rejected (validation Calmar -1.83/PF 0.46)
  - `g10_229` straddle_d456: valid Calmar -0.20 PF 0.96 net ₹-711; holdout not touched → rejected (validation Calmar -0.20/PF 0.96)
  - `g10_189` straddle_d456: valid Calmar 0.04 PF 1.01 net ₹135; holdout not touched → rejected (validation Calmar 0.04/PF 1.01)
  - `g10_195` strangle_offset_d23: valid Calmar 12.49 PF 3.42 net ₹10,019; holdout not touched → rejected (train hard-gate: thin edge: expectancy ₹353 < ₹450; losing months 16.7% > 15%)
- Phase D hypotheses:
  - Worst days spread across causes — no single structural fix; keep priors.
  - Leader worst days: 20240712(dte6,₹-1,599,0SL,LOCK), 20240105(dte6,₹-1,358,1SL,TIME), 20240216(dte6,₹-1,319,1SL,TIME), 20250613(dte6,₹-1,317,1SL,TIME), 20250321(dte6,₹-1,222,1SL,TIME)
- Dead regions (not re-sampled): straddle/DTE[2, 3], strangle_premium/DTE[2, 3]
- Next-gen bucket weights: d23=3.40, d456=3.40


# Run v5 — realistic engine + AlgoTest-expressible space + anchored walk-forward

Pre-registered protocol (written before running):
- Data: 2024 true OHLC + 2025-26 LTP with synthetic wicks (validated vs true OHLC on Oct-Dec 2024).
- Costs: Rs20/order, STT 0.1% sell, NSE 0.03503%, SEBI, stamp, GST; slippage 0.5%/fill (min Rs0.10) + 1% on stops.
- One strategy per TRADING-DTE bucket (0..4) so every weekday can use the capital; 1 lot, Rs2L gates.
- Walk-forward: for each quarter from 2024-Q3 the optimiser (LHS-style sampling + mutation, stability audit:
  entry +-1/+-2 min, SL +-2.5/+-5 pts, ratio >= 0.75) sees only earlier data, then trades the quarter blind.
- Final configs: same optimiser on all data; deploy only if hard gate passes on the full sample, stability >= 0.75,
  walk-forward OOS of that bucket is profitable with PF >= 1.2, and Deflated Sharpe >= 0.90.

- WF fold 2024-Q3 (train 20240101-20240628, test 20240701-20240930): tdte0 ironfly OOS Rs-9,123; tdte1 ironfly OOS Rs-12,921; tdte2 ironfly OOS Rs-1,410; tdte3 ironfly OOS Rs-15,605; tdte4 atm_pct OOS Rs2,802;
- WF fold 2024-Q4 (train 20240101-20240930, test 20241001-20241231): tdte0 ironfly OOS Rs16,595; tdte1 ironcondor OOS Rs-882; tdte2 prem_strangle OOS Rs2,919; tdte3 no stable config; tdte4 ironfly OOS Rs-7,224;
- WF fold 2025-Q1 (train 20240101-20241231, test 20250101-20250328): tdte0 no stable config; tdte1 atm_pct OOS Rs-6,389; tdte2 ironfly OOS Rs2,907; tdte3 ironcondor OOS Rs-1,436; tdte4 no stable config;
- WF fold 2025-Q2 (train 20240101-20250328, test 20250401-20250630): tdte0 ironfly OOS Rs-7,531; tdte1 prem_strangle OOS Rs-13,310; tdte2 ironcondor OOS Rs8,020; tdte3 prem_strangle OOS Rs-244; tdte4 ironfly OOS Rs-1,230;
- WF fold 2025-Q3 (train 20240101-20250630, test 20250701-20250930): tdte0 no stable config; tdte1 ironfly OOS Rs115; tdte2 ironfly OOS Rs2,504; tdte3 prem_strangle OOS Rs4,547; tdte4 prem_strangle OOS Rs-9,947;
- WF fold 2025-Q4 (train 20240101-20250930, test 20251001-20251231): tdte0 ironfly OOS Rs-4,363; tdte1 ironfly OOS Rs-135; tdte2 ironcondor OOS Rs2,342; tdte3 no stable config; tdte4 prem_strangle OOS Rs1,249;
- WF fold 2026-Q1 (train 20240101-20251231, test 20260101-20260324): tdte0 prem_strangle OOS Rs16,688; tdte1 ironfly OOS Rs256; tdte2 ironcondor OOS Rs-11,559; tdte3 atm_pct OOS Rs-5,197; tdte4 atm_pct OOS Rs-7,844;
- FINAL tdte0: ironfly stab 0.80 | net Rs59,969 DD Rs5,701 Calmar 4.81 PF 2.11 gate False losing months 25.9% > 15%
- FINAL tdte1: ironfly stab 0.81 | net Rs55,150 DD Rs8,313 Calmar 3.03 PF 1.72 gate False tail: worst day ₹8313 > 2.5x p90 win ₹2946; tail: worst day ₹8313 > 1.5% of capital; losing months 33.3% > 15%
- FINAL tdte2: ironfly stab 0.88 | net Rs62,220 DD Rs9,091 Calmar 3.13 PF 1.80 gate False tail: worst day ₹5180 > 1.5% of capital
- FINAL tdte3: prem_strangle stab 0.50 | net Rs35,674 DD Rs8,106 Calmar 2.01 PF 1.44 gate False thin edge: expectancy ₹310 < ₹450; tail: worst day ₹3004 > 1.5% of capital; losing months 25.9% > 15%
- FINAL tdte4: prem_strangle stab 0.54 | net Rs39,103 DD Rs4,329 Calmar 4.13 PF 2.13 gate False losing months 38.5% > 15%
- Trials evaluated in v5: 32610 (var of daily Sharpe across trials 0.00888); wall 220s

# Runs v6 / v7 — parsimonious grids, plateau selection, anchored walk-forward

v5 verdict: rejected. The 32,610-trial free search changed structure every quarter, walk-forward OOS summed to −₹55k (only DTE 0 +₹12k PF 1.20), and the Deflated Sharpe was ≈ 0.

v6 (pre-declared grid, 960 configs per trading-DTE, plateau selection, every config backtested once and selection replayed per fold):
- DTE 0: WF OOS +₹41,902, PF 1.44, DD ₹15,417. Picked the iron fly in all 7 folds (entry 09:20, SL 50%, trail-to-BE on SL legs, overall SL ₹2,500; wings ±200 to ±600).
- DTE 1: −₹13,496 (PF 0.56). DTE 2: −₹23,091 (PF 0.75). DTE 3: no config had a profitable plateau. DTE 4: −₹20,015 (PF 0.71). All rejected.

v7 (two hypotheses written down before running):
- H1 refine DTE 0 (432 configs): WF OOS +₹60,585, PF 1.66, DD ₹13,371. Final: ATM iron fly, OTM12 wings, 09:20 entry, SL 60%, trail-to-BE on SL legs, overall SL ₹2,000, exit 15:15. The search region was informed by v6's walk-forward, so this WF figure is mildly optimistic; v6's figure is the clean one.
- H2 afternoon theta on DTE 1–4 (144 configs each): DTE 1 WF −₹18,886 (PF 0.44); DTE 2–4 no stable config. Rejected.

Final grading (results/final_v7/final.json):
- 1 lot: +₹93,372 over 551 days (117 expiry days), max DD ₹12,423, PF 1.81, worst day −₹3,345.
- Stress: no wicks ₹107k; 2× slippage ₹74k; Monte-Carlo DD95 ₹27.4k.
- Deflated Sharpe 0.30 / 0.07 / 0.02 at 100 / 1,000 / 6,000 trials.
- The same rules forced onto every non-expiry DTE lose money; 4-Jun-2024 (DTE 2) would have cost −₹8,051.
- Hard gates: expectancy pass, underwater pass, worst-day fail (₹3,345 > ₹3,000), losing months fail (29.6%).

# Run v8 — VIX regime / shared-capital framework (user-supplied framework)

Pre-declared: SELL grid 126, BUY ORB grid 108 (1.5% slippage). Regime by India VIX previous close (NSE). Quarterly walk-forward per policy:
- A pure selling, expiry-day only (v7 style): net ₹38,489, PF 1.42, DD ₹15,379
- B pure selling, every day: net ₹-26,451, PF 0.88, DD ₹39,823
- C framework: sell low+mid VIX (every day), buy high VIX: net ₹-56,169, PF 0.52, DD ₹57,639
- D framework on expiry days: sell low+mid, buy high: net ₹-5,760, PF 0.95, DD ₹45,043
- E sell low+mid expiry only, no buying: net ₹22,664, PF 1.28, DD ₹15,580
- F = A + skip gap days > 0.7%: net ₹9,256, PF 1.10, DD ₹13,682
- G buy ORB in high VIX only (no selling): net ₹-28,424, PF 0.38, DD ₹41,125
- Threshold sensitivity (D): 12.5/15.5 −₹27.7k; 13/16 +₹37.1k; 13.5/16.5 −₹5.8k; 14/17 +₹32.2k; 15/18 +₹49.3k → unstable, rejected.
- In-sample-chosen VIX floor for expiry selling: WF +₹8.2k (worse than no floor). Rejected.
- Portfolio max profit hurts; portfolio max loss non-binding. Entry plateau 09:17–09:27. Wings: wider is better.
- Outcome: framework rejected except its risk layers; recommendation = expiry-day iron fly, ±400 wings on ₹2L / ±600 on ₹3L.

# Run v9 — review round 3
- Overfit audit (PBO 16–21%, one-shot v6 fails, bootstrap CI > 0, decay); compounding table; trend/sideways + OI study (no edge); sideways strangles fail OOS; Varsity structures + other trader's books; Gap-and-Go→Williams replication (GnG part survives, Williams fails); baskets with correlation ≈ 0.

## Round 5: Upstox Plus data (2026-11-08)
**Data validation (old research data vs Upstox exchange 1-min OHLC, 2026-03-03..24 overlap, 108,420 option-minutes):**
closes identical on 100.0% of rows (the LTP dataset is exact on closes). The synthetic intra-minute wicks were too
small: on expiry days the true wick (high / max(open, close) - 1) is median 4.1% / p90 11.9% / p99 28.2% vs the model's
2.2% / 7.6% / 17.1%. Stop-loss triggers were under-counted, so earlier 2025-26 results are optimistic.

**One-shot holdout, untouched 2026-03-25..2026-11-03 (32 NIFTY expiry days), frozen configs, STT 0.15%:**

| Strategy | Net | PF | Max DD | Worst day | Winning months |
|---|---|---|---|---|---|
| Iron fly +/-400 (fly400) | -Rs 2,145 | 0.93 | Rs 7,741 | -Rs 2,940 | 44% |
| Iron fly +/-600 | -Rs 1,851 | 0.94 | Rs 8,804 | -Rs 3,078 | 44% |
| ORB directional spread | -Rs 2,880 | 0.91 | Rs 11,867 | -Rs 2,549 | 33% |
| fly400 + spread | -Rs 5,025 | 0.90 | Rs 14,730 | -Rs 5,175 | 56% |
| Fly with wings by premium (~Rs 3) * | +Rs 5,558 | 1.18 | Rs 7,529 | -Rs 3,001 | 56% |

\* variant chosen after seeing the 2017-2020 data (below), not the holdout.
Exit mix is unchanged (34% overall-SL days vs 36% in research), so the strategy behaves the same; its edge per trade
has shrunk. -Rs 67/day over 32 days is about 1.5 standard errors below the earlier bootstrap mean: a warning, not yet proof.

**Independent 2017-2020 (Zenodo 10899828, CC0; 47 MONTHLY expiry days, trade-only bars, no OI):** strike-based wings are
mostly untradeable (fly400 traded on 20 of 47 days). With wings by premium (~Rs 3): all 47 days traded, +Rs 17,136,
PF 1.80, DD Rs 5,490, worst day -Rs 2,293, positive each year (2017 +1.5k, 2018 +2.5k, 2019 +2.4k, 2020 +10.7k).
The same rule on 2024-26 makes +Rs 92.4k, PF 1.80.

**SENSEX first look (2026-05-07..11-05, 27 expiry days, frozen NIFTY fly rules, lot 20; test-period data, not used for selection):**
PF 0.42-0.44 for every wing choice (OTM 10/15/20, premium Rs 3/10), net about -Rs 20k, DD about Rs 27k; half the days end at the
Rs 2,000 overall stop. 16 of 30 leg stops came from momentary spike prints (no close above the trigger within 3 min).
New engine option `exec.stop_on_close` (+ `catastrophe_mult`): stops fire on the 1-minute close and fill at the next bar's
open, as our own executor could do. Result on 2026: SENSEX PF 0.48 (-Rs 16.7k), NIFTY PF 1.07 (worse than 1.18 with resting
stops). Spike stops are not the main problem; SENSEX expiry days moved too much for this structure in 2026.

## Round 6: v11 discovery on 5 years of NIFTY (2026-11-09)
Data: NIFTY weekly options 2021-11-15..2026-11-03, 1,230 trading days / 259 expiry days, true exchange 1-min OHLC:
Upstox full chains (2024-10 ->), Breeze full chains (2024-01..09), Dhan rolling ATM+/-10 (2021-11..2024-09; matches Breeze
on the overlap: expiry dates 100%, closes within 1% on 98% of traded minutes). Costs at today's rates (STT 0.15%).
Dhan expiry dates come from the exchange calendar (settlement on the last-30-min average spot means 15:29 premiums cannot
identify expiry days); checked by the ATM straddle jumping 1.9x (p5) the day after each expiry.

**Protocol:** 208 configs in 6 families; select on 2024-01..2026-03; test once on 2021-11..2023-12 (never seen) and
2026-03-25..11-03 (holdout).

| Family | Median PF 2024-26 / 2021-23 / 2026 | Share of configs profitable |
|---|---|---|
| F1 expiry short fly | 0.98 / 1.13 / 1.04 | 50 / 59 / 57 % |
| F2 expiry short strangle | 0.83 / 1.06 / 0.71 | 23 / 62 / 8 % |
| F3 expiry ORB long (long gamma) | 0.80 / 1.26 / 1.46 | 11 / 89 / 81 % |
| F4 expiry momentum long | 0.92 / 1.26 / 1.59 | 25 / 92 / 100 % |
| F5 DTE1-2 straddle | 0.76 / 0.69 / 0.61 | 6 / 12 / 25 % |
| F6 ORB credit spread | 0.93 / 1.06 / 0.75 | 33 / 89 / 0 % |

**The selection rule failed out of sample:** the top selection-UPI config (fly, leg SL 80%, overall SL Rs 1,500) made
PF 1.56 in 2024-26 but PF 1.03 (DD Rs 27k) in 2021-23 and PF 0.54 (-Rs 18k) in 2026.
**A region that is positive in all three blocks exists** (found by looking at all blocks, so it is a candidate, not a
result): expiry-day fly at 09:20, wings by premium ~Rs 3, leg SL 30-50%. Over 2021-26, 1 lot:
SL50 / overall SL 3000 / trail-BE: +Rs 122.7k, PF 1.49, DD Rs 24.7k, worst day -Rs 3.9k, 64% winning months, 2023 -Rs 16.7k;
SL30 / overall SL 1500: +Rs 101.2k, DD Rs 19.8k, 56% winning months, 2023 -Rs 9.3k.
Long gamma (F3/F4) is profitable when the fly is weak in 2026 but is positively correlated with it (daily corr +0.24..+0.30),
and both lose in 2023: combinations raise DD (Rs 42-97k) without raising winning months.
VIX filter (skip if VIX at 09:15 < 12, thin premium): PF 1.38-1.49 -> 1.52-1.68 and DD -Rs 5-8k on two of three configs,
worse on the third, 2023 still negative or flat. A mild risk filter, not an edge.
**Against the user's targets:** nothing reaches DD <= 6% (Rs 12k) with 1 lot over 5 years, or >= 85% winning months
(best about 64%). Next: confirm the candidate region unchanged on BANKNIFTY 2021-24 and SENSEX 2023-26 (untouched instruments).

**Cross-instrument check, SENSEX (untouched instrument):** the NIFTY candidate region unchanged (09:20 fly, leg SL 30/50%,
overall SL Rs 1,500/3,000; wings by premium Rs 10, the pre-declared index-scaled value, and also Rs 3; lot 20):
2023-05..2024-09 (Dhan, 71 expiries) PF 1.08-1.10, net +Rs 6.5k..8.0k, DD Rs 16.9k..38.7k;
2024-10 -> (Upstox, 29 expiries so far) PF 0.55-0.77, net -Rs 7.5k..-17.7k.
**The NIFTY fly region does not transfer to SENSEX.** Together with the failed one-shot selection, this says the NIFTY
expiry-day fly "edge" is weak and period-dependent rather than a structural premium. BANKNIFTY 2021-24 check pending.

## Round 7: NIFTY calendar spread (2026-11-09), research/v13_calendar.py
Expiry-day calendar straddle: sell current-week ATM CE+PE, buy next-week ATM CE+PE (same strike, 1:1), 256 expiry days
2021-11..2026-11, grid entry {09:20, 10:30} x overall SL {2000, 3000, none} x front-leg SL {none, 50 %}, exit 15:15.
Python simulator validated against the Rust engine on the plain straddle: 255 common days, per-day |diff| median Rs 18,
same sign 99.2 %.
**Calendar: rejected.** PF 0.36-0.88 in every config and every block (2021-23 0.35-0.59, 2024-26 0.37-0.88, 2026 0.12-0.30),
5-year net -Rs 135k..-212k per lot. The long next-week legs lose on expiry day (IV falls into expiry, back-week theta, and
4 legs of costs) more than they hedge. Caveat (conservative for 2021-24): Dhan next-week data covers ATM+/-3 only.
Side finding (control): plain short ATM straddle at 09:20, leg SL 50 %, overall SL Rs 2,000: 5-year PF 1.72-1.76,
DD Rs 17.6k, but the 2026 holdout PF 0.76 (Strategy B: 1.31), about 1.7x the margin of Strategy B, and no protection
against a gap through the stops. Not adopted; Strategy B stays the candidate.

## Round 8: trend days and adjustments (2026-11-09)
Last week NIFTY rallied 23,053 -> 25,030 (+8.6 %, 30 Oct -> 6 Nov; 6 Nov +492 pts open-to-close).
Strategy B trades only on expiry days: 27 Oct +Rs 1,256, 3 Nov (+229 pt trend day) +Rs 3,724.
Run on EVERY day 26 Oct - 6 Nov with the same rules (4-6 Nov from Upstox live-contract history): total +Rs 11,852 for one lot;
6 Nov +Rs 5,238 (short CE stopped 09:51 at -83.6 pts, short PE decayed 192 -> 36 = +156.6 pts); only loss -Rs 3,317 on 28 Oct, a
reversal (CE stopped 13:00, then overall stop 14:38).
**Trend vs whipsaw over 252 expiry days (2022-26):** big trend days are the best days (|09:20->15:15 move| >= 1.5 %: 9 days,
avg +Rs 5,115, 89 % winners; 0.8-1.5 %: PF 1.6-2.3). Losses come from moderate moves (0.4-0.6 %: PF 0.55) and whipsaws
(range minus trend >= 0.7 %: 39 days, avg -Rs 1.1k..-1.4k, 28-31 % winners).
**Adjustment tested: re-entry after a stop** (pre-declared, 2 variants): RE-COST x1: 5-year PF 1.20, net Rs 58.9k, 2026 holdout PF 0.76;
RE-ASAP x1: PF 1.22, net Rs 61.3k, DD Rs 50k, holdout PF 0.82. Both worse than B (PF 1.50, holdout 1.31). **No adjustment adopted.**
Note: the 5-year cache now contains 4-6 Nov (contracts expiring 9 Nov); until today's data is added, 6 Nov carries tdte 0 because
the 9 Nov expiry is not yet in the cache. Strategy B backtests should use --date-to 20261103 until the cache is refreshed.

## Round 9: simulator, features, where the premium is (2026-11-09)
**New Python simulator** (`research/sim/`: store.py day store, engine.py, features.py): multi-day positions, adjustments,
signal-driven entries, approximate SPAN margin. Validated against opt_engine on Strategy B over 5 years: net Rs 1,23,188 vs
Rs 1,22,694 (0.4 %), per-day |diff| median Rs 6, same sign 100 % (validate.py). 5 years run in ~2-9 s.
Found while validating: after both shorts stop, opt_engine/AlgoTest keeps the wings to 15:15 (12-Sep-2024 the CE wing ran
Rs 3.65 -> Rs 161). The live executor and paper script closed the wings; fixed to keep them, matching the backtest.
**Feature table** (1,232 days, values known at 09:20): gap, opening range, prior-day return/range, RV5/RV20, VIX + change
(2022+), ATM IV (straddle-implied), next-expiry IV, IV/RV, IV rank, PCR (+/-2 % band), PCR change, max-pain distance, OI walls.
**Volatility risk premium by days-to-expiry** (sell ATM straddle at 09:20, 1 lot, before costs):
| tdte at entry | intraday (09:20 -> 15:15) | held to expiry | 5 % worst week, held |
|---|---|---|---|
| 0 | +Rs 290 | +Rs 287 | -Rs 12.1k |
| 1 | +Rs 86 | +Rs 756 | -Rs 14.2k |
| 2 | +Rs 149 | +Rs 1,353 | -Rs 20.6k |
| 3 | +Rs 143 | +Rs 1,283 | -Rs 23.2k |
| 4 | -Rs 42 | +Rs 1,631 | -Rs 25.1k |
Intraday selling on non-expiry days earns about the round-trip cost (~Rs 160): no edge, which explains every earlier failure
there. The premium is earned overnight: holding from 2-4 days before expiry earns ~5x the expiry-day edge per lot, with fat
tails. IV/RV5 buckets do not sort the outcomes (RV5 is too noisy).
Lesson from the first positional smoke test: wings priced at Rs 5-10 sit ~1,100 points away at 3 DTE; on the 3-Feb-2026
~3 % gap-up, a 1-lot "fly" lost Rs 49.8k in one morning. Multi-day positions need wings by distance (v14 grid uses 1.5 % / 3 %).

## Round 10: strictly intraday basket, every day (2026-11-09), research/v15_intraday.py
Store now carries option lows (long stops / short targets were checked on open/close before; re-validated vs engine: unchanged
for Strategy B). 32 base configs on all 1,230 days (1 lot, exits by 15:15):
| Family | PF 2021-23 | PF 2024-26 | PF 2026 |
|---|---|---|---|
| SELL 09:20/10:00 straddle + wings 1-2 %, leg SL 30/50 %, trail, overall SL (16) | 0.57-0.79 | 0.69-0.87 | 0.54-0.89 |
| BUY ORB 09:30/09:45 breakout, SL 25/35 %, ratchet trail (8) | 0.81-0.96 | 0.84-0.96 | 0.64-0.78 |
| BUY momentum +15/25 % premium trigger (8) | 0.86-0.99 | 0.79-0.97 | 0.73-1.06 |
Signal layer: 288 tercile filters (gap, opening range, prior-day range, VIX, IV, IV rank, IV/RV5, PCR, tdte) chosen on
2024-26: 20 reached selection PF >= 1.2; the only one that held in both test blocks is tdte = 0 (expiry day, i.e. Strategy B's
family). OI/PCR, VIX, IV and opening-range filters all failed out of sample.
Cost sensitivity (5 years): best buy (MOM 25 %) PF 0.98 realistic -> 1.02 without slippage -> 1.06 without slippage and charges;
ORB 0.88 -> 0.92 -> 0.97; every-day sell 0.81 -> 0.95 -> 1.21. Realistic friction (~Rs 300-400 per trade) consumes any edge.
**Conclusion: no intraday NIFTY option strategy outside expiry day survives realistic costs in 5 years of data.**
Positional preview (v14, stopped at 193/576 configs because the user requires intraday only): weekly fly entered 2 trading days
before expiry with wings 3 % beyond the shorts is positive in all three blocks in 33 configs, e.g. T-2 15:15 entry, no leg SL,
weekly stop Rs 4k, exit expiry morning: PF 1.26 / 1.35 / 1.42, ~Rs 30k/yr per lot, but 5-year DD Rs 47k and worst day -Rs 22k
(overnight gaps), margin ~Rs 1.15L. Parked, not pursued.

## Round 11: intraday NIFTY futures (2026-11-09), research/fut/
Data: index 1-min as the futures proxy, 2,915 days 2015-01-09..2026-11-06 (debashis74017 + Upstox, joined cleanly). Costs at
today's rates: futures STT 0.05 % of sell notional since 1-Apr-2026 (verified: Budget 2026, effective 1 April) -> ~Rs 962 per
round trip per lot (~14.8 pts) + 1 pt slippage per fill (+1 on stops). Flat by 15:25. Select on 2015-2020, test 2021-23 and 2024-26.
**v16, 52 configs (ORB 36, momentum-into-close 8, EMA 2, mean reversion 2, gap 4): every config PF < 1 in every block**
(ORB 0.57-1.02 / 0.61-0.97 / 0.60-0.90; momentum-into-close 0.25-0.66; EMA 0.45-0.66; MR 0.47-0.89; gap 0.33-0.91).
**Gross edge exists:** with zero costs and zero slippage, 11-year PF: ORB 1.15-1.29 (Rs 63-80k/yr per lot), EMA 20/50 1.29
(Rs 1.44L/yr); MR and gap ~1.0-1.09 (no edge). With the pre-April-2026 STT (0.02 %) the slower ORBs were marginally positive
(PF 1.02-1.05). The trend edge is ~8 pts per trade against ~19 pts of cost.
**v16b, fewer bigger trades + day filters (36 variants):** nearly all fail out of sample; best survivor ORB 11:15 + 0.1 % buffer
on gap days (|gap| >= 0.39 %): PF 1.30 / 1.03 / 1.14, Rs 3-17k/yr per lot on ~20 trades/yr: not meaningful.
**v17, the same signals executed with deep ITM options (to avoid futures STT), real option prices 2021-11..2026-11:**
ORB ITM-200 PF 1.04-1.11 (2021-23) / 0.94-0.97 (2024-26); ITM-400 0.82-0.95; EMA flip 0.59-0.85. ITM spreads and residual
time value eat the STT saving.
**Conclusion after rounds 9-11:** across 5 years of NIFTY options and 11 years of NIFTY futures, no intraday strategy outside
expiry day survives realistic costs out of sample. The only robust intraday edge found is the expiry-day iron fly (Strategy B).
Trend-following has a real gross edge that today's STT (futures) or option friction consumes; costs, not signal discovery, are
the binding constraint.

## Round 12: overnight weekly fly (Strategy W) and the B + W portfolio (2026-11-09)
v14 grid completed: 576 positional configs. Profitable share: 2021-23 39 %, 2024-26 37 %, 2026 66 %.
**Pre-declared pick (research/v14_select.py, committed before the grid finished) failed:** fly T-4 15:15, Rs 20 wings, weekly
stop Rs 4k: PF 1.39 in 2024-26 but 0.77 (-Rs 38.7k/yr, DD Rs 1.08L) in 2021-23. Selection on 2024-26 is weakly informative
(53 % of 2024-26 winners also win 2021-23 vs 30 % of losers; 37 % win both test blocks).
**Robust structure:** of 80 configs profitable in all three blocks, 69 are flies and 52 use wings 3 % beyond the shorts. Family
"fly + 3 % wings + 15:15 entry + no leg SL" (24 configs, none picked): median PF 1.27 / 1.15 / 1.10, profitable in 92 / 96 / 79 %.
(Recognised after seeing all blocks: strong evidence, not a clean holdout.)
**Strategy W** (remaining choices fixed by reasoning: T-3, weekly stop Rs 8k, no adjustments, exit 09:20 on expiry morning):
5-year PF 1.17, Rs 28.9k/yr per lot, DD Rs 64.2k, bootstrap p95 DD Rs 1.35L, worst day -Rs 17.0k (2-Mar-2026 gap), 56 % winning
months, longest losing run 7 months; blocks 1.23 / 1.09 / 1.35; slippage x2 PF 1.12. Daily correlation with Strategy B -0.01.
**Portfolio on Rs 5L:** B 2 lots Rs 49.6k/yr (9.9 %), DD 9.9 %, p95 Rs 81.6k; **B 2 lots + W 1 lot Rs 78.5k/yr (15.7 %), DD 12.4 %,
p95 Rs 1.33L, 64 % winning months**; B 2 + W 2 Rs 1.07L/yr but DD 22.3 % (too much for Rs 5L). Margins never stack (W exits 09:20
on expiry morning as B enters). Sim margin for W median Rs 1.12L vs Upstox fly +/-800 Rs 1.06L.
Executor: execution/upstox_weekly.py (state file across days, product D, holiday-aware T-3 detection, weekly stop every minute,
exit 09:20 expiry morning, ledger + kill-switch); paper-tested 9-Nov-2026. Card: STRATEGY_W_CARD.md.

## Round 13: overnight momentum (Strategy M), margin facts, new portfolio (2026-11-10), research/r13/
Goal (user): more profit per rupee of margin, lower drawdown, more winning months, expiry and non-expiry days.
**Premium decomposition (s1_decomp.py, gross points per unit, short option):** no leg has a large unconditional premium. ATM legs
earn 0-5 pts per segment (|t| < 1.5) against ~1.5 pts of cost per leg; the only t > 2.5 cells are 1-3 % OTM puts at tdte 0-1
(premium Rs 3-18, earn 1.5-4 pts, worst -110..-330): pennies in front of a steamroller. Unconditional selling has no usable edge.
**Overnight drift (idx.py, 2,912 nights 2015-2026):** spot 15:20 -> next 09:20 = +6.9 bp (t 5.7), intraday -2.6 bp. But the
synthetic future (K + C - P) shows the basis is 17.7 pts at 15:20 and 9.2 pts at 09:20 (carry 4.7 pts per calendar day): the
tradable unconditional overnight return 2021-26 is +0.05 pts. **The famous overnight drift is carry, not alpha.**
**Conditional on the day's move it is real:** after 09:20->15:20 > +0.3 %: +8.2 bp net of carry and 2 bp cost, t 3.5, n 876,
positive 11 of 12 years, monotonic in the size of the move. No stable sub-filter (weekday, weekend, VIX, trend flip sign between
2015-20 and 2021-26). Short side with futures: negative 2015-2021, positive 2022-26.
**Real option prices 2021-26 (s2/s4/on2.py, 1 lot, all costs):**
| Structure (thr 0.3 %) | Rs/yr | PF | DD | WM | note |
|---|---|---|---|---|---|
| up: synthetic long | 68.0k | 1.41 | 51.5k | 62 % | margin 1.83L |
| up: long ATM call | 28.3k | 1.33 | 34.8k | 52 % | no margin, pays theta |
| up: short ATM put | 39.6k | 1.49 | 25.8k | 69 % | |
| down: short ATM call | 32.7k | 1.33 | 29.1k | 65 % | |
| down: synthetic short | 76.0k | 1.36 | 58.6k | 62 % | |
| **M = short put after up / short call after down** | **72.3k** | **1.42** | **35.0k** | **69 %** | Sharpe 1.58, every year positive |
| synthetic both ways | 144.0k | 1.40 | 70.3k | 67 % | twice the gap risk |
Rejected: put/call credit spreads with 1-2 % wings (wing decay eats the edge, PF 0.9-1.1), call debit spreads (PF 0.88-1.02),
all-nights synthetic long (PF 0.90), ITM calls (2021-23 numbers not trusted: far strikes are stale in the Dhan rolling data).
**Unseen data, 2017-2020 monthly options (zen.py, on2_zen.py):** M unchanged: +3.5k, +2.2k, +21.3k, +32.7k, PF 1.13 (index 2.3x
lower, monthly options costlier). Down leg alone PF 1.22; up leg alone PF 1.04.
**Robustness (m_robust.py):** 15 variants (threshold 0-0.5 %, entry 15:10/15:25, exit 09:17/09:25/09:45, slippage x2, wings):
5-year PF 1.26-1.48 for all naked variants; 4 % wing PF 1.37 in 2024-26 (pre-2024 wing prices untestable).
**Real margins (margins.py, Upstox 10-Nov-2026, non-expiry):** naked straddle 1.87L; iron fly +-200 / +-800 / +-1200 = 0.68L /
0.91L / 1.15L; put credit spread ATM/-200 0.41L; naked short ATM option 1.68L, with 4 % wing 0.84L; synthetic long 1.83L, with
-500 put 0.70L; long call = premium. Expiry day adds 2 % ELM (Rs 32.6k) per short leg, so margin is driven by the number of
short legs, not by the wing price.
**Portfolio (portfolio.py, Rs 5L):** B2+W1 76.8k/yr, DD 12.4 %, 64 % winning months -> **B2+W1+M1 149.0k/yr (29.8 %), DD 9.1 %,
p95 DD 90k, 75 % winning months, no losing year, Sharpe 2.0.** Correlations: M vs B -0.01, M vs W -0.10.
Card: STRATEGY_M_CARD.md. Next: executor for M (paper), far-wing prices from live chains, bid/ask recorder at 15:20 and 09:20.

## Round 14: safest M, executor, intraday afternoon momentum (2026-11-10), research/r13/mom.py
**Index study, 4 blocks 2015-2026:** (a) M's up signal aligned with the 5-day trend: +13.7 bp a night net of carry, t 5.8, t >= 2.0 in
every block; against the trend +3.2 bp (t 0.6); down signals +4.1 / -0.4 bp (not significant). (b) Intraday continuation: the move
09:20 -> 12:00 (|r| > 0.3 %) continues to 15:20 by +8.1 bp (t 4.3, positive in all blocks, both directions); 13:00 +6.9 (t 4.8).
(c) Gap follow-through: nothing (2.3 bp, t 0.9). (d) Nights after flat days by trend: weak (one block).
**M variants (1 lot, naked; 2021-26 | 2017-20):** both legs PF 1.42, 72.3k/yr, DD 35.0k | PF 1.13, DD 49k; **both + trend filter
PF 1.36, 44.9k/yr, DD 38.9k | PF 1.51, 30.7k/yr, DD 19.9k**; up + filter PF 1.66, 30.4k/yr, DD 24.5k | PF 1.72, DD 11.0k (10/10 years).
With wings, 2024+ only: both 4 % PF 1.28, 49.7k/yr, DD 35.3k; both + filter 4 % 34.9k, DD 37.5k; **both + filter 3 % (M-safe) PF 1.25,
29.5k/yr, DD 34.2k**; up + filter 4 % PF 1.36, 17.2k, DD 25.1k.
**Portfolio 2024+ (Rs 5L):** B2+W1 92.1k/yr, DD 12.4 % -> B2+W1+M-safe 121.7k/yr (24.3 %), DD 8.3 %, p95 87k, 71 % winning months.
**N = intraday afternoon momentum with a short ATM option (12:00 -> 15:20, non-expiry days): rejected.** PF 1.23, 20.7k/yr, DD 44k,
2022 negative; 13:00 entry PF 1.07 and fails 2021-23 and the 2026 holdout; 2017-20: 12:00 loses 42k in 2020; with a 3 % wing PF 1.13.
The index effect is real but half of it (delta 0.5) minus option costs leaves too little. Lead, not tested further: on expiry days
the same trade (all days incl. expiry, naked) made 38.9k/yr PF 1.34, positive every year 2021-26; not tested separately or with wings.
**Executor:** execution/upstox_m.py (paper default), paper-tested with forced entry/exit.
