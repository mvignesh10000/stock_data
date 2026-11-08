# WINNING_STRATEGIES — NIFTY intraday non-directional selling (v2, realistic engine)

Generated 2026-11-08. Interactive report: `reports/strategy_report.html`. AlgoTest field-by-field setup: `ALGOTEST_SETUP.md`.

## Bottom line

- After the external review the engine was made realistic: slippage, intra-minute wicks, SPAN margin with the expiry-day ELM, and trading-day DTE. Under it, **the earlier P1 portfolio does not survive** (holdout Calmar 11.6 → 0.7) and the DTE 4–6 strategy loses money out of sample.
- **One strategy survives an honest anchored walk-forward: the expiry-day (trading DTE 0) iron fly.** In the walk-forward every quarter's parameters were chosen only from earlier data; the procedure picked the same structure, entry time and stop logic each quarter.
- Intraday selling on DTE 1, 2, 3 and 4 (morning or afternoon) **lost money out of sample** after costs. So nothing is deployed on Mon/Wed/Thu/Fri; the capital is idle on purpose.
- **Expected (walk-forward, 1 lot): ≈ ₹24,221/yr (~12% on ₹2L), max DD ≈ ₹15,417.** Full-sample optimised (an upper bound): ₹93,372 over 2.2 yrs, DD ₹12,423, PF 1.81.
- The edge is **shrinking**: 2024 ₹59,722, 2025 ₹31,351, 2026-Q1 ₹2,300 (1 lot).
- **Statistical caution:** the Deflated Sharpe ratio is 0.07 at 1,000 effective trials. 117 expiry days are too few to prove the edge is not luck. **Paper-trade first.**

## The strategy

```json
{
 "kind": "algotest",
 "name": "NIFTY_ExpiryDay_IronFly",
 "entry_time": "09:20",
 "exit_time": "15:15",
 "no_reentry_after": "14:30",
 "dte": [
  0
 ],
 "underlying": "cash",
 "legs": [
  {
   "side": "sell",
   "opt": "CE",
   "strike": {
    "mode": "atm"
   },
   "sl": {
    "kind": "pct",
    "value": 60
   }
  },
  {
   "side": "sell",
   "opt": "PE",
   "strike": {
    "mode": "atm"
   },
   "sl": {
    "kind": "pct",
    "value": 60
   }
  },
  {
   "side": "buy",
   "opt": "CE",
   "strike": {
    "mode": "otm",
    "n": 12
   }
  },
  {
   "side": "buy",
   "opt": "PE",
   "strike": {
    "mode": "otm",
    "n": 12
   }
  }
 ],
 "square_off": "partial",
 "trail_to_breakeven": "sl_legs",
 "overall": {
  "sl_mtm": 2000
 },
 "sizing": {
  "mode": "fixed",
  "multiplier": 1
 }
}
```

| Window | Trade days | Net | ROI/yr | Max DD | Calmar | PF | Win % | Exp/day | Worst day |
|---|---|---|---|---|---|---|---|---|---|
| Full sample, 1 lot (₹2L) | 117 | ₹93,372 | 21.4% | ₹12,423 | 3.44 | 1.81 | 54.7% | ₹798 | ₹-3,345 |
| Full sample, ₹3L margin-sized | 117 | ₹145,248 | 22.1% | ₹23,713 | 2.80 | 1.92 | 55.6% | ₹1,241 | ₹-5,610 |
| Walk-forward OOS v6 (clean), 1 lot | 91 | ₹41,902 | 12.1% | ₹15,417 | 1.59 | 1.44 | - | - | ₹-3,577 |
| Walk-forward OOS v7-H1, 1 lot | 91 | ₹60,585 | 17.5% | ₹13,371 | 2.65 | 1.66 | - | - | ₹-3,747 |

₹3L note: the 2-lot days are all before 20-Nov-2024. Since the 2% expiry-day ELM, ₹3L funds only 1 lot, so going forward the ₹3L result ≈ the ₹2L result.

## Hard-gate check (your spec)

- Expectancy ≥ ₹450/lot-day: **pass** (₹798).
- Worst day ≤ 1.5% of capital (₹3,000): **fail** (₹3,345); ≤ 2.5× p90 win: pass.
- ≤ 15% losing months: **fail** (30%). With ~4 trades/month some red months are unavoidable.
- Max underwater ≤ 25 active days: **pass** (15).

## Stress tests (1 lot)

| Scenario | Net | Max DD |
|---|---|---|
| Base (wicks + 0.5%/1% slippage) | ₹93,372 | ₹12,423 |
| No synthetic wicks (optimistic) | ₹107,239 | ₹12,423 |
| Slippage ×2 (1% / 2% / ₹0.20 min) | ₹74,451 | ₹12,642 |
| Monte-Carlo DD 95th / 99th pct | - | ₹27,409 / ₹32,747 |
| AlgoTest platform fee (100 credits/28 days) | −₹2,700 total | - |

