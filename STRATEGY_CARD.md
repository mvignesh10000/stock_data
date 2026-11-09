# Strategy B: NIFTY expiry-day iron fly (cheap wings)

The one configuration that survived 5 years of true exchange 1-minute data (Nov 2021 – Nov 2026), two untouched
test periods, and a stress battery. It is a modest edge, not a money machine. Read "Limits" before trading it.

## Rules (identical in the backtest, `execution/upstox_ironfly.py` and AlgoTest)
| Item | Setting |
|---|---|
| Instrument / day | NIFTY weekly options, **expiry day only** (Tuesday; Thursday before Sep-2025; previous trading day if holiday) |
| Entry | **09:20** (AlgoTest: candle close of 09:19). Live: at 09:20:00 IST |
| Legs | SELL ATM CE, SELL ATM PE; BUY CE and PE whose premium is **closest to ₹3** (wings first) |
| Leg stop | **50 %** above each short leg's entry price (SL-limit at the exchange) |
| After a leg stops | move the other short leg's stop to its entry price (trail to breakeven, SL legs) |
| Overall stop | **₹3,000 per lot** MTM, exits everything |
| Exit | **15:15** all legs, shorts first |
| Re-entry / targets | none |
| Size | 1 lot = 65 qty. ₹5L capital: 1 lot (conservative) or 2 lots (max) |
| Orders | limit orders with an 8 % price buffer (market orders not allowed for API algos), re-priced every 3 s |
| Margin | about ₹1.6L per lot on expiry day (SPAN + exposure + 2 % expiry ELM) |

AlgoTest equivalent: Time-based, Expiry: weekly, DTE 0, entry 09:20, exit 15:15; Leg 1 Sell CE ATM SL 50 %;
Leg 2 Sell PE ATM SL 50 %; Leg 3 Buy CE closest premium 3; Leg 4 Buy PE closest premium 3;
Square off: partial; Trail SL to break-even: SL legs; Overall SL: MTM ₹3,000.

## Backtest (1 lot, costs at today's rates: STT 0.15 %, slippage 0.5 %/fill + 1 % on stops, pessimistic intrabar stops)
| | Value |
|---|---|
| Period | 2021-11-15 – 2026-11-03, 259 expiry days traded |
| Net | ₹1,22,694 (₹24.7k / year) |
| Profit factor | 1.50 |
| Win rate (days) / winning months | 55.6 % / **64 %** |
| Max drawdown | ₹24,726 (4.9 % of ₹5L) |
| Worst day / worst month | –₹3,911 / –₹12,156 |
| Longest losing-month streak | 3 |
| Bootstrap max-DD (5 y, monthly blocks) | median ₹23k, 95th pct ₹41k, 99th pct ₹54k |
| By year | 2021 (6 wk) +3.7k · 2022 +43.2k · **2023 –16.7k** · 2024 +59.8k · 2025 +13.5k · 2026 +19.2k |

On ₹5L: 1 lot ≈ **5 %/yr, max DD 5 %** (bad-case DD 8 %); 2 lots ≈ 10 %/yr, max DD 10 % (bad-case 16 %).

## Why this one (evidence, research/v11_discover.py, research/v12_stress.py)
* Positive in all three independent blocks: 2021-23 PF 1.35 · 2024-26 PF 1.66 · 2026 holdout PF 1.31.
* Stress (5-year PF / net): slippage ×2 1.32 / ₹84k · stops on 1-min close 1.39 / ₹103k · wings ₹2 1.52 · wings ₹5 1.46 ·
  leg SL 40 % 1.33 · leg SL 60 % 1.41 · overall SL ₹2.5k 1.51 · ₹3.5k 1.48 · entry 09:17 1.31 · entry 09:25 1.29.
  Every variant stays above PF 1.29: no cliff next to the chosen parameters.

