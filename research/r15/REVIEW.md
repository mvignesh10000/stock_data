# Round 15 (2026-11-11): independent review of M-safe, a Reddit strategy, a credit-spread infographic, VIX rule, FVG/SMC

Reviewer's independent tests. Index data 2015-01..2026-05 (debashis74017) plus the Upstox lake; real option prices 2021-11..2026-11
(Dhan 2021-24 + Upstox 2024-10..). Own quick engine (`ob.py`): lot 65, slippage max(0.5 %, Rs 0.10)/fill, today's charges.
It is not the `research/sim` simulator, so absolute numbers differ slightly from rounds 13-14.
Restore: Kaggle `debashis74017/nifty-50-minute-data` (NIFTY 50 + INDIA VIX minute CSVs) into `data/deb/`, `kaggle_sync.py pull history`,
`etl_upstox.py NIFTY`, Dhan 2021-24 parquet into `data/r15/dhan_in/`, then `python3 research/r15/ostore.py` and run any script from this folder.

| Script | Question |
|---|---|
| `reddit.py` / `t_rd.py` | Reddit "buy puts on previous-day-low break" on index (2015-26) and on real options |
| `t_cs.py` | OptionsPlay credit-spread infographic on real NIFTY weekly options |
| `on.py`, `t_m.py` | independent replication of Strategy M (index signal, walk-forward threshold, VIX buckets; real options) |
| `t_vix.py` | VIX > 20 rule for M |
| `grid.py`, `mr.py` | opening-deviation momentum with stop/target; daily mean reversion (RSI2, IBS) |
| `smc.py`, `smc2.py` | FVG and liquidity-sweep (smart money concepts) with a random-entry placebo |

## Results
**Reddit rules (index, gross, n=1,213 breaks):** short on prev-day-low break +2.3 bp (t 0.95); below EMA20 only +1.9 bp (t 0.4); the same
shorts ABOVE EMA20 +2.6 bp (filter filters nothing); mirror longs on prev-high break -1.3 bp (t -0.7). Real options 2024-26, ATM put,
exit 15:20, below EMA20: 136 trades, PF 1.02, Rs 2.5k/yr, DD Rs 50k; with 30 % stop / 60 % target PF 0.82-0.91. Green-day / narrow-range subsets
(n 17-109) not significant. The commenter's backtest used model-priced options and a third of its profit is 2020.

**Credit spread (infographic), 84 weekly trades 2024-10..2026-11, 1/3-width credit, trend direction:** win 63 % (claimed 67 %), PF 0.77,
-Rs 36k/yr (200 wide); 100 % stop PF 0.98; 100 % stop + 50 % target PF 0.69. Credit = 1/3 width means break-even win rate 67 %, i.e. no edge by construction.
Always-call +58k vs always-put -69k is the market's direction in one window. Stop-exit cases omit exit slippage (flatters them).

**Strategy M replication (index):** up > 0.3 % and trend up: +9.9 bp/night net of carry and costs (t 3.96, n 565); down: +9.3 bp (t 2.4). Walk-forward
threshold choice 2019-26 pooled +9.2 bp (t 3.9). By year (up aligned): 2020 +34, 21 +20, 22 +11, 23 +1, 24 +4, 25 +3, 26 +20 bp: calm years are near cost.
Real options 2024-10..2026-11, M-safe (both, trend, 3 % wing): 187 trades, PF 1.40, Rs 43.8k/yr, DD Rs 26k (sim: 1.25 / 29.5k / 34k); naked PF 1.60, 68.6k/yr.
Exit 09:30 PF 1.28, 10:00 PF 1.23 (the 09:20 exit is structural). Wing costs ~36 % of profit.

**VIX rule (naked ATM M, both legs + trend, 2022-2026, 469 trades):** baseline PF 1.45, Rs 51k/yr, DD 37.9k. Skip down leg when VIX(15:20) > 18: PF 1.71, DD 23.6k;
> 20: PF 1.69, 58k/yr, DD 29.3k; > 22: PF 1.51, DD 37.5k (no gain); skip all when VIX > 20: PF 1.62, 48k/yr. M-safe 2024-10+ skip-down > 20: PF 1.40 -> 1.51, DD unchanged.
Index VIX buckets: down signal at VIX > 20 earns +3.6 bp (t 0.3) with worst night -496 bp; up signal at VIX > 20 +32 bp. Verdict: helps in 4 of 5 years (2026 worse), cut-off
sensitive and chosen post hoc; use as a risk-reduction option, not a proven edge.

**Other searches (index 2015-2026):** opening-deviation momentum (enter at 0.3-0.5 ATR from open, stop 0.4-0.5 ATR, target 0.8-1.0 ATR): +4.8..+5.6 bp gross per trade, t ~4.3, 10/12 years,
fade version -5..-9 bp; futures STT ~5 bp absorbs it (2015-20 +7 bp vs 2021-26 +3 bp). Daily mean reversion in uptrends (RSI2 < 10, 3 lower closes, IBS < 0.2): t 0.4-0.7 or negative; short bounces negative.

**FVG / smart money concepts (5-min bars, 11 years, 4,500-4,800 FVG trades, 1,500-2,300 sweep trades; stop at structure, target 1-3 R, exit 15:15; random-entry placebo with the same stop distance):**
FVG (displacement candle >= 1.5x average range, entry at gap edge or 50 %, stop at candle-1 extreme): gross R -0.07..0.00 (placebo -0.09..-0.18), net of costs -0.54..-0.79 R,
trend alignment does not help. Liquidity sweep and rejection (previous-day high/low and opening range): gross R -0.11..-0.23, no better than placebo. Stops are 11-15 bp of the index,
so a 6 bp cost is ~0.5 R per trade: such tight-stop patterns cannot pay on NIFTY even with a small real edge.

**Order blocks, BOS/CHoCH, premium/discount (`smc3.py`, added after the first pass; same harness, 3-bar fractal swings, OB = last opposite candle before the structure-breaking leg, limit at OB edge, stop beyond OB):**
OB after any structure break (3,939 trades): gross R -0.15..-0.19, placebo -0.18..-0.21, net about -0.94 R. BOS only (2,893): -0.15..-0.18. CHoCH only (1,759): -0.24..-0.25 (worse than placebo).
Premium/discount filter (long only below 50 % of the day's range so far, short only above): OB all -0.17..-0.21; BOS-only subset (n=370) -0.07..-0.15 R, better than its placebo (-0.14..-0.37) but still negative and a small sample;
FVG + premium/discount (2,107) -0.12..-0.14 R. No variant has positive gross R, every year-by-year row is mostly negative, stops are about 10 bp so costs add -0.5 R. First-pass note that trend alignment "covers" premium/discount was wrong; they are separate and were tested separately here.