Same rules forced onto every day (shows why the DTE-0 filter is structural):

| Trading DTE | Net (1 lot) | Days |
|---|---|---|
| 0 | ₹93,372 | 117 |
| 1 | ₹-22,078 | 106 |
| 2 | ₹-11,234 | 88 |
| 3 | ₹-29,132 | 79 |
| 4 | ₹-18,754 | 30 |
| 5 | ₹-12,305 | 31 |
| 6 | ₹-69,097 | 99 |

## Monthly P&L (₹, 1 lot)

| Year | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | Year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2024 | 2,298 | 7,254 | 7,177 | -3,663 | 4,935 | 6,193 | -1,046 | 11,051 | -7,883 | 8,737 | 20,696 | 3,973 | **59,722** |
| 2025 | 13,357 | 333 | -6,206 | 9,198 | -712 | 3,037 | 6,274 | -966 | 2,612 | 2,088 | 1,358 | 978 | **31,351** |
| 2026 | -5,790 | 14,762 | -6,672 |  |  |  |  |  |  |  |  |  | **2,300** |

Quarterly: 2024-Q1: ₹16,728, 2024-Q2: ₹7,465, 2024-Q3: ₹2,122, 2024-Q4: ₹33,406, 2025-Q1: ₹7,484, 2025-Q2: ₹11,523, 2025-Q3: ₹7,920, 2025-Q4: ₹4,424, 2026-Q1: ₹2,300

## Worst 5 days (1 lot)

| Date | DTE | Net | Stops | Final exit |
|---|---|---|---|---|
| 20260317 | 0 | ₹-3,345 | 2 | OVERALL_SL @ 11:26 |
| 20240229 | 0 | ₹-2,900 | 2 | OVERALL_SL @ 10:11 |
| 20240606 | 0 | ₹-2,891 | 1 | OVERALL_SL @ 11:47 |
| 20240718 | 0 | ₹-2,847 | 2 | OVERALL_SL @ 11:13 |
| 20240215 | 0 | ₹-2,812 | 2 | OVERALL_SL @ 09:49 |

## What was rejected (walk-forward out-of-sample, 1 lot)

| Day | Search | OOS net | OOS PF |
|---|---|---|---|
| DTE 1 | morning grid (v6) | ₹-13,496 | 0.56 |
| DTE 2 | morning grid (v6) | ₹-23,091 | 0.75 |
| DTE 3 | morning grid (v6) | ₹0 | 0.00 |
| DTE 4 | morning grid (v6) | ₹-20,015 | 0.71 |
| DTE 1 | afternoon grid (v7-H2) | ₹-18,886 | 0.44 |
| DTE 2 | afternoon grid (v7-H2) | ₹0 | no stable config |
| DTE 3 | afternoon grid (v7-H2) | ₹0 | no stable config |
| DTE 4 | afternoon grid (v7-H2) | ₹0 | no stable config |

Earlier strategies re-tested on the realistic engine (holdout Calmar / PF, full-period net):

| Strategy | Model | Holdout Calmar | Holdout PF | Full net | Full DD |
|---|---|---|---|---|---|
| S1 | As first reported | 5.05 | 1.92 | ₹85,385 | ₹6,068 |
| S1 | + realistic slippage | 4.43 | 1.81 | ₹87,678 | ₹6,334 |
| S1 | + intra-minute wicks | 3.24 | 1.53 | ₹71,629 | ₹6,440 |
| S3 | As first reported | 6.44 | 1.55 | ₹53,219 | ₹4,760 |
| S3 | + realistic slippage | 2.98 | 1.29 | ₹41,385 | ₹5,651 |
| S3 | + intra-minute wicks | -1.79 | 0.8 | ₹20,749 | ₹8,625 |
| P1 | As first reported | 11.59 | 1.69 | ₹138,604 | ₹5,737 |
| P1 | + realistic slippage | 6.96 | 1.48 | ₹129,063 | ₹6,451 |
| P1 | + intra-minute wicks | 0.7 | 1.04 | ₹92,378 | ₹8,472 |

## Caveats

- 2025–26 option data is minute LTP; true intra-minute highs are modelled with wicks calibrated on true OHLC (validated on Oct–Dec 2024). True OHLC for 2025–26 (e.g. Upstox expired-instrument API) would remove this approximation.
- 551 trading days include only 117 expiry days. The Deflated Sharpe is low, and the out-of-sample edge (PF 1.44–1.66) is real but modest.
- Results use today's lot (65) and today's charges for every year so they read as 'what this would make now'.
- The AlgoTest backtest checks overall SL at candle close; live trading checks it on LTP, so live exits can be slightly earlier or later.
- This is research, not investment advice.
