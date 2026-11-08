//! Virtual OMS: order lifecycle, intra-bar stop/target matching, MTM, slippage and the
//! Indian NSE index-option statutory cost model.
//!
//! Event order per minute `m` (enforced by the engine loop in `cli_runner`):
//!   1. `process_triggers(m)` — stops / targets of positions opened *before* `m` are matched
//!      against bar `m`'s [open, high, low, close]; if a stop and a target are both inside the
//!      bar, the stop wins (pessimistic). Short stop fill = max(trigger, open) * (1 + sl_slip).
//!   2. strategy `on_minute(m)` — market orders fill at bar `m`'s close +/- entry slippage.
//!   3. at `eod_minute` everything is squared off.

use core_types::{minute_to_hhmm, OhlcBar, Side, TradingDayData};
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct CostModel {
    pub brokerage_per_order: f64,
    pub stt_sell_pct: f64,
    pub exchange_txn_pct: f64,
    pub sebi_pct: f64,
    pub stamp_buy_pct: f64,
    pub gst_pct: f64,
}

impl Default for CostModel {
    fn default() -> Self {
        CostModel {
            brokerage_per_order: 20.0,
            stt_sell_pct: 0.15, // from 1-Apr-2026 (was 0.1 from 1-Oct-2024)
            exchange_txn_pct: 0.03503,
            sebi_pct: 0.0001,
            stamp_buy_pct: 0.003,
            gst_pct: 18.0,
        }
    }
}

