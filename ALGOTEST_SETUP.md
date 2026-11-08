# AlgoTest setup — NIFTY Expiry-Day Iron Fly

Every value below is an AlgoTest builder field (docs.algotest.in). Backtest it on AlgoTest with **taxes & charges ON and 0.5% slippage** before going live, then forward-test (paper) for at least 4–6 expiries.

## Strategy (Backtest → Create strategy → Intraday)

| Field | Value |
|---|---|
| Instrument settings | Index: NIFTY · Underlying from: Cash |
| Strategy type | Intraday |
| Entry time | 09:20 |
| Exit time | 15:15 |
| No re-entry after | 14:30 |
| Legwise settings → Square off | Partial |
| Legwise settings → Trail SL to break-even | On – SL legs |

## Legs (Leg builder)

| # | Segment | Lots | Position | Option type | Expiry | Strike criteria | Stop loss | Target | Trail SL | Re-entry on SL | Simple momentum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Options | 1 | Sell | Call | Weekly | Strike Type: ATM | 60% | - | - | - | - |
| 2 | Options | 1 | Sell | Put | Weekly | Strike Type: ATM | 60% | - | - | - | - |
| 3 | Options | 1 | Buy | Call | Weekly | Strike Type: OTM12 | - | - | - | - | - |
| 4 | Options | 1 | Buy | Put | Weekly | Strike Type: OTM12 | - | - | - | - | - |

## Overall strategy settings

| Field | Value |
|---|---|
| Overall stop loss | MTM ₹2,000 (per 1× quantity; AlgoTest multiplies by the quantity multiplier) |

## Portfolio, sizing and execution

| Field | Value |
|---|---|
| Portfolio → DTE filter / Auto-activation | DTE 0 (Tuesday (expiry day) on the Tuesday-expiry calendar) |
| Quantity multiplier | ₹2L capital: 1× · ₹3L capital: 1× (expiry-day margin includes SEBI's extra 2% ELM) |
| Execution → Entry/Exit order type | Limit (market orders are disabled since 1-Apr-2026); limit buffer 5–8% of premium, convert-to-market/chase on |
| Execution → Delay entry by | 3–5 s on the SELL legs so the BUY (hedge) legs fill first and you get the hedge margin benefit |
| Execution → Trade monitoring | Candle Close (matches how the backtest evaluates Overall SL / Target / Lock) |
| Execution → TGT/SL ref price | Traded |
| Execution → Product | NRML (or make sure exit time is before your broker's MIS auto square-off, e.g. IIFL/Upstox 15:15) |
| Execution → Auto square-off on margin error | On |

## Margin you need (calibrated on the exchange SPAN file, NIFTY ≈ 25,000, lot 65)

- Expiry day, 1 lot of this iron fly: SPAN ≈ ₹40k + exposure ≈ ₹62k + SEBI expiry-day ELM 2% ≈ ₹65k → **≈ ₹1.67–1.74 lakh**.
- 2 lots therefore need ≈ ₹3.5 lakh, so **₹2L and ₹3L both run 1 lot** (quantity multiplier 1). A ₹3L account keeps ~₹1.3L as buffer.
- Always place the BUY wings first (Delay entry on SELL legs), otherwise the broker blocks naked-short margin (~₹2.2L+).

## Second expiry-day strategy for ₹3L: ORB directional hedged spread (v4)

| Field | Value |
|---|---|
| Strategy type / index | Intraday · NIFTY · Underlying from Cash |
| Entry time | 09:16 (range start) |
| Exit time | 15:15 |
| Portfolio DTE / auto-activation | DTE 0 only (expiry day) |
| Overall SL | MTM ₹2,000 |

| # | Position | Type | Strike | SL | Range Breakout |
|---|---|---|---|---|---|
| 1 | Sell | PE | ATM | 40% | High of 09:16–09:31 on **Underlying** |
| 2 | Buy | PE | OTM4 | – | High of 09:16–09:31 on **Underlying** |
| 3 | Sell | CE | ATM | 40% | Low of 09:16–09:31 on **Underlying** |
| 4 | Buy | CE | OTM4 | – | Low of 09:16–09:31 on **Underlying** |

- An upside break enters a bull put spread and a downside break enters a bear call spread. Margin ≈ ₹0.8L when one side triggers.
- Set **Stop monitoring after 15:14** on both strategies.
