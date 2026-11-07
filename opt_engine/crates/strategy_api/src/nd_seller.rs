//! `NdSeller` — a fully parameterised intraday NON-DIRECTIONAL option-selling strategy.
//!
//! One JSON config covers: short straddle (synthetic-ATM), premium-matched strangle, fixed-offset
//! strangle; far-OTM margin wings; time-split tranches; opening-range filter; DTE / weekday
//! filters with per-DTE overrides; per-leg or combined SL; move-SL-to-cost; re-entry on cost;
//! wait-and-trade; rolling/balancing; portfolio max-loss, target and trailing profit lock.

use crate::{IntradayStrategy, MarketView};
use core_types::{DayMetadata, Side};
use oms_simulator::VirtualOms;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct NdConfig {
    pub name: String,
    /// "straddle" | "strangle_premium" | "strangle_offset"
    pub structure: String,
    pub target_premium: f32,
    pub otm_steps: i32,
    /// Buy far-OTM wings closest to this premium (0 = naked). Wings are for margin benefit.
    pub hedge_premium: f32,
    /// Wings must be at least this many strike steps beyond the short strikes.
    pub hedge_min_steps: i32,
    pub dte_allowed: Vec<u8>,
    pub weekdays: Vec<u8>,
    /// Tranche entry minutes (minute_idx; 10 = 09:25). Each tranche sells `lots`.
    pub entry_minutes: Vec<usize>,
    pub lots: u32,
    pub or_minutes: usize,
    /// Skip the day if the opening range (high-low over the first `or_minutes`) exceeds this % of spot.
    pub or_filter_pct: f32,
    /// "leg" | "combined"
    pub sl_mode: String,
    pub sl_pct: f32,
    pub combined_sl_pct: f32,
    pub move_sl_to_cost: bool,
    /// After one leg is stopped, other legs' SL = entry * (1 + cost_offset).
    pub cost_offset: f32,
    pub max_reentries: u32,
    pub reentry_cutoff: usize,
    /// Wait & trade: only sell a leg once it has decayed by this % from its reference price.
    pub wt_drop_pct: f32,
    pub wt_window: usize,
    /// Portfolio limits in premium points per lot of the structure.
    pub max_loss_pts: f32,
    pub target_pts: f32,
    pub lock_trigger_pts: f32,
    pub lock_pct: f32,
    pub trail_step_pts: f32,
    pub trail_by_pts: f32,
    pub exit_minute: usize,
    /// Roll the decayed leg when |CE-PE|/(CE+PE) exceeds this ratio (0 = off).
    pub roll_ratio: f32,
    pub max_rolls: u32,
    pub roll_cutoff: usize,
    /// Per-DTE parameter overrides: keys "0", "1", "2-3", "4-99" -> partial config objects.
    pub dte_overrides: BTreeMap<String, Value>,
}