## Limits (read this)
1. **The edge is small**: expectancy about ₹474 per trade against a worst day of –₹3.9k; with doubled slippage the yearly result drops to ~₹17k per lot.
2. **It has losing years** (2023: record-low VIX ~10-12, thin premiums) and 3-month losing streaks. Expect them.
3. **It did not transfer to SENSEX** (PF 1.1 in 2023-24, 0.6-0.8 since Oct-2024): treat it as a NIFTY-specific effect,
   not a law of options. BANKNIFTY 2021-24 check pending.
4. **Timing matters**: entering 3-5 minutes off 09:20 cost 35-45 % of the profit. Automate the entry.
5. ≥ 85 % winning months was not reachable by any strategy tested (best ~64 %). With 4-5 trades a month, a few bad
   expiries decide the month.
6. The past five years include the 2024-26 period the earlier research rounds studied; the clean out-of-sample evidence
   is 2021-23 (+₹30k, PF 1.35) and Apr-Nov 2026 (+₹9.6k, PF 1.31).

## Going live (recommended path)
1. **Paper, 8 expiries**: `python execution/upstox_ironfly.py NIFTY` (paper is the default) on your static-IP machine
   every Tuesday. Compare fills vs. the backtest's 09:20 closes; average entry slippage must stay below ~1 %.
2. **1 lot live** for 3 months (`--live`, normal daily Upstox token). Keep the algo tag / SEBI algo-ID requirements.
3. **2 lots** only if live results track the backtest (PF ≥ 1.2 over ≥ 12 expiries).

## Kill-switch (stop and re-evaluate if any happens)
* drawdown from peak > ₹40k per lot (beyond the bootstrap 95th percentile);
* 4 consecutive losing months;
* average live slippage > 2 % per fill over 8 expiries;
* exchange rule change touching expiry day (ELM, lot size, expiry weekday, settlement method).

## Running Strategy B at size (multi-lot, multi-account)
| Capital | Setup | Margin used (expiry day) | Expected / yr | Max DD (5 y) | Bad-case DD (95 %) | Worst day |
|---|---|---|---|---|---|---|
| ₹5L | 1 lot | ~₹1.7L | ~₹24.7k (4.9 %) | ₹24.7k (4.9 %) | ₹41k (8.2 %) | –₹3.9k |
| ₹5L | 2 lots (one account, or 1 + 1 across two) | ~₹3.4L | ~₹49.5k (9.9 %) | ₹49.5k (9.9 %) | ₹82k (16.5 %) | –₹7.8k |
Lots scale P&L and drawdown linearly; margin per lot ~₹1.6-1.7L on expiry day (SPAN + exposure + 2 % ELM), so ₹5L holds 2 lots
with ~₹1.6L spare. Splitting the same lots across accounts does not diversify (same trade); it only spreads broker/operational risk.

**Implementation** (`execution/run_b.py` + `execution/upstox_ironfly.py`):
1. `cp execution/accounts.example.json execution/accounts.json`; one entry per account: `token_file` (that account's normal
   daily Upstox token), `lots`, `live` (start `false`).
2. Schedule `python execution/run_b.py` at 09:12 IST on weekdays (cron / Task Scheduler). On non-expiry days every account exits
   immediately; on expiry day one executor process runs per account, in parallel.
3. Before placing orders each account asks the Upstox margin API for the per-lot margin and its available funds and trades the
   largest lot count that fits with a 10 % buffer (falls back to the configured lots if the funds API is unavailable).
4. Each account keeps its own log (`data/upstox/exec_<name>.log`) and ledger (`data/upstox/b_ledger_<name>.csv`). The kill-switch
   reads the live rows and refuses to trade after a drawdown above ₹40k per lot or 4 losing months in a row (reset by review).
5. Wings stay open after both shorts stop (as in the backtest); exit 15:15; orders are limit orders with an 8 % buffer.
Tested in paper mode on 9 Nov 2026 (2 lots, ledger written, margin fallback exercised; kill-switch unit-tested).
