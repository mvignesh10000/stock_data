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

## Capital-specific wing choice (v3)

- **₹2L account:** change legs 3–4 to **OTM8** (±400). Margin ≈ ₹1.54L, which keeps a ~23% cash buffer. Backtest net ₹72k vs ₹93k with OTM12, same rules.
- **₹3L account:** keep **OTM12** (±600). Margin ≈ ₹1.68L, buffer ≈ 44%.
- Add a **Broker-level Stop Loss of ₹4,000** each morning (Algo Trade → Add Settings). Do **not** set a broker-level target.
- Do not add an ORB buying strategy or a VIX switch: both were tested and rejected (see WINNING_STRATEGIES.md §v3).