impl Default for NdConfig {
    fn default() -> Self {
        NdConfig {
            name: "nd_seller".into(),
            structure: "straddle".into(),
            target_premium: 60.0,
            otm_steps: 2,
            hedge_premium: 3.0,
            hedge_min_steps: 4,
            dte_allowed: vec![],
            weekdays: vec![],
            entry_minutes: vec![10],
            lots: 1,
            or_minutes: 15,
            or_filter_pct: 0.0,
            sl_mode: "leg".into(),
            sl_pct: 30.0,
            combined_sl_pct: 20.0,
            move_sl_to_cost: false,
            cost_offset: 0.0,
            max_reentries: 0,
            reentry_cutoff: 300,
            wt_drop_pct: 0.0,
            wt_window: 60,
            max_loss_pts: 0.0,
            target_pts: 0.0,
            lock_trigger_pts: 0.0,
            lock_pct: 0.5,
            trail_step_pts: 0.0,
            trail_by_pts: 0.0,
            exit_minute: 365,
            roll_ratio: 0.0,
            max_rolls: 0,
            roll_cutoff: 300,
            dte_overrides: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum LegState {
    Pending { ref_px: f64, deadline: usize },
    Open,
    Stopped,
    Closed,
}

#[derive(Clone, Debug)]
struct Leg {
    tranche: usize,
    strike: u32,
    is_call: bool,
    pos: Option<usize>,
    first_entry: f64,
    reentries: u32,
    state: LegState,
}

pub struct NdSeller {
    base: Value,
    pub cfg: NdConfig,
    active: bool,
    done: bool,
    legs: Vec<Leg>,
    hedges: Vec<usize>,
    tranche_started: Vec<bool>,
    tranche_combined_entry: Vec<f64>,
    rolls: u32,
    lock_floor: Option<f64>,
    or_checked: bool,
}

fn merge(a: &mut Value, b: &Value) {
    if let (Value::Object(ao), Value::Object(bo)) = (a, b) {
        for (k, v) in bo {
            ao.insert(k.clone(), v.clone());
        }
    }
}

fn dte_key_matches(key: &str, dte: u8) -> bool {
    if let Some((a, b)) = key.split_once('-') {
        match (a.trim().parse::<u8>(), b.trim().parse::<u8>()) {
            (Ok(a), Ok(b)) => dte >= a && dte <= b,
            _ => false,
        }
    } else {
        key.trim().parse::<u8>().map(|k| k == dte).unwrap_or(false)
    }
}

impl NdSeller {
    pub fn from_value(v: Value) -> Result<Self, String> {
        let cfg: NdConfig = serde_json::from_value(v.clone()).map_err(|e| e.to_string())?;
        Ok(NdSeller {
            base: v,
            cfg,
            active: false,
            done: false,
            legs: vec![],
            hedges: vec![],
            tranche_started: vec![],
            tranche_combined_entry: vec![],
            rolls: 0,
            lock_floor: None,
            or_checked: false,
        })
    }

    fn units(&self) -> f64 {
        let n = self.tranche_started.iter().filter(|x| **x).count().max(1);
        (n as u32 * self.cfg.lots) as f64
    }

    fn exit_all(&mut self, oms: &mut VirtualOms, reason: &str) {
        oms.square_off_all(reason);
        for l in self.legs.iter_mut() {
            l.state = LegState::Closed;
        }
        self.done = true;
    }

    fn sell_leg(&mut self, li: usize, oms: &mut VirtualOms) -> bool {
        let (strike, is_call, tr) = (self.legs[li].strike, self.legs[li].is_call, self.legs[li].tranche);
        let tag = format!("T{}{}", tr, if is_call { "CE" } else { "PE" });
        match oms.submit_market(strike, is_call, Side::Sell, self.cfg.lots, &tag) {
            Ok(id) => {
                let px = oms.positions[id].entry_price;
                if self.cfg.sl_mode == "leg" && self.cfg.sl_pct > 0.0 {
                    oms.set_stop_loss(id, px * (1.0 + self.cfg.sl_pct as f64 / 100.0));
                }
                let l = &mut self.legs[li];
                if l.first_entry == 0.0 {
                    l.first_entry = px;
                }
                l.pos = Some(id);
                l.state = LegState::Open;
                true
            }
            Err(_) => false,
        }
    }

    fn pick_shorts(&self, mk: &MarketView) -> Option<(u32, u32)> {
        let step = mk.strike_step() as i64;
        match self.cfg.structure.as_str() {
            "straddle" => {
                let k = mk.atm_by_synthetic();
                Some((k, k))
            }
            "strangle_offset" => {
                let k = mk.atm_by_synthetic() as i64;
                Some(((k + self.cfg.otm_steps as i64 * step) as u32, (k - self.cfg.otm_steps as i64 * step) as u32))
            }
            _ => {
                let atm = mk.atm_by_synthetic();
                let ce = mk.select_strike_by_premium_from(true, self.cfg.target_premium, atm)?;
                let pe = mk.select_strike_by_premium_from(false, self.cfg.target_premium, atm)?;
                Some((ce, pe))
            }
        }
    }

    fn start_tranche(&mut self, t: usize, m: usize, mk: &MarketView, oms: &mut VirtualOms) {
        let (ce, pe) = match self.pick_shorts(mk) {
            Some(x) => x,
            None => return,
        };
        let step = mk.strike_step();
        if self.cfg.hedge_premium > 0.0 {
            let piv_c = ce + self.cfg.hedge_min_steps.max(1) as u32 * step;
            let piv_p = pe.saturating_sub(self.cfg.hedge_min_steps.max(1) as u32 * step);
            let wc = mk.select_strike_by_premium_from(true, self.cfg.hedge_premium, piv_c);
            let wp = mk.select_strike_by_premium_from(false, self.cfg.hedge_premium, piv_p);
            match (wc, wp) {
                (Some(wc), Some(wp)) => {
                    // the shorts must be tradeable too, otherwise do not buy wings at all
                    let ok_c = mk.option_bar(ce, true).map(|b| b.volume > 0).unwrap_or(false);
                    let ok_p = mk.option_bar(pe, false).map(|b| b.volume > 0).unwrap_or(false);
                    if !(ok_c && ok_p) {
                        return;
                    }
                    let a = oms.submit_market(wc, true, Side::Buy, self.cfg.lots, &format!("T{}HCE", t));
                    let b = oms.submit_market(wp, false, Side::Buy, self.cfg.lots, &format!("T{}HPE", t));
                    if let Ok(a) = a {
                        self.hedges.push(a);
                    }
                    if let Ok(b) = b {
                        self.hedges.push(b);
                    }
                }
                _ => return, // capital model requires wings; skip tranche if none
            }
        }
        self.tranche_started[t] = true;
        let mut combined = 0.0;
        for (strike, is_call) in [(ce, true), (pe, false)] {
            let li = self.legs.len();
            self.legs.push(Leg { tranche: t, strike, is_call, pos: None, first_entry: 0.0, reentries: 0, state: LegState::Closed });
            if self.cfg.wt_drop_pct > 0.0 {
                if let Some(b) = mk.option_bar(strike, is_call) {
                    self.legs[li].state = LegState::Pending { ref_px: b.close as f64, deadline: m + self.cfg.wt_window };
                }
            } else if self.sell_leg(li, oms) {
                combined += oms.positions[self.legs[li].pos.unwrap()].entry_price;
            }
        }
        self.tranche_combined_entry[t] = combined;
    }
}

impl IntradayStrategy for NdSeller {
    fn on_day_start(&mut self, meta: &DayMetadata) -> bool {
        let mut v = self.base.clone();
        if let Some(Value::Object(ov)) = self.base.get("dte_overrides") {
            for (k, o) in ov {
                if dte_key_matches(k, meta.dte) {
                    merge(&mut v, o);
                    break;
                }
            }
        }
        if let Ok(c) = serde_json::from_value::<NdConfig>(v) {
            self.cfg = c;
        }
        self.legs.clear();
        self.hedges.clear();
        self.tranche_started = vec![false; self.cfg.entry_minutes.len()];
        self.tranche_combined_entry = vec![0.0; self.cfg.entry_minutes.len()];
        self.rolls = 0;
        self.lock_floor = None;
        self.or_checked = false;
        self.done = false;
        let dte_ok = self.cfg.dte_allowed.is_empty() || self.cfg.dte_allowed.contains(&meta.dte);
        let wd_ok = self.cfg.weekdays.is_empty() || self.cfg.weekdays.contains(&meta.weekday);
        let skip = self.base.get("dte_overrides").and_then(|o| o.as_object()).map(|ov| {
            ov.iter().any(|(k, o)| dte_key_matches(k, meta.dte) && o.get("skip").and_then(|x| x.as_bool()).unwrap_or(false))
        });
        self.active = dte_ok && wd_ok && !skip.unwrap_or(false);
        self.active
    }

    fn on_minute(&mut self, m: usize, mk: &MarketView, oms: &mut VirtualOms) {
        if !self.active || self.done {
            return;
        }
        // 1. react to stops fired this minute
        let events: Vec<_> = oms.events.iter().filter(|e| e.kind == "SL").map(|e| e.position_id).collect();
        for pid in events {
            if let Some(li) = self.legs.iter().position(|l| l.pos == Some(pid)) {
                self.legs[li].state = LegState::Stopped;
                if self.cfg.move_sl_to_cost {
                    let tr = self.legs[li].tranche;
                    for l in self.legs.iter() {
                        if l.tranche == tr && l.state == LegState::Open {
                            let id = l.pos.unwrap();
                            let e = oms.positions[id].entry_price;
                            let new_sl = e * (1.0 + self.cfg.cost_offset as f64);
                            let cur = oms.positions[id].stop.unwrap_or(f64::MAX);
                            if new_sl < cur {
                                oms.set_stop_loss(id, new_sl);
                            }
                        }
                    }
                }
            }
        }
        // 2. portfolio level checks
        let units = self.units();
        let any_started = self.tranche_started.iter().any(|x| *x);
        if any_started {
            let mtm = oms.mtm_points();
            if self.cfg.max_loss_pts > 0.0 && mtm <= -(self.cfg.max_loss_pts as f64) * units {
                return self.exit_all(oms, "MAXLOSS");
            }
            if self.cfg.target_pts > 0.0 && mtm >= self.cfg.target_pts as f64 * units {
                return self.exit_all(oms, "TARGET");
            }
            if self.cfg.lock_trigger_pts > 0.0 {
                let trig = self.cfg.lock_trigger_pts as f64 * units;
                if mtm >= trig {
                    let mut floor = self.cfg.lock_trigger_pts as f64 * self.cfg.lock_pct as f64;
                    if self.cfg.trail_step_pts > 0.0 {
                        let steps = ((mtm - trig) / (self.cfg.trail_step_pts as f64 * units)).floor();
                        floor += steps * self.cfg.trail_by_pts as f64;
                    }
                    let floor = floor * units;
                    self.lock_floor = Some(self.lock_floor.map(|f| f.max(floor)).unwrap_or(floor));
                }
                if let Some(f) = self.lock_floor {
                    if mtm <= f {
                        return self.exit_all(oms, "LOCK");
                    }
                }
            }
        }
        if m >= self.cfg.exit_minute {
            return self.exit_all(oms, "TIME");
        }
        // 3. opening range filter
        if self.cfg.or_filter_pct > 0.0 && !self.or_checked {
            if m < self.cfg.or_minutes {
                return;
            }
            self.or_checked = true;
            let h = mk.spot_history();
            let hi = h.iter().map(|b| b.high).fold(f32::MIN, f32::max);
            let lo = h.iter().map(|b| b.low).fold(f32::MAX, f32::min);
            if (hi - lo) / h[0].open * 100.0 > self.cfg.or_filter_pct {
                self.done = true;
                return;
            }
        }
        // 4. tranche entries (delayed to the OR window end if needed)
        for t in 0..self.cfg.entry_minutes.len() {
            let em = self.cfg.entry_minutes[t].max(if self.cfg.or_filter_pct > 0.0 { self.cfg.or_minutes } else { 0 });
            if !self.tranche_started[t] && m >= em && m <= em + 5 {
                self.start_tranche(t, m, mk, oms);
            }
        }
        // 5. wait & trade pending legs
        for li in 0..self.legs.len() {
            if let LegState::Pending { ref_px, deadline } = self.legs[li].state {
                if m > deadline {
                    self.legs[li].state = LegState::Closed;
                    continue;
                }
                if let Some(b) = mk.option_bar(self.legs[li].strike, self.legs[li].is_call) {
                    if (b.close as f64) <= ref_px * (1.0 - self.cfg.wt_drop_pct as f64 / 100.0) && b.volume > 0 {
                        self.sell_leg(li, oms);
                    }
                }
            }
        }
        // 6. combined-premium SL per tranche
        if self.cfg.sl_mode == "combined" && self.cfg.combined_sl_pct > 0.0 {
            for t in 0..self.tranche_started.len() {
                let entry = self.tranche_combined_entry[t];
                if !self.tranche_started[t] || entry <= 0.0 {
                    continue;
                }
                let open: Vec<usize> = (0..self.legs.len()).filter(|&i| self.legs[i].tranche == t && self.legs[i].state == LegState::Open).collect();
                if open.is_empty() {
                    continue;
                }
                let cur: f64 = open.iter().map(|&i| oms.mark(self.legs[i].strike, self.legs[i].is_call).unwrap_or(0.0)).sum();
                let entry_open: f64 = open.iter().map(|&i| oms.positions[self.legs[i].pos.unwrap()].entry_price).sum();
                if cur >= entry_open * (1.0 + self.cfg.combined_sl_pct as f64 / 100.0) {
                    for &i in &open {
                        let _ = oms.close_position(self.legs[i].pos.unwrap(), "CSL");
                        self.legs[i].state = LegState::Stopped;
                    }
                }
            }
        }
        // 7. re-entry on cost
        if self.cfg.max_reentries > 0 && m <= self.cfg.reentry_cutoff {
            for li in 0..self.legs.len() {
                let l = &self.legs[li];
                if l.state == LegState::Stopped && l.reentries < self.cfg.max_reentries {
                    if let Some(b) = mk.option_bar(l.strike, l.is_call) {
                        if b.volume > 0 && (b.close as f64) <= l.first_entry {
                            if self.sell_leg(li, oms) {
                                self.legs[li].reentries += 1;
                            }
                        }
                    }
                }
            }
        }
        // 8. rolling / balancing
        if self.cfg.roll_ratio > 0.0 && self.rolls < self.cfg.max_rolls && m <= self.cfg.roll_cutoff {
            for t in 0..self.tranche_started.len() {
                let ce = self.legs.iter().position(|l| l.tranche == t && l.is_call && l.state == LegState::Open);
                let pe = self.legs.iter().position(|l| l.tranche == t && !l.is_call && l.state == LegState::Open);
                if let (Some(ci), Some(pi)) = (ce, pe) {
                    let c = oms.mark(self.legs[ci].strike, true).unwrap_or(0.0);
                    let p = oms.mark(self.legs[pi].strike, false).unwrap_or(0.0);
                    if c + p <= 0.0 || ((c - p).abs() / (c + p)) as f32 <= self.cfg.roll_ratio {
                        continue;
                    }
                    let (dec, other, target) = if c < p { (ci, pi, p) } else { (pi, ci, c) };
                    let is_call = self.legs[dec].is_call;
                    let other_strike = self.legs[other].strike;
                    // never cross the other leg (at most an inverted-free straddle)
                    let new_strike = mk.select_strike_by_premium_from(is_call, target as f32, other_strike);
                    if let Some(ns) = new_strike {
                        if ns == self.legs[dec].strike {
                            continue;
                        }
                        let _ = oms.close_position(self.legs[dec].pos.unwrap(), "ROLL");
                        self.legs[dec].state = LegState::Closed;
                        let li = self.legs.len();
                        self.legs.push(Leg { tranche: t, strike: ns, is_call, pos: None, first_entry: 0.0, reentries: 0, state: LegState::Closed });
                        self.sell_leg(li, oms);
                        self.rolls += 1;
                    }
                }
            }
        }
        // 9. nothing left to manage -> release wings and stop for the day
        let all_entries_done = self
            .cfg
            .entry_minutes
            .iter()
            .enumerate()
            .all(|(t, &em)| self.tranche_started[t] || m > em.max(self.cfg.or_minutes) + 5);
        if all_entries_done && any_started {
            let open_or_pending = self.legs.iter().any(|l| matches!(l.state, LegState::Open | LegState::Pending { .. }));
            let reentry_possible = self.cfg.max_reentries > 0
                && m < self.cfg.reentry_cutoff
                && self.legs.iter().any(|l| l.state == LegState::Stopped && l.reentries < self.cfg.max_reentries);
            if !open_or_pending && !reentry_possible {
                self.exit_all(oms, "FLAT");
            }
        }
    }

    fn on_day_end(&mut self, oms: &mut VirtualOms) {
        oms.square_off_all("EOD");
    }
}
