# Paper-trading configuration (final, 2026-11-12): B + W + M-safe on NIFTY

For the coding agent. Everything below is a **paper** run: no live orders, no real money. Existing executors (paper is their default):
`execution/run_b.py` + `upstox_ironfly.py` (B), `execution/upstox_weekly.py` (W), `execution/upstox_m.py` (M). Rationale and evidence:
`STRATEGY_CARD.md`, `STRATEGY_W_CARD.md`, `STRATEGY_M_CARD.md`, `research/r15/REVIEW.md`. Do not change a rule below without the owner's approval:
the rules were chosen from backtests and any tweak invalidates them.

## 0. Common rules
| Item | Setting |
|---|---|
| Instrument | NIFTY weekly options (NFO). Lot = 65. Expiry day = Tuesday (previous trading day if holiday). Check `/v2/market/holidays` daily |
| Size in paper | 1 lot each strategy (planned live mix on Rs 5L: B 2 lots + W 1 lot + M-safe 1 lot; record P&L per lot so it scales) |
| Orders | limit orders with 8 % price buffer, re-priced every 3 s, wings (buys) always first on entry, shorts first on exit |
| Fill model (paper) | fill at the live bid/ask if available, else last price +/- 0.5 % (never at mid); stop fills +1 % extra |
| Product | B intraday (MIS); W and M carry-forward (NRML / "D") |
| Charges | brokerage Rs 20/order, STT 0.15 % on option sell premium, exchange 0.03503 %, SEBI, stamp 0.003 % on buys, GST 18 % |
| No profit targets, no re-entry, no adjustments in any strategy (targets and re-entry were tested and hurt) | |
| Log per trade | signal inputs, intended price (the 1-min close the backtest would use), actual paper fill, slippage %, P&L net of charges, reason for exit |
| Data for the audit | also record 1-second bid/ask of every leg at entry and exit minutes (`etl/bidask_recorder.py`) to measure real spreads |

## 1. Strategy B: expiry-day iron fly (intraday)
| Item | Setting |
|---|---|
| Day | expiry day only |
| Entry | 09:20:00 IST. SELL ATM CE + SELL ATM PE; BUY one CE and one PE whose premium is closest to Rs 3 (wings first) |
| Stop-loss (leg) | each short leg: SL at **+50 %** of its entry price (SL-limit; assume +1 % extra slippage) |
| After one leg stops | move the other short leg's stop to its entry price (breakeven) |
| Stop-loss (overall) | close everything if position MTM <= **-Rs 3,000 per lot** |
| Target | none |
| Exit | 15:15 all legs, shorts first. Wings stay open after both shorts stop, exit them at 15:15 |
| Skip | non-expiry days. No other filter |
| Margin check | ~Rs 1.6L per lot (paper: log it, do not block) |
| Expected (backtest, 1 lot) | PF 1.50, ~Rs 24.7k/yr, 55 % winning days, max DD Rs 24.7k, worst day -Rs 3.9k |
| Kill-switch (paper alarm) | DD from peak > Rs 40k per lot, 4 losing months in a row, average slippage > 2 %/fill over 8 expiries |

## 2. Strategy W: weekly overnight iron fly
| Item | Setting |
|---|---|
| Entry | **3 trading days before expiry at 15:15** (Wednesday for Tuesday expiry; shift for holidays by trading days, not calendar days) |
| Legs | SELL ATM CE + ATM PE; BUY CE and PE **3 % of spot beyond each short strike**, rounded to the 50 grid (wings first). Contract = the coming expiry |
| Stop-loss | no leg stops. **Weekly stop: close everything if MTM since entry <= -Rs 8,000 per lot**, checked every minute while the market is open (overnight gaps cannot be stopped; wings cap the loss at ~Rs 39k/lot) |
| Target | none |
| Exit | **09:20 on expiry morning**, shorts first, then wings (B enters right after) |
| Expected (backtest) | PF 1.17, ~Rs 28.9k/yr, 56 % winning months, DD Rs 64k, worst day -Rs 17k |
| Kill-switch (paper alarm) | DD from peak > Rs 1.0L per lot or 6 losing months |

