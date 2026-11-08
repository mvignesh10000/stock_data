//! Core data types shared by every crate of the engine.
//!
//! Memory layout: a trading day stores the full 375-minute grid (09:15..=15:29) for the
//! underlying spot and, for every strike on a dense strike grid, 375 option bars for CE and PE.
//! Lookup of `(strike, is_call, minute)` is O(1): `((strike - min_strike) / step) * 375 + minute`.

use serde::{Deserialize, Serialize};

pub const MINUTES: usize = 375;

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct OhlcBar {
    pub open: f32,
    pub high: f32,
    pub low: f32,
    pub close: f32,
    pub volume: u32,
    pub oi: u32,
}

impl OhlcBar {
    /// A bar with close <= 0 marks "contract not present" on the dense grid.
    #[inline]
    pub fn is_valid(&self) -> bool {
        self.close > 0.0
    }
}

#[repr(C)]
#[derive(Clone, Copy, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct SpotBar {
    pub open: f32,
    pub high: f32,
    pub low: f32,
    pub close: f32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TradingDayData {
    pub trade_date: u32,  // YYYYMMDD
    pub expiry_date: u32, // YYYYMMDD
    pub dte: u8,
    pub expiry_rank: u8,
    pub weekday: u8, // 1 = Monday .. 5 = Friday
    /// Trading days to expiry (AlgoTest definition: weekends & exchange holidays excluded).
    #[serde(default)]
    pub tdte: u8,
    pub strike_step: u32,
    pub min_strike: u32,
    pub n_strikes: u32,
    pub spot: Vec<SpotBar>,  // MINUTES
    pub calls: Vec<OhlcBar>, // n_strikes * MINUTES
    pub puts: Vec<OhlcBar>,  // n_strikes * MINUTES
}

impl TradingDayData {
    #[inline]
    pub fn strike_index(&self, strike: u32) -> Option<usize> {
        if strike < self.min_strike || (strike - self.min_strike) % self.strike_step != 0 {
            return None;
        }
        let i = ((strike - self.min_strike) / self.strike_step) as usize;
        if i < self.n_strikes as usize {
            Some(i)
        } else {
            None
        }
    }

    #[inline]
    pub fn strike_at(&self, idx: usize) -> u32 {
        self.min_strike + idx as u32 * self.strike_step
    }

    #[inline]
    pub fn bar(&self, strike: u32, is_call: bool, minute: usize) -> Option<&OhlcBar> {
        let i = self.strike_index(strike)?;
        let v = if is_call { &self.calls } else { &self.puts };
        let b = &v[i * MINUTES + minute];
        if b.is_valid() {
            Some(b)
        } else {
            None
        }
    }

    pub fn meta(&self) -> DayMetadata {
        DayMetadata {
            trade_date: self.trade_date,
            expiry_date: self.expiry_date,
            dte: self.dte,
            tdte: self.tdte,
            weekday: self.weekday,
            strike_step: self.strike_step,
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct DayMetadata {
    pub trade_date: u32,
    pub expiry_date: u32,
    pub dte: u8,
    pub tdte: u8,
    pub weekday: u8,
    pub strike_step: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Side {
    Buy,
    Sell,
}

impl Side {
    /// +1 for a long position, -1 for a short one.
    #[inline]
    pub fn sign(self) -> f64 {
        match self {
            Side::Buy => 1.0,
            Side::Sell => -1.0,
        }
    }
    #[inline]
    pub fn opposite(self) -> Side {
        match self {
            Side::Buy => Side::Sell,
            Side::Sell => Side::Buy,
        }
    }
}

/// The full on-disk cache: a vector of days sorted by `trade_date`.
#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct ChainCache {
    pub instrument: String,
    pub days: Vec<TradingDayData>,
}

/// Wall-clock time at which a fill on bar `m` happens = the bar's CLOSE (AlgoTest convention:
/// the "09:20" candle is the broker's 09:19:00-09:19:59 bar).
pub fn minute_to_hhmm(m: usize) -> String {
    let t = 9 * 60 + 15 + m + 1;
    format!("{:02}:{:02}", t / 60, t % 60)
}
