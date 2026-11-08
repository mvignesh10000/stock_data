//! `AlgoTestStrategy` — a strategy whose JSON config maps 1:1 onto the AlgoTest
//! (https://docs.algotest.in) time-based strategy builder, so anything found here can be typed into
//! AlgoTest and deployed without translation.
//!
//! Semantics follow the AlgoTest docs:
//! * Times are AlgoTest times: "09:20" = close of the broker's 09:19 one-minute candle.
//! * Leg SL / Target are evaluated on the 1-minute high/low (gap-through fills at the next open);
//!   Overall SL / Target / Lock / Lock&Trail / Overall Trail-SL are evaluated at candle close
//!   (exactly how AlgoTest's backtester does it).
//! * Square-off Partial / Complete, Trail-SL-to-breakeven (SL legs | all legs), Trail SL X-Y,
//!   RE-ASAP / RE-COST / RE-MOMENTUM re-entries with counts and "No re-entry after",
//!   Simple Momentum (premium % / pts up/down), strike criteria ATM/OTMn/ITMn, Closest premium,
//!   Premium >=, Straddle width, ATM-straddle-premium %, cash or synthetic-future ATM,
//!   DTE filter in TRADING days, quantity multiplier.
//! * Overall MTM values are ₹ for multiplier 1 and are scaled by the quantity multiplier (AlgoTest rule).
//! Extra realism (not an AlgoTest setting): margin-based sizing using the SPAN-calibrated margin model,
//! pessimistic same-bar re-check after stops are moved.

use crate::{IntradayStrategy, MarketView};
use core_types::{DayMetadata, Side};
use oms_simulator::{MarginLeg, VirtualOms};
use serde::{Deserialize, Serialize};