impl CostModel {
    /// Rupee charges for one executed order of `qty` units at `price`.
    pub fn charges(&self, side: Side, price: f64, qty: f64) -> f64 {
        let turnover = price * qty;
        let brokerage = self.brokerage_per_order;
        let stt = if side == Side::Sell { turnover * self.stt_sell_pct / 100.0 } else { 0.0 };
        let exch = turnover * self.exchange_txn_pct / 100.0;
        let sebi = turnover * self.sebi_pct / 100.0;
        let stamp = if side == Side::Buy { turnover * self.stamp_buy_pct / 100.0 } else { 0.0 };
        let gst = (brokerage + exch + sebi) * self.gst_pct / 100.0;
        brokerage + stt + exch + sebi + stamp + gst
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct ExecConfig {
    /// Constant normalised lot size (NSE changed NIFTY lots 25 -> 75 -> 65; we keep one value
    /// so every year is weighted equally).
    pub lot_size: f64,
    /// Market-order slippage, % of price, applied against us on every entry/exit.
    pub entry_slippage_pct: f64,
    /// Extra slippage, % of price, applied on stop-loss fills.
    pub sl_slippage_pct: f64,
    /// Minimum absolute slippage per fill in premium points (1 tick).
    pub min_slippage_pts: f64,
    /// Auto square-off minute (370 = 15:25).
    pub eod_minute: usize,
    pub costs: CostModel,
    pub margin: MarginModel,
    /// After a stop moves (e.g. SL-to-breakeven) re-check it against the SAME bar's high/low.
    /// 1-minute bars do not tell which leg moved first, so assume the worst.
    pub pessimistic_same_bar: bool,
}

/// NSE margin approximation calibrated on the exchange SPAN file (via a broker SPAN calculator,
/// NIFTY 25,030 / VIX 17.7 / lot 65, Nov-2026):
///   naked short ATM CE  SPAN 150,917  -> model 151,000 (PSR 9.3%)
///   iron fly +-300      SPAN  20,307  -> model  19,500 x 1.03
///   exposure            31,197 per short lot = 1.92% of notional
/// plus SEBI's additional 2% ELM on short options on expiry day (from 20-Nov-2024).
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct MarginModel {
    pub psr_pct: f64,
    pub span_mult: f64,
    pub exposure_pct: f64,
    pub expiry_elm_pct: f64,
    pub expiry_elm_from: u32,
}

impl Default for MarginModel {
    fn default() -> Self {
        MarginModel { psr_pct: 9.3, span_mult: 1.03, exposure_pct: 1.92, expiry_elm_pct: 2.0, expiry_elm_from: 20241120 }
    }
}

/// (strike, is_call, side, lots)
pub type MarginLeg = (u32, bool, Side, u32);

impl MarginModel {
    /// Rupee margin for a set of legs at spot `s`.
    pub fn margin(&self, legs: &[MarginLeg], s: f64, lot_size: f64, expiry_day: bool, trade_date: u32) -> f64 {
        if legs.is_empty() {
            return 0.0;
        }
        let mut worst = 0.0f64;
        for k in -6i32..=6 {
            let sp = s * (1.0 + self.psr_pct / 100.0 * k as f64 / 6.0);
            let mut loss = 0.0;
            for &(strike, is_call, side, lots) in legs {
                let intr = if is_call { (sp - strike as f64).max(0.0) } else { (strike as f64 - sp).max(0.0) };
                // a short loses its intrinsic, a long gains it
                loss -= side.sign() * intr * lots as f64;
            }
            worst = worst.max(loss);
        }
        let span = worst * lot_size * self.span_mult;
        let short_lots: u32 = legs.iter().filter(|l| l.2 == Side::Sell).map(|l| l.3).sum();
        let notional = s * lot_size * short_lots as f64;
        let mut m = span + notional * self.exposure_pct / 100.0;
        if expiry_day && trade_date >= self.expiry_elm_from {
            m += notional * self.expiry_elm_pct / 100.0;
        }
        m
    }
}

impl Default for ExecConfig {
    fn default() -> Self {
        ExecConfig {
            lot_size: 65.0,
            entry_slippage_pct: 0.5,
            sl_slippage_pct: 1.0,
            min_slippage_pts: 0.10,
            eod_minute: 370,
            costs: CostModel::default(),
            margin: MarginModel::default(),
            pessimistic_same_bar: true,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum OrderRejected {
    IlliquidStrike,
    NoSuchContract,
    MarketClosed,
    UnknownPosition,
}

#[derive(Clone, Debug, Serialize)]
pub struct Position {
    pub id: usize,
    pub strike: u32,
    pub is_call: bool,
    pub side: Side,
    pub lots: u32,
    pub entry_price: f64,
    pub entry_minute: usize,
    pub exit_price: Option<f64>,
    pub exit_minute: Option<usize>,
    pub exit_reason: Option<String>,
    pub stop: Option<f64>,
    pub target: Option<f64>,
    pub tag: String,
}

impl Position {
    pub fn is_open(&self) -> bool {
        self.exit_price.is_none()
    }
    /// P&L in premium points * lots.
    pub fn points(&self, mark: f64) -> f64 {
        let exit = self.exit_price.unwrap_or(mark);
        self.side.sign() * (exit - self.entry_price) * self.lots as f64
    }
}

#[derive(Clone, Debug)]
pub struct TriggerEvent {
    pub position_id: usize,
    pub kind: &'static str, // "SL" | "TGT"
    pub fill_price: f64,
}

#[derive(Clone, Debug, Serialize)]
pub struct TradeRecord {
    pub trade_date: u32,
    pub tag: String,
    pub strike: u32,
    pub right: &'static str,
    pub side: Side,
    pub lots: u32,
    pub entry_time: String,
    pub entry_price: f64,
    pub exit_time: String,
    pub exit_price: f64,
    pub exit_reason: String,
    pub points: f64,
}

#[derive(Clone, Debug, Default, Serialize)]
pub struct DayResult {
    pub trade_date: u32,
    pub dte: u8,
    pub weekday: u8,
    pub traded: bool,
    pub points: f64,          // after slippage, per 1 qty * lots
    pub slippage_points: f64, // slippage paid (already inside `points`)
    pub charges_rupees: f64,
    pub net_rupees: f64,
    pub n_orders: u32,
    pub n_stops: u32,
    pub exit_reason: String,
    pub last_exit_minute: usize,
    pub max_lots: u32,
    pub peak_margin: f64,
}

pub struct VirtualOms<'a> {
    pub day: &'a TradingDayData,
    pub cfg: &'a ExecConfig,
    pub minute: usize,
    pub positions: Vec<Position>,
    pub events: Vec<TriggerEvent>,
    slippage_points: f64,
    charges: f64,
    n_orders: u32,
    n_stops: u32,
    last_reason: String,
    last_exit_minute: usize,
    max_lots: u32,
    peak_margin: f64,
}

impl<'a> VirtualOms<'a> {
    pub fn new(day: &'a TradingDayData, cfg: &'a ExecConfig) -> Self {
        VirtualOms {
            day,
            cfg,
            minute: 0,
            positions: Vec::with_capacity(16),
            events: Vec::with_capacity(4),
            slippage_points: 0.0,
            charges: 0.0,
            n_orders: 0,
            n_stops: 0,
            last_reason: String::new(),
            last_exit_minute: 0,
            max_lots: 0,
            peak_margin: 0.0,
        }
    }

    pub fn is_expiry_day(&self) -> bool {
        self.day.tdte == 0
    }

    /// Margin of the currently open positions plus `extra` legs (what-if), at the current spot.
    pub fn margin_with(&self, extra: &[MarginLeg]) -> f64 {
        let mut legs: Vec<MarginLeg> = self.positions.iter().filter(|p| p.is_open()).map(|p| (p.strike, p.is_call, p.side, p.lots)).collect();
        legs.extend_from_slice(extra);
        let s = self.day.spot[self.minute].close as f64;
        self.cfg.margin.margin(&legs, s, self.cfg.lot_size, self.is_expiry_day(), self.day.trade_date)
    }

    pub fn update_margin(&mut self) {
        let m = self.margin_with(&[]);
        if m > self.peak_margin {
            self.peak_margin = m;
        }
    }

    /// Pessimistic same-bar check of one position's stop against the CURRENT bar (used right after a
    /// stop was moved inside this minute). Returns true if it fired.
    pub fn check_stop_now(&mut self, id: usize) -> bool {
        if !self.cfg.pessimistic_same_bar {
            return false;
        }
        let m = self.minute;
        let p = &self.positions[id];
        if !p.is_open() || p.entry_minute >= m {
            return false;
        }
        let (sl, side, lots) = match p.stop {
            Some(sl) => (sl, p.side, p.lots),
            None => return false,
        };
        let bar = match self.day.bar(p.strike, p.is_call, m) {
            Some(b) => *b,
            None => return false,
        };
        let hit = match side {
            Side::Sell => bar.high as f64 >= sl,
            Side::Buy => (bar.low as f64) <= sl,
        };
        if !hit {
            return false;
        }
        // we do not know when inside the bar it happened: fill at the stop (+ stop slippage)
        let fill = match side {
            Side::Sell => sl * (1.0 + self.cfg.sl_slippage_pct / 100.0) + self.cfg.min_slippage_pts,
            Side::Buy => (sl * (1.0 - self.cfg.sl_slippage_pct / 100.0) - self.cfg.min_slippage_pts).max(0.0),
        };
        self.slippage_points += (fill - sl).abs() * lots as f64;
        self.book_fill(side.opposite(), fill, lots);
        let p = &mut self.positions[id];
        p.exit_price = Some(fill);
        p.exit_minute = Some(m);
        p.exit_reason = Some("SL".to_string());
        self.n_stops += 1;
        self.last_reason = "SL".to_string();
        self.last_exit_minute = m;
        self.events.push(TriggerEvent { position_id: id, kind: "SL", fill_price: fill });
        true
    }

    /// Fill a limit-style entry at `price` (used by RE-COST / momentum entries that rest at a level).
    pub fn submit_at_price(&mut self, strike: u32, is_call: bool, side: Side, lots: u32, price: f64, tag: &str) -> Result<usize, OrderRejected> {
        if self.minute >= self.cfg.eod_minute {
            return Err(OrderRejected::MarketClosed);
        }
        let bar = *self.bar(strike, is_call, self.minute).ok_or(OrderRejected::NoSuchContract)?;
        if bar.volume == 0 {
            return Err(OrderRejected::IlliquidStrike);
        }
        let s = self.slip(price, self.cfg.entry_slippage_pct);
        let fill = match side {
            Side::Buy => price + s,
            Side::Sell => (price - s).max(0.05),
        };
        self.slippage_points += (fill - price).abs() * lots as f64;
        self.book_fill(side, fill, lots);
        let id = self.positions.len();
        self.positions.push(Position {
            id, strike, is_call, side, lots, entry_price: fill, entry_minute: self.minute,
            exit_price: None, exit_minute: None, exit_reason: None, stop: None, target: None, tag: tag.to_string(),
        });
        self.update_margin();
        Ok(id)
    }

    #[inline]
    fn bar(&self, strike: u32, is_call: bool, m: usize) -> Option<&OhlcBar> {
        self.day.bar(strike, is_call, m)
    }

    /// Last known close for a contract at or before the current minute (for MTM).
    pub fn mark(&self, strike: u32, is_call: bool) -> Option<f64> {
        let mut m = self.minute as isize;
        while m >= 0 {
            if let Some(b) = self.bar(strike, is_call, m as usize) {
                return Some(b.close as f64);
            }
            m -= 1;
        }
        None
    }

    fn slip(&self, price: f64, pct: f64) -> f64 {
        (price * pct / 100.0).max(self.cfg.min_slippage_pts)
    }

    fn book_fill(&mut self, side: Side, price: f64, lots: u32) {
        self.charges += self.cfg.costs.charges(side, price, lots as f64 * self.cfg.lot_size);
        self.n_orders += 1;
    }

    /// Market order at the current minute's close (+/- slippage). Rejected on zero volume.
    pub fn submit_market(&mut self, strike: u32, is_call: bool, side: Side, lots: u32, tag: &str) -> Result<usize, OrderRejected> {
        if self.minute >= self.cfg.eod_minute {
            return Err(OrderRejected::MarketClosed);
        }
        let bar = *self.bar(strike, is_call, self.minute).ok_or(OrderRejected::NoSuchContract)?;
        if bar.volume == 0 {
            return Err(OrderRejected::IlliquidStrike);
        }
        let px = bar.close as f64;
        let s = self.slip(px, self.cfg.entry_slippage_pct);
        let fill = match side {
            Side::Buy => px + s,
            Side::Sell => (px - s).max(0.05),
        };
        self.slippage_points += (fill - px).abs() * lots as f64;
        self.book_fill(side, fill, lots);
        let id = self.positions.len();
        self.positions.push(Position {
            id,
            strike,
            is_call,
            side,
            lots,
            entry_price: fill,
            entry_minute: self.minute,
            exit_price: None,
            exit_minute: None,
            exit_reason: None,
            stop: None,
            target: None,
            tag: tag.to_string(),
        });
        let open_lots: u32 = self.positions.iter().filter(|p| p.is_open() && p.side == Side::Sell).map(|p| p.lots).sum();
        self.max_lots = self.max_lots.max(open_lots);
        self.update_margin();
        Ok(id)
    }

    /// Close at current minute close (+/- slippage). Uses the last known price when the
    /// contract has no bar this minute (forced exits must always be possible).
    pub fn close_position(&mut self, id: usize, reason: &str) -> Result<f64, OrderRejected> {
        let p = self.positions.get(id).ok_or(OrderRejected::UnknownPosition)?;
        if !p.is_open() {
            return Err(OrderRejected::UnknownPosition);
        }
        let (strike, is_call, side, lots) = (p.strike, p.is_call, p.side, p.lots);
        let px = self.mark(strike, is_call).unwrap_or(p.entry_price);
        let s = self.slip(px, self.cfg.entry_slippage_pct);
        let exit_side = side.opposite();
        let fill = match exit_side {
            Side::Buy => px + s,
            Side::Sell => (px - s).max(0.0),
        };
        self.slippage_points += (fill - px).abs() * lots as f64;
        self.book_fill(exit_side, fill, lots);
        let m = self.minute;
        let p = &mut self.positions[id];
        p.exit_price = Some(fill);
        p.exit_minute = Some(m);
        p.exit_reason = Some(reason.to_string());
        self.last_reason = reason.to_string();
        self.last_exit_minute = m;
        Ok(fill)
    }

    pub fn set_stop_loss(&mut self, id: usize, trigger: f64) {
        if let Some(p) = self.positions.get_mut(id) {
            p.stop = Some(trigger);
        }
    }

    pub fn set_target(&mut self, id: usize, price: f64) {
        if let Some(p) = self.positions.get_mut(id) {
            p.target = Some(price);
        }
    }

    /// Step 1 of the minute: match stops/targets against bar `m`. Returns fired events
    /// (also kept in `self.events` for the strategy to inspect during `on_minute`).
    pub fn process_triggers(&mut self, m: usize) {
        self.minute = m;
        self.events.clear();
        for i in 0..self.positions.len() {
            let p = &self.positions[i];
            if !p.is_open() || p.entry_minute >= m {
                continue;
            }
            let bar = match self.day.bar(p.strike, p.is_call, m) {
                Some(b) => *b,
                None => continue,
            };
            let (hi, lo, op) = (bar.high as f64, bar.low as f64, bar.open as f64);
            let mut fired: Option<(&'static str, f64)> = None;
            match p.side {
                Side::Sell => {
                    if let Some(sl) = p.stop {
                        if hi >= sl {
                            let base = sl.max(op);
                            fired = Some(("SL", base * (1.0 + self.cfg.sl_slippage_pct / 100.0) + self.cfg.min_slippage_pts));
                        }
                    }
                    if fired.is_none() {
                        if let Some(t) = p.target {
                            if lo <= t {
                                fired = Some(("TGT", t.min(op)));
                            }
                        }
                    }
                }
                Side::Buy => {
                    if let Some(sl) = p.stop {
                        if lo <= sl {
                            let base = sl.min(op);
                            fired = Some(("SL", (base * (1.0 - self.cfg.sl_slippage_pct / 100.0) - self.cfg.min_slippage_pts).max(0.0)));
                        }
                    }
                    if fired.is_none() {
                        if let Some(t) = p.target {
                            if hi >= t {
                                fired = Some(("TGT", t.max(op)));
                            }
                        }
                    }
                }
            }
            if let Some((kind, fill)) = fired {
                let reference = if kind == "SL" { p.stop.unwrap().max(0.0) } else { fill };
                let (side, lots) = (p.side, p.lots);
                self.slippage_points += (fill - reference).abs() * lots as f64;
                self.book_fill(side.opposite(), fill, lots);
                let p = &mut self.positions[i];
                p.exit_price = Some(fill);
                p.exit_minute = Some(m);
                p.exit_reason = Some(kind.to_string());
                if kind == "SL" {
                    self.n_stops += 1;
                }
                self.last_reason = kind.to_string();
                self.last_exit_minute = m;
                self.events.push(TriggerEvent { position_id: i, kind, fill_price: fill });
            }
        }
    }

    /// Realised + unrealised P&L in points (after slippage, before charges).
    pub fn mtm_points(&self) -> f64 {
        self.positions
            .iter()
            .map(|p| {
                if p.is_open() {
                    let mk = self.mark(p.strike, p.is_call).unwrap_or(p.entry_price);
                    p.points(mk)
                } else {
                    p.points(0.0)
                }
            })
            .sum()
    }

    /// MTM net of charges already incurred, in rupees.
    pub fn mtm_rupees(&self) -> f64 {
        self.mtm_points() * self.cfg.lot_size - self.charges
    }

    pub fn open_ids(&self) -> Vec<usize> {
        self.positions.iter().filter(|p| p.is_open()).map(|p| p.id).collect()
    }

    pub fn square_off_all(&mut self, reason: &str) {
        // close shorts first, then hedges
        let mut ids = self.open_ids();
        ids.sort_by_key(|&i| if self.positions[i].side == Side::Sell { 0 } else { 1 });
        for id in ids {
            let _ = self.close_position(id, reason);
        }
    }

    pub fn result(&self) -> DayResult {
        let pts: f64 = self.positions.iter().map(|p| p.points(p.entry_price)).sum();
        DayResult {
            trade_date: self.day.trade_date,
            dte: self.day.dte,
            weekday: self.day.weekday,
            traded: !self.positions.is_empty(),
            points: pts,
            slippage_points: self.slippage_points,
            charges_rupees: self.charges,
            net_rupees: pts * self.cfg.lot_size - self.charges,
            n_orders: self.n_orders,
            n_stops: self.n_stops,
            exit_reason: self.last_reason.clone(),
            last_exit_minute: self.last_exit_minute,
            max_lots: self.max_lots,
            peak_margin: self.peak_margin,
        }
    }

    pub fn trade_records(&self) -> Vec<TradeRecord> {
        self.positions
            .iter()
            .map(|p| TradeRecord {
                trade_date: self.day.trade_date,
                tag: p.tag.clone(),
                strike: p.strike,
                right: if p.is_call { "CE" } else { "PE" },
                side: p.side,
                lots: p.lots,
                entry_time: minute_to_hhmm(p.entry_minute),
                entry_price: p.entry_price,
                exit_time: minute_to_hhmm(p.exit_minute.unwrap_or(p.entry_minute)),
                exit_price: p.exit_price.unwrap_or(p.entry_price),
                exit_reason: p.exit_reason.clone().unwrap_or_default(),
                points: p.points(p.entry_price),
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn margin_model_matches_exchange_span_points() {
        let m = MarginModel::default();
        let s = 25030.0;
        // naked short ATM CE: exchange total 182,114
        let a = m.margin(&[(25050, true, Side::Sell, 1)], s, 65.0, false, 20261106);
        assert!((a - 182_114.0).abs() / 182_114.0 < 0.06, "naked {}", a);
        // iron fly +-300: exchange total 82,700
        let b = m.margin(&[(25050, true, Side::Sell, 1), (25050, false, Side::Sell, 1), (25350, true, Side::Buy, 1), (24750, false, Side::Buy, 1)], s, 65.0, false, 20261106);
        assert!((b - 82_700.0).abs() / 82_700.0 < 0.06, "ironfly {}", b);
        // iron fly +-1000: exchange total 128,866
        let c = m.margin(&[(25050, true, Side::Sell, 1), (25050, false, Side::Sell, 1), (26050, true, Side::Buy, 1), (24050, false, Side::Buy, 1)], s, 65.0, false, 20261106);
        assert!((c - 128_866.0).abs() / 128_866.0 < 0.06, "ironfly1000 {}", c);
        // expiry day adds 2% per short lot
        let d = m.margin(&[(25050, true, Side::Sell, 1), (25050, false, Side::Sell, 1), (25350, true, Side::Buy, 1), (24750, false, Side::Buy, 1)], s, 65.0, true, 20261106);
        assert!((d - b - 2.0 * s * 65.0 * 0.02).abs() < 1.0);
    }

    #[test]
    fn statutory_costs_match_hand_calc() {
        let c = CostModel::default();
        // sell 65 qty @ 100 -> turnover 6500
        let sell = c.charges(Side::Sell, 100.0, 65.0);
        let expected = 20.0 + 9.75 + 6500.0 * 0.0003503 + 6500.0 * 0.000001 + (20.0 + 6500.0 * 0.0003503 + 6500.0 * 0.000001) * 0.18;
        assert!((sell - expected).abs() < 1e-9);
        let buy = c.charges(Side::Buy, 100.0, 65.0);
        let expected_b = 20.0 + 6500.0 * 0.00003 + 6500.0 * 0.0003503 + 6500.0 * 0.000001 + (20.0 + 6500.0 * 0.0003503 + 6500.0 * 0.000001) * 0.18;
        assert!((buy - expected_b).abs() < 1e-9);
    }
}
