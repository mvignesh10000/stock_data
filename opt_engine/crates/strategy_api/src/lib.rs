//! Strategy plugin interface: `MarketView` (look-ahead-free read-only chain view),
//! the `IntradayStrategy` trait, and the built-in parameterised non-directional seller.

pub mod algotest;
pub mod nd_seller;

use core_types::{DayMetadata, OhlcBar, SpotBar, TradingDayData};
use oms_simulator::VirtualOms;

/// Read-only view of the market at minute `m`. Nothing at `minute_idx > m` is reachable.
pub struct MarketView<'a> {
    day: &'a TradingDayData,
    m: usize,
}

impl<'a> MarketView<'a> {
    pub fn new(day: &'a TradingDayData, m: usize) -> Self {
        MarketView { day, m }
    }
    pub fn minute(&self) -> usize {
        self.m
    }
    pub fn meta(&self) -> DayMetadata {
        self.day.meta()
    }
    pub fn spot(&self) -> SpotBar {
        self.day.spot[self.m]
    }
    pub fn spot_history(&self) -> &[SpotBar] {
        &self.day.spot[..=self.m]
    }
    pub fn option_bar(&self, strike: u32, is_call: bool) -> Option<OhlcBar> {
        self.day.bar(strike, is_call, self.m).copied()
    }
    /// Bar of a contract at an earlier minute `k <= m`.
    pub fn option_bar_at(&self, strike: u32, is_call: bool, k: usize) -> Option<OhlcBar> {
        if k > self.m {
            return None;
        }
        self.day.bar(strike, is_call, k).copied()
    }
    /// All strikes on the day's grid (ascending).
    pub fn strikes(&self) -> impl Iterator<Item = u32> + '_ {
        (0..self.day.n_strikes as usize).map(move |i| self.day.strike_at(i))
    }
    pub fn strike_step(&self) -> u32 {
        self.day.strike_step
    }
    pub fn atm_strike(&self) -> u32 {
        let s = self.spot().close as f64;
        let step = self.day.strike_step as f64;
        ((s / step).round() * step) as u32
    }
    /// ATM via the synthetic future: the strike (near spot) minimising |CE - PE|.
    pub fn atm_by_synthetic(&self) -> u32 {
        let atm = self.atm_strike();
        let step = self.day.strike_step;
        let mut best = (f32::MAX, atm);
        for k in -4i32..=4 {
            let s = (atm as i64 + k as i64 * step as i64) as u32;
            if let (Some(c), Some(p)) = (self.option_bar(s, true), self.option_bar(s, false)) {
                if c.volume > 0 && p.volume > 0 {
                    let d = (c.close - p.close).abs();
                    if d < best.0 {
                        best = (d, s);
                    }
                }
            }
        }
        best.1
    }
    /// Synthetic future price = K + C - P at the synthetic ATM strike.
    pub fn synthetic_future(&self) -> f32 {
        let k = self.atm_by_synthetic();
        match (self.option_bar(k, true), self.option_bar(k, false)) {
            (Some(c), Some(p)) => k as f32 + c.close - p.close,
            _ => self.spot().close,
        }
    }
    pub fn select_strike_by_offset(&self, offset_steps: i32) -> u32 {
        (self.atm_by_synthetic() as i64 + offset_steps as i64 * self.day.strike_step as i64) as u32
    }
    /// Liquid strike (volume > 0) whose close is closest to `target_premium`, restricted to the
    /// OTM side of `pivot` (calls: strike >= pivot, puts: strike <= pivot).
    pub fn select_strike_by_premium_from(&self, is_call: bool, target_premium: f32, pivot: u32) -> Option<u32> {
        let mut best: Option<(f32, u32)> = None;
        for i in 0..self.day.n_strikes as usize {
            let s = self.day.strike_at(i);
            if (is_call && s < pivot) || (!is_call && s > pivot) {
                continue;
            }
            if let Some(b) = self.option_bar(s, is_call) {
                if b.volume == 0 {
                    continue;
                }
                let d = (b.close - target_premium).abs();
                if best.map(|x| d < x.0).unwrap_or(true) {
                    best = Some((d, s));
                }
            }
        }
        best.map(|x| x.1)
    }
    pub fn select_strike_by_premium(&self, is_call: bool, target_premium: f32) -> Option<u32> {
        self.select_strike_by_premium_from(is_call, target_premium, self.atm_by_synthetic())
    }
}

pub trait IntradayStrategy: Send {
    /// Called once at 09:15 before iterating minutes 0..375. Return false to skip the day.
    fn on_day_start(&mut self, meta: &DayMetadata) -> bool;
    /// Called every minute AFTER pending SL/target orders were evaluated for that minute.
    fn on_minute(&mut self, minute_idx: usize, market: &MarketView, oms: &mut VirtualOms);
    /// Called at end of day.
    fn on_day_end(&mut self, oms: &mut VirtualOms);
}