pub fn hhmm_to_idx(t: &str) -> usize {
    let mut it = t.split(':');
    let h: i64 = it.next().and_then(|x| x.trim().parse().ok()).unwrap_or(9);
    let m: i64 = it.next().and_then(|x| x.trim().parse().ok()).unwrap_or(20);
    // AlgoTest "HH:MM" == close of the candle that starts one minute earlier
    (h * 60 + m - (9 * 60 + 15) - 1).clamp(0, 374) as usize
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct StrikeCfg {
    /// "atm" | "otm" | "itm" | "closest_premium" | "premium_gte" | "straddle_width" | "atm_premium_pct"
    pub mode: String,
    pub n: i32,
    pub value: f32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Thr {
    /// SL/Target: "pct" | "pts".  Momentum: "pct_up" | "pct_down" | "pts_up" | "pts_down"
    pub kind: String,
    pub value: f32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TrailCfg {
    pub kind: String, // "pct" | "pts"
    pub x: f32,
    pub y: f32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ReCfg {
    pub kind: String, // "asap" | "cost" | "momentum"
    pub count: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct LegCfg {
    pub side: String, // "sell" | "buy"
    pub opt: String,  // "CE" | "PE"
    pub lots: u32,
    pub strike: StrikeCfg,
    pub sl: Option<Thr>,
    pub target: Option<Thr>,
    pub trail: Option<TrailCfg>,
    pub re_sl: Option<ReCfg>,
    pub re_tgt: Option<ReCfg>,
    pub momentum: Option<Thr>,
    /// AlgoTest "Range Breakout": range from the strategy entry time to `end`; enter when the
    /// underlying (or the instrument) breaks the range `side` ("high" | "low"). Strike is fixed at entry time.
    pub orb: Option<OrbCfg>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OrbCfg {
    pub end: String,
    pub side: String,
    #[serde(default = "default_orb_on")]
    pub on: String,
}
fn default_orb_on() -> String {
    "underlying".into()
}

impl Default for LegCfg {
    fn default() -> Self {
        LegCfg { side: "sell".into(), opt: "CE".into(), lots: 1, strike: StrikeCfg { mode: "atm".into(), n: 0, value: 0.0 }, sl: None, target: None, trail: None, re_sl: None, re_tgt: None, momentum: None, orb: None }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct OverallCfg {
    /// ₹ per quantity-multiplier 1 (0 = off)
    pub sl_mtm: f64,
    pub tgt_mtm: f64,
    /// % of total (net) entry premium (0 = off)
    pub sl_prem_pct: f64,
    pub tgt_prem_pct: f64,
    /// Lock: when MTM reaches `lock_reach`, lock `lock_profit`.  Lock&Trail: then for every
    /// `trail_every` further profit raise the lock by `trail_by`.
    pub lock_reach: f64,
    pub lock_profit: f64,
    pub trail_every: f64,
    pub trail_by: f64,
    /// Overall Trail SL (MTM): for every `trail_sl_x` profit reduce the overall SL by `trail_sl_y`.
    pub trail_sl_x: f64,
    pub trail_sl_y: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct SizingCfg {
    /// "fixed" (use `multiplier`) | "margin" (largest multiplier whose margin <= capital*util)
    pub mode: String,
    pub multiplier: u32,
    pub capital: f64,
    pub util: f64,
    pub max_multiplier: u32,
}

impl Default for SizingCfg {
    fn default() -> Self {
        SizingCfg { mode: "fixed".into(), multiplier: 1, capital: 200_000.0, util: 0.9, max_multiplier: 10 }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct AtConfig {
    pub name: String,
    pub entry_time: String,
    pub exit_time: String,
    pub no_reentry_after: String,
    /// trading-day DTE filter (empty = every day)
    pub dte: Vec<u8>,
    pub weekdays: Vec<u8>,
    /// "cash" | "synthetic"
    pub underlying: String,
    pub legs: Vec<LegCfg>,
    /// "partial" | "complete"
    pub square_off: String,
    /// "none" | "sl_legs" | "all_legs"
    pub trail_to_breakeven: String,
    pub overall: OverallCfg,
    pub sizing: SizingCfg,
    /// Manual activation calendar (e.g. VIX regime decided before the open). Empty = every day.
    pub allowed_dates: Vec<u32>,
}

impl Default for AtConfig {
    fn default() -> Self {
        AtConfig {
            name: "algotest".into(),
            entry_time: "09:20".into(),
            exit_time: "15:15".into(),
            no_reentry_after: "15:00".into(),
            dte: vec![],
            weekdays: vec![],
            underlying: "cash".into(),
            legs: vec![],
            square_off: "partial".into(),
            trail_to_breakeven: "none".into(),
            overall: OverallCfg::default(),
            sizing: SizingCfg::default(),
            allowed_dates: vec![],
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum St {
    Idle,
    /// waiting for a premium move from `reference` (momentum / RE-MOMENTUM) on a fixed strike
    WaitMomentum { reference: f64, since: usize },
    /// RE-COST: waiting for the same strike to return to `price`
    WaitCost { price: f64, since: usize },
    /// waiting for a range breakout (range = (entry, end])
    WaitOrb { end: usize },
    Open,
    Done,
}

#[derive(Clone, Debug)]
struct LegRt {
    strike: u32,
    pos: Option<usize>,
    st: St,
    first_entry: f64,
    entry: f64,
    init_sl: Option<f64>,
    best: f64,
    re_sl_used: u32,
    re_tgt_used: u32,
}

pub struct AlgoTestStrategy {
    pub cfg: AtConfig,
    entry_m: usize,
    exit_m: usize,
    noreent_m: usize,
    active: bool,
    done: bool,
    entered: bool,
    mult: u32,
    legs: Vec<LegRt>,
    lock_floor: Option<f64>,
    net_premium_pts: f64,
    peak_mtm: f64,
    pub last_multiplier: u32,
    pub last_margin_1x: f64,
}

impl AlgoTestStrategy {
    pub fn from_value(v: serde_json::Value) -> Result<Self, String> {
        let cfg: AtConfig = serde_json::from_value(v).map_err(|e| e.to_string())?;
        if cfg.legs.is_empty() {
            return Err("strategy has no legs".into());
        }
        Ok(AlgoTestStrategy {
            entry_m: hhmm_to_idx(&cfg.entry_time),
            exit_m: hhmm_to_idx(&cfg.exit_time),
            noreent_m: hhmm_to_idx(&cfg.no_reentry_after),
            cfg,
            active: false,
            done: false,
            entered: false,
            mult: 1,
            legs: vec![],
            lock_floor: None,
            net_premium_pts: 0.0,
            peak_mtm: 0.0,
            last_multiplier: 0,
            last_margin_1x: 0.0,
        })
    }

    fn side(l: &LegCfg) -> Side {
        if l.side.eq_ignore_ascii_case("buy") {
            Side::Buy
        } else {
            Side::Sell
        }
    }

    fn is_call(l: &LegCfg) -> bool {
        l.opt.eq_ignore_ascii_case("CE")
    }

    fn atm(&self, mk: &MarketView) -> u32 {
        if self.cfg.underlying == "synthetic" {
            let f = mk.synthetic_future() as f64;
            let step = mk.strike_step() as f64;
            ((f / step).round() * step) as u32
        } else {
            mk.atm_strike()
        }
    }

    fn closest_premium(mk: &MarketView, is_call: bool, target: f32) -> Option<u32> {
        let mut best: Option<(f32, f32, u32)> = None;
        for s in mk.strikes() {
            if let Some(b) = mk.option_bar(s, is_call) {
                if b.volume == 0 {
                    continue;
                }
                let d = (b.close - target).abs();
                // tie -> lower premium (AlgoTest rule)
                if best.map(|x| d < x.0 || (d == x.0 && b.close < x.1)).unwrap_or(true) {
                    best = Some((d, b.close, s));
                }
            }
        }
        best.map(|x| x.2)
    }

    fn select_strike(&self, l: &LegCfg, mk: &MarketView) -> Option<u32> {
        let is_call = Self::is_call(l);
        let step = mk.strike_step() as i64;
        let atm = self.atm(mk) as i64;
        let k = match l.strike.mode.as_str() {
            "atm" => atm,
            "otm" => if is_call { atm + l.strike.n as i64 * step } else { atm - l.strike.n as i64 * step },
            "itm" => if is_call { atm - l.strike.n as i64 * step } else { atm + l.strike.n as i64 * step },
            "closest_premium" => return Self::closest_premium(mk, is_call, l.strike.value),
            "max_oi" => {
                // OI wall: the OTM strike (within n steps of ATM) with the highest open interest
                let lim = if l.strike.n > 0 { l.strike.n as i64 } else { 20 };
                let mut best: Option<(u32, u32)> = None;
                for j in 1..=lim {
                    let s = if is_call { atm + j * step } else { atm - j * step };
                    if s <= 0 {
                        continue;
                    }
                    if let Some(b) = mk.option_bar(s as u32, is_call) {
                        if best.map(|x| b.oi > x.0).unwrap_or(true) {
                            best = Some((b.oi, s as u32));
                        }
                    }
                }
                return best.map(|x| x.1);
            }
            "premium_gte" => {
                let mut best: Option<(f32, u32)> = None;
                for s in mk.strikes() {
                    if let Some(b) = mk.option_bar(s, is_call) {
                        if b.volume > 0 && b.close >= l.strike.value && best.map(|x| b.close < x.0).unwrap_or(true) {
                            best = Some((b.close, s));
                        }
                    }
                }
                return best.map(|x| x.1);
            }
            "straddle_width" | "atm_premium_pct" => {
                let a = atm as u32;
                let st = mk.option_bar(a, true)?.close + mk.option_bar(a, false)?.close;
                if l.strike.mode == "atm_premium_pct" {
                    return Self::closest_premium(mk, is_call, st * l.strike.value / 100.0);
                }
                let raw = atm as f64 + l.strike.value as f64 * st as f64;
                ((raw / step as f64).round() as i64) * step
            }
            _ => atm,
        };
        if k <= 0 {
            None
        } else {
            Some(k as u32)
        }
    }

    fn tag(i: usize, n: u32) -> String {
        format!("L{}{}", i + 1, if n > 0 { format!("r{}", n) } else { String::new() })
    }

    fn arm(&mut self, i: usize, id: usize, oms: &mut VirtualOms) {
        let l = self.cfg.legs[i].clone();
        let side = Self::side(&l);
        let px = oms.positions[id].entry_price;
        let rt = &mut self.legs[i];
        rt.pos = Some(id);
        rt.st = St::Open;
        rt.entry = px;
        if rt.first_entry == 0.0 {
            rt.first_entry = px;
        }
        rt.best = px;
        rt.init_sl = None;
        if let Some(sl) = &l.sl {
            let d = if sl.kind == "pts" { sl.value as f64 } else { px * sl.value as f64 / 100.0 };
            let p = match side {
                Side::Sell => px + d,
                Side::Buy => (px - d).max(0.0),
            };
            oms.set_stop_loss(id, p);
            rt.init_sl = Some(p);
        }
        if let Some(t) = &l.target {
            let d = if t.kind == "pts" { t.value as f64 } else { px * t.value as f64 / 100.0 };
            let p = match side {
                Side::Sell => (px - d).max(0.05),
                Side::Buy => px + d,
            };
            oms.set_target(id, p);
        }
    }

    fn enter_market(&mut self, i: usize, strike: u32, oms: &mut VirtualOms, n: u32) -> bool {
        let l = &self.cfg.legs[i];
        let (side, is_call, lots) = (Self::side(l), Self::is_call(l), l.lots * self.mult);
        match oms.submit_market(strike, is_call, side, lots, &Self::tag(i, n)) {
            Ok(id) => {
                self.legs[i].strike = strike;
                self.arm(i, id, oms);
                true
            }
            Err(_) => false,
        }
    }

    fn mom_trigger(m: &Thr, reference: f64) -> (f64, bool) {
        // (trigger price, is_up)
        match m.kind.as_str() {
            "pct_up" => (reference * (1.0 + m.value as f64 / 100.0), true),
            "pts_up" => (reference + m.value as f64, true),
            "pts_down" => ((reference - m.value as f64).max(0.05), false),
            _ => ((reference * (1.0 - m.value as f64 / 100.0)).max(0.05), false),
        }
    }

    fn exit_all(&mut self, oms: &mut VirtualOms, reason: &str) {
        oms.square_off_all(reason);
        for l in self.legs.iter_mut() {
            l.st = St::Done;
        }
        self.done = true;
    }

    /// leg-level re-entry after an SL/TGT exit of leg i at minute m
    fn schedule_reentry(&mut self, i: usize, was_sl: bool, m: usize, mk: &MarketView, oms: &mut VirtualOms) {
        let l = self.cfg.legs[i].clone();
        let re = if was_sl { l.re_sl.clone() } else { l.re_tgt.clone() };
        let used = if was_sl { self.legs[i].re_sl_used } else { self.legs[i].re_tgt_used };
        let re = match re {
            Some(r) if used < r.count && m <= self.noreent_m && m < self.exit_m => r,
            _ => {
                self.legs[i].st = St::Done;
                return;
            }
        };
        if was_sl {
            self.legs[i].re_sl_used += 1;
        } else {
            self.legs[i].re_tgt_used += 1;
        }
        let n = self.legs[i].re_sl_used + self.legs[i].re_tgt_used;
        match re.kind.as_str() {
            "cost" => {
                let p = self.legs[i].first_entry;
                self.legs[i].st = St::WaitCost { price: p, since: m };
            }
            "momentum" if l.momentum.is_some() => {
                if let Some(k) = self.select_strike(&l, mk) {
                    if let Some(b) = mk.option_bar(k, Self::is_call(&l)) {
                        self.legs[i].strike = k;
                        self.legs[i].st = St::WaitMomentum { reference: b.close as f64, since: m };
                        return;
                    }
                }
                self.legs[i].st = St::Done;
            }
            _ => {
                // RE-ASAP (and RE-MOMENTUM without momentum behaves like RE-ASAP)
                match self.select_strike(&l, mk) {
                    Some(k) if self.enter_market(i, k, oms, n) => {}
                    _ => self.legs[i].st = St::Done,
                }
            }
        }
    }
}

impl IntradayStrategy for AlgoTestStrategy {
    fn on_day_start(&mut self, meta: &DayMetadata) -> bool {
        self.legs = self
            .cfg
            .legs
            .iter()
            .map(|_| LegRt { strike: 0, pos: None, st: St::Idle, first_entry: 0.0, entry: 0.0, init_sl: None, best: 0.0, re_sl_used: 0, re_tgt_used: 0 })
            .collect();
        self.done = false;
        self.entered = false;
        self.lock_floor = None;
        self.net_premium_pts = 0.0;
        self.peak_mtm = 0.0;
        self.mult = self.cfg.sizing.multiplier.max(1);
        self.last_multiplier = 0;
        self.last_margin_1x = 0.0;
        let dte_ok = self.cfg.dte.is_empty() || self.cfg.dte.contains(&meta.tdte);
        let wd_ok = self.cfg.weekdays.is_empty() || self.cfg.weekdays.contains(&meta.weekday);
        let date_ok = self.cfg.allowed_dates.is_empty() || self.cfg.allowed_dates.binary_search(&meta.trade_date).is_ok();
        self.active = dte_ok && wd_ok && date_ok;
        self.active
    }

    fn on_minute(&mut self, m: usize, mk: &MarketView, oms: &mut VirtualOms) {
        if !self.active || self.done {
            return;
        }
        // ---------------------------------------------------------------- initial entry
        if !self.entered {
            if m < self.entry_m {
                return;
            }
            self.entered = true;
            // strikes for all legs at entry time
            let mut strikes = vec![];
            for l in self.cfg.legs.clone() {
                match self.select_strike(&l, mk) {
                    Some(k) if mk.option_bar(k, Self::is_call(&l)).is_some() => strikes.push(k),
                    _ => {
                        self.done = true; // a leg cannot be priced: AlgoTest would error -> skip day
                        return;
                    }
                }
            }
            // sizing on margin (hedges reduce SPAN)
            let legs1: Vec<MarginLeg> = self.cfg.legs.iter().zip(&strikes).map(|(l, &k)| (k, Self::is_call(l), Self::side(l), l.lots)).collect();
            let premium_paid: f64 = self.cfg.legs.iter().zip(&strikes)
                .filter(|(l, _)| Self::side(l) == Side::Buy)
                .map(|(l, &k)| mk.option_bar(k, Self::is_call(l)).map(|b| b.close as f64).unwrap_or(0.0) * l.lots as f64 * oms.cfg.lot_size)
                .sum();
            let m1 = oms.margin_with(&legs1) + premium_paid;
            self.last_margin_1x = m1;
            if self.cfg.sizing.mode == "margin" {
                let cap = self.cfg.sizing.capital * self.cfg.sizing.util;
                let k = if m1 > 0.0 { (cap / m1).floor() as u32 } else { self.cfg.sizing.max_multiplier };
                self.mult = k.min(self.cfg.sizing.max_multiplier);
                if self.mult == 0 {
                    self.done = true; // not enough margin today (e.g. expiry-day ELM)
                    return;
                }
            }
            self.last_multiplier = self.mult;
            // buy legs first (margin benefit), then sells
            let mut order: Vec<usize> = (0..self.cfg.legs.len()).collect();
            order.sort_by_key(|&i| if Self::side(&self.cfg.legs[i]) == Side::Buy { 0 } else { 1 });
            for i in order {
                let l = self.cfg.legs[i].clone();
                let k = strikes[i];
                self.legs[i].strike = k;
                if let Some(o) = &l.orb {
                    self.legs[i].st = St::WaitOrb { end: hhmm_to_idx(&o.end) };
                } else if let Some(mo) = &l.momentum {
                    let _ = mo;
                    let r = mk.option_bar(k, Self::is_call(&l)).map(|b| b.close as f64).unwrap_or(0.0);
                    self.legs[i].st = St::WaitMomentum { reference: r, since: m };
                } else if !self.enter_market(i, k, oms, 0) {
                    self.legs[i].st = St::Done;
                }
            }
            self.net_premium_pts = self
                .legs
                .iter()
                .filter_map(|r| r.pos.map(|p| &oms.positions[p]))
                .map(|p| -p.side.sign() * p.entry_price)
                .sum::<f64>()
                .abs();
            return;
        }

        // ---------------------------------------------------------------- leg SL / TGT events (high/low)
        let events: Vec<(usize, &'static str)> = oms.events.iter().map(|e| (e.position_id, e.kind)).collect();
        let mut complete = false;
        for (pid, kind) in events {
            let i = match self.legs.iter().position(|r| r.pos == Some(pid) && r.st == St::Open) {
                Some(i) => i,
                None => continue,
            };
            self.legs[i].st = St::Idle;
            let was_sl = kind == "SL";
            if was_sl && self.cfg.trail_to_breakeven != "none" {
                for j in 0..self.legs.len() {
                    if j == i || self.legs[j].st != St::Open {
                        continue;
                    }
                    if self.cfg.trail_to_breakeven == "sl_legs" && self.cfg.legs[j].sl.is_none() {
                        continue;
                    }
                    let id = self.legs[j].pos.unwrap();
                    let e = oms.positions[id].entry_price;
                    oms.set_stop_loss(id, e);
                    if oms.check_stop_now(id) {
                        self.legs[j].st = St::Idle;
                        self.schedule_reentry(j, true, m, mk, oms);
                    }
                }
            }
            if self.cfg.square_off == "complete" {
                complete = true;
            } else {
                self.schedule_reentry(i, was_sl, m, mk, oms);
            }
        }
        if complete {
            return self.exit_all(oms, "SQ_COMPLETE");
        }

        // ---------------------------------------------------------------- trail SL (after SL check -> pessimistic)
        for i in 0..self.legs.len() {
            if self.legs[i].st != St::Open {
                continue;
            }
            let l = &self.cfg.legs[i];
            let (tr, init) = match (&l.trail, self.legs[i].init_sl) {
                (Some(t), Some(s)) => (t.clone(), s),
                _ => continue,
            };
            let id = self.legs[i].pos.unwrap();
            let p = &oms.positions[id];
            let bar = match mk.option_bar(p.strike, p.is_call) {
                Some(b) => b,
                None => continue,
            };
            let e = self.legs[i].entry;
            let (x, y) = if tr.kind == "pts" { (tr.x as f64, tr.y as f64) } else { (e * tr.x as f64 / 100.0, e * tr.y as f64 / 100.0) };
            if x <= 0.0 {
                continue;
            }
            match p.side {
                Side::Sell => {
                    self.legs[i].best = self.legs[i].best.min(bar.low as f64);
                    let steps = ((e - self.legs[i].best) / x).floor().max(0.0);
                    let ns = init - steps * y;
                    if ns < p.stop.unwrap_or(f64::MAX) {
                        oms.set_stop_loss(id, ns);
                    }
                }
                Side::Buy => {
                    self.legs[i].best = self.legs[i].best.max(bar.high as f64);
                    let steps = ((self.legs[i].best - e) / x).floor().max(0.0);
                    let ns = init + steps * y;
                    if ns > p.stop.unwrap_or(f64::MIN) {
                        oms.set_stop_loss(id, ns);
                    }
                }
            }
        }

        // ---------------------------------------------------------------- overall settings @ candle close
        let mult = self.mult as f64;
        let mtm = oms.mtm_points() * oms.cfg.lot_size; // ₹, like AlgoTest MTM (charges excluded)
        let o = &self.cfg.overall;
        let mut sl_lvl = if o.sl_mtm > 0.0 { Some(o.sl_mtm * mult) } else { None };
        if o.sl_prem_pct > 0.0 {
            let v = self.net_premium_pts * o.sl_prem_pct / 100.0 * oms.cfg.lot_size * mult;
            sl_lvl = Some(sl_lvl.map(|x: f64| x.min(v)).unwrap_or(v));
        }
        if let Some(s) = sl_lvl {
            let mut s = s;
            if o.trail_sl_x > 0.0 {
                // Overall Trail SL: for every X of (peak) profit, reduce the overall SL by Y
                let k = (self.peak_mtm / (o.trail_sl_x * mult)).floor().max(0.0);
                s -= k * o.trail_sl_y * mult;
            }
            if mtm <= -s {
                return self.exit_all(oms, "OVERALL_SL");
            }
        }
        let mut tgt = if o.tgt_mtm > 0.0 { Some(o.tgt_mtm * mult) } else { None };
        if o.tgt_prem_pct > 0.0 {
            let v = self.net_premium_pts * o.tgt_prem_pct / 100.0 * oms.cfg.lot_size * mult;
            tgt = Some(tgt.map(|x: f64| x.min(v)).unwrap_or(v));
        }
        if let Some(t) = tgt {
            if mtm >= t {
                return self.exit_all(oms, "OVERALL_TGT");
            }
        }
        if o.lock_reach > 0.0 {
            let reach = o.lock_reach * mult;
            if mtm >= reach {
                let mut floor = o.lock_profit * mult;
                if o.trail_every > 0.0 {
                    floor += ((mtm - reach) / (o.trail_every * mult)).floor() * o.trail_by * mult;
                }
                self.lock_floor = Some(self.lock_floor.map(|f| f.max(floor)).unwrap_or(floor));
            }
            if let Some(f) = self.lock_floor {
                if mtm <= f {
                    return self.exit_all(oms, "LOCK");
                }
            }
        }
        if mtm > self.peak_mtm {
            self.peak_mtm = mtm;
        }

        // ---------------------------------------------------------------- exit time
        if m >= self.exit_m {
            return self.exit_all(oms, "TIME");
        }

        // ---------------------------------------------------------------- waiting legs (momentum / re-cost)
        for i in 0..self.legs.len() {
            let l = self.cfg.legs[i].clone();
            let n = self.legs[i].re_sl_used + self.legs[i].re_tgt_used;
            match self.legs[i].st {
                St::WaitMomentum { reference, since } if m > since => {
                    let mo = match &l.momentum {
                        Some(x) => x.clone(),
                        None => continue,
                    };
                    let k = self.legs[i].strike;
                    let bar = match mk.option_bar(k, Self::is_call(&l)) {
                        Some(b) if b.volume > 0 => b,
                        _ => continue,
                    };
                    let (tp, up) = Self::mom_trigger(&mo, reference);
                    let hit = if up { bar.high as f64 >= tp } else { bar.low as f64 <= tp };
                    if hit {
                        // limit/SL-L at trigger; a gap through the trigger fills at the (worse for us) open
                        let side = Self::side(&l);
                        let op = bar.open as f64;
                        let px = match (up, side) {
                            (true, Side::Buy) => tp.max(op),
                            (false, Side::Sell) => tp.min(op),
                            _ => tp,
                        };
                        if let Ok(id) = oms.submit_at_price(k, Self::is_call(&l), side, l.lots * self.mult, px, &Self::tag(i, n)) {
                            self.arm(i, id, oms);
                        }
                    }
                }
                St::WaitOrb { end } if m > end => {
                    let o = match &l.orb {
                        Some(o) => o.clone(),
                        None => continue,
                    };
                    let k = self.legs[i].strike;
                    let is_call = Self::is_call(&l);
                    let side = Self::side(&l);
                    let lo_m = self.entry_m + 1;
                    if o.on == "instrument" {
                        let (mut hi, mut lo) = (f64::MIN, f64::MAX);
                        for t in lo_m..=end {
                            if let Some(b) = mk.option_bar_at(k, is_call, t) {
                                hi = hi.max(b.high as f64);
                                lo = lo.min(b.low as f64);
                            }
                        }
                        let bar = match mk.option_bar(k, is_call) {
                            Some(b) if b.volume > 0 => b,
                            _ => continue,
                        };
                        let (hit, px) = if o.side == "high" { (bar.high as f64 > hi, hi.max(bar.open as f64)) } else { (bar.low as f64 >= 0.0 && (bar.low as f64) < lo, lo.min(bar.open as f64)) };
                        if hit && hi > f64::MIN {
                            if let Ok(id) = oms.submit_at_price(k, is_call, side, l.lots * self.mult, px, &Self::tag(i, n)) {
                                self.arm(i, id, oms);
                            }
                        }
                    } else {
                        let hist = mk.spot_history();
                        if hist.len() <= end {
                            continue;
                        }
                        let hi = hist[lo_m..=end].iter().map(|b| b.high).fold(f32::MIN, f32::max);
                        let lo = hist[lo_m..=end].iter().map(|b| b.low).fold(f32::MAX, f32::min);
                        let sb = mk.spot();
                        let hit = if o.side == "high" { sb.high > hi } else { sb.low < lo };
                        if hit {
                            // option bought at this minute's close (+ slippage); AlgoTest checks the index on LTP
                            if self.enter_market(i, k, oms, n) {
                                // reached
                            }
                        }
                    }
                }
                St::WaitCost { price, since } if m > since => {
                    let k = self.legs[i].strike;
                    let side = Self::side(&l);
                    let bar = match mk.option_bar(k, Self::is_call(&l)) {
                        Some(b) if b.volume > 0 => b,
                        _ => continue,
                    };
                    // short re-cost: price must come back DOWN to the original sell price
                    let hit = match side {
                        Side::Sell => bar.low as f64 <= price,
                        Side::Buy => bar.high as f64 >= price,
                    };
                    if hit {
                        let op = bar.open as f64;
                        let px = match side {
                            Side::Sell => price.min(op),
                            Side::Buy => price.max(op),
                        };
                        if let Ok(id) = oms.submit_at_price(k, Self::is_call(&l), side, l.lots * self.mult, px, &Self::tag(i, n)) {
                            self.arm(i, id, oms);
                        }
                    }
                }
                _ => {}
            }
        }
    }

    fn on_day_end(&mut self, oms: &mut VirtualOms) {
        oms.square_off_all("EOD");
    }
}