## 3. Strategy M-safe: overnight momentum premium (signal nights only, ~75-90 per year)
| Item | Setting |
|---|---|
| Reference | NIFTY spot at 09:20 (close of the 09:19 candle) |
| Signal time | 15:19:30. r = spot / spot(09:20) - 1 |
| UP signal | r > **+0.30 %** AND spot > daily close 5 trading days ago. Trade: BUY PE 3 % of spot below ATM (wing, first), then SELL ATM PE |
| DOWN signal | r < **-0.30 %** AND spot < daily close 5 trading days ago. Trade: BUY CE 3 % above ATM (wing, first), then SELL ATM CE |
| No signal | no trade (about 60 % of days) |
| Contract | nearest weekly expiry with at least 1 calendar day left (on expiry day use next week's contract; the night before expiry uses the expiring one) |
| Entry | 15:20 |
| Stop-loss | none overnight (it cannot act); the 3 % wing is the stop. Max loss ~Rs 42k per lot |
| Target | none |
| Exit | **09:20 next trading day**, short leg first, then the wing. Never carry into the day session; if the exit fails, log an ALERT and retry every 3 s until done |
| Wing/strike rounding | nearest 50 strike; wing premium must be > 0, skip the trade (log it) if the wing has no quote |
| Expected (sim 2024-26 / my replication) | PF 1.25 / 1.40, Rs 29.5k / 43.8k per yr, DD Rs 34k / 26k, 66-73 % winning months |
| Kill-switch (paper alarm) | live DD from peak > Rs 90k per lot, or last 12 months negative (needs >= 6 months of history) |
Both M and W can be open the same night (~Rs 1.8L margin together). On expiry morning the order is: exit W and M at 09:20, then B enters.

### 3a. Shadow variants for M (log only, same signals, no extra orders)
Run the same signal in parallel and keep a separate ledger so the real evidence builds without extra risk. Required addition to the executor: log India VIX
(`NSE_INDEX|India VIX`) at 15:19.
| Shadow | Rule | Why |
|---|---|---|
| M-vix | M-safe, but skip the DOWN signal when VIX(15:19) > 20 | backtest PF 1.45 -> 1.69 and DD 38k -> 29k, but cut-off sensitive (22 shows no gain) and chosen after the fact |
| M-thr05 | M-safe with threshold 0.50 % | fewer trades (~120 vs ~190), PF 1.72, DD Rs 14k in a 2-year replication |
| M-naked | no wing | measures what the wing costs (~36 % of profit) |
Promote a shadow only after >= 40 shadow trades and with the owner's approval.

## 4. Daily schedule (IST)
| Time | Action |
|---|---|
| 09:12 | start: holiday check, load state, restore any open M/W position from state files, check data feed |
| 09:20 | if M open from last night: exit M. If W due to exit (expiry morning): exit W. Record spot(09:20) for M. If expiry day: enter B (after exits finish) |
| 09:20-15:15 | B leg stops and overall stop; W weekly stop (every minute) |
| 15:15 | exit B; enter W if today is T-3 |
| 15:19:30 | evaluate M signal, enter at 15:20 |
| 15:30 | write daily summary (P&L per strategy, open positions, margin estimate, alerts), upload ledgers to the repo as small CSVs |

## 5. Paper-trading acceptance (all must hold before the owner considers 1 live lot)
* B: >= 8 expiries; W: >= 8 weeks; M-safe: >= 8 weeks and >= 35 signal trades.
* Average paper slippage versus the backtest's 1-min close: B < 1 %/fill, W and M < 1.5 %/fill, using actual bid/ask not mid.
* Each strategy's paper P&L within the backtest's expectation (not worse than 0.5x expected P&L per trade after 35+ trades; one losing month is normal).
* Zero missed exits, zero unintended overnight positions, state files survive a restart.
* Report to the owner after 4 weeks and at the end: per-strategy P&L, slippage, alerts, shadow-variant comparison.

## 6. Known gaps in the code to fix first
1. `upstox_m.py`: the timed full cycle (09:20 reference, 15:19:30 signal, 09:20 exit) has only been tested with forced entry/exit on a holiday.
2. VIX logging and the shadow ledgers (section 3a) are not implemented.
3. The 5-day trend uses previous daily closes; the backtest used the 15:19 print (differs by a few points; log both).
4. Check Upstox's retail algo-ID requirement (SEBI, from 1-Apr-2026) before any live step.

## 7. Machine-readable summary
```yaml
common: {lot: 65, buffer_pct: 8, reprice_s: 3, paper: true, slippage_pct_per_fill: 0.5, stop_extra_slip_pct: 1.0}
B: {days: expiry, entry: "09:20", legs: {short: [ATM_CE, ATM_PE], long: [CE_premium_closest_3, PE_premium_closest_3]},
    leg_sl_pct: 50, after_leg_stop: other_leg_sl_to_entry, overall_sl_inr_per_lot: 3000, target: none, exit: "15:15"}
W: {entry: "T-3 trading days 15:15", legs: {short: [ATM_CE, ATM_PE], long: [CE_plus_3pct, PE_minus_3pct]},
    leg_sl: none, weekly_stop_inr_per_lot: 8000, target: none, exit: "expiry day 09:20"}
M_safe: {ref: "09:20", signal: "15:19:30", thr_pct: 0.30, trend: "spot vs close 5 trading days ago",
         up: {buy: PE_minus_3pct, sell: ATM_PE}, down: {buy: CE_plus_3pct, sell: ATM_CE},
         expiry: "nearest weekly with >=1 calendar day left", entry: "15:20", stop: wing_only, target: none, exit: "next trading day 09:20",
         kill_dd_inr_per_lot: 90000}
shadow: [{name: M_vix, skip_down_if_vix_gt: 20}, {name: M_thr05, thr_pct: 0.50}, {name: M_naked, wing: none}]
```
