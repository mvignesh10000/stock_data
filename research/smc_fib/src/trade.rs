//! Triple-barrier outcomes (E1), tradable simulation (E2), random-entry control and metrics.
use std::collections::BTreeMap;

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde::Serialize;

use chrono::Datelike;

use crate::data::{year_of, Series, Tf};
use crate::detect::{Analysis, FIB_EXT};
use crate::events::Event;
use crate::experiments::Prepared;
use crate::stats;

/// Fraction of equity risked per trade (used only for the daily-return series).
pub const RISK: f64 = 0.01;
const STOP_BUFFER_ATR: f64 = 0.1;

/// The signal bar t has a next bar that trades in the same session (intraday) or exists (daily).
pub fn valid_signal(s: &Series, t: usize) -> bool {
    t + 1 < s.bars.len() && (s.tf == Tf::D1 || t + 1 <= s.sess_end[t])
}

/// Last bar of the window that starts at bar t+1 (H bars, cut at the session end intraday).
fn window_end(s: &Series, t: usize, h: usize) -> usize {
    let n = s.bars.len();
    if s.tf == Tf::M15 {
        (t + h).min(s.sess_end[t])
    } else {
        (t + h).min(n - 1)
    }
}

/// Triple barrier from the next bar's open. Success = upper barrier before lower; a bar that
/// touches both counts as a loss (stop first). Timeouts count as losses.
pub fn barrier_win(s: &Series, atr: f64, t: usize, dir: i8, up: f64, dn: f64, h: usize) -> Option<bool> {
    if !atr.is_finite() || !valid_signal(s, t) {
        return None;
    }
    let entry = s.bars[t + 1].o;
    let w = window_end(s, t, h);
    let (tp, sl) = if dir > 0 { (entry + up * atr, entry - dn * atr) } else { (entry - up * atr, entry + dn * atr) };
    for j in (t + 1)..=w {
        let b = &s.bars[j];
        let (hit_tp, hit_sl) = if dir > 0 { (b.h >= tp, b.l <= sl) } else { (b.l <= tp, b.h >= sl) };
        if hit_sl {
            return Some(false);
        }
        if hit_tp {
            return Some(true);
        }
    }
    Some(false)
}

/// Exit for a trade entered at bar `e` (price `entry`). Stops and targets are checked on
/// each bar; a gap through a level fills at the open. Time exit at the close of the H-th bar
/// (cut at the session end intraday, the MIS square-off).
pub fn simulate(s: &Series, e: usize, dir: i8, stop: f64, target: f64, h: usize) -> (usize, f64) {
    let last = window_end(s, e - 1, h);
    let up = dir > 0;
    for j in e..=last {
        let b = &s.bars[j];
        let gap_stop = if up { b.o <= stop } else { b.o >= stop };
        let gap_tp = if up { b.o >= target } else { b.o <= target };
        if gap_stop || gap_tp {
            return (j, b.o);
        }
        let (hit_sl, hit_tp) = if up { (b.l <= stop, b.h >= target) } else { (b.h >= stop, b.l <= target) };
        if hit_sl {
            return (j, stop);
        }
        if hit_tp {
            return (j, target);
        }
    }
    (last, s.bars[last].c)
}

/// Net result in R after round-trip cost (cost_bps of the entry price).
pub fn net_r(dir: i8, entry: f64, exit: f64, risk: f64, cost_bps: f64) -> f64 {
    ((exit - entry) * dir as f64 - entry * cost_bps / 1e4) / risk
}

#[derive(Clone, Debug, Serialize)]
pub struct TradeRec {
    pub sym: u32,
    pub index: bool,
    pub entry_day: i32,
    pub exit_day: i32,
    pub dir: i8,
    pub r: f64,
    /// target distance in R
    pub rr: f64,
    /// stop distance in ATR units (for the random-entry control)
    pub r_atr: f64,
    pub hold: u32,
}

/// Tradable HPZ/baseline trades. One position per symbol. Entry at the next open after a
/// touch bar that closes in the expected direction. Stop at zone edge minus 0.1 ATR.
/// Target 2R, or the 1.272 Fibonacci extension of the active leg if `ext`.
pub fn e2_trades(s: &Series, sym: u32, an: &Analysis, evs: &[Event], ext: bool, cost_bps: f64, h: usize) -> Vec<TradeRec> {
    let bars = &s.bars;
    let mut out = Vec::new();
    let mut busy_until: Option<usize> = None;
    for ev in evs {
        let t = ev.bar;
        if !valid_signal(s, t) {
            continue;
        }
        if let Some(x) = busy_until {
            if t + 1 <= x {
                continue;
            }
        }
        let b = &bars[t];
        let up = ev.dir > 0;
        if (up && b.c <= b.o) || (!up && b.c >= b.o) {
            continue;
        }
        let a = an.atr[t];
        if !a.is_finite() {
            continue;
        }
        let e = t + 1;
        let entry = bars[e].o;
        let stop = if up { ev.zlo - STOP_BUFFER_ATR * a } else { ev.zhi + STOP_BUFFER_ATR * a };
        let risk = (entry - stop).abs();
        if risk <= 0.0 || (up && entry <= stop) || (!up && entry >= stop) {
            continue;
        }
        let target = if ext {
            let Some(li) = ev.leg else { continue };
            let leg = &an.legs[li];
            let span = leg.hi - leg.lo;
            let tg = if up { leg.lo + FIB_EXT * span } else { leg.hi - FIB_EXT * span };
            if (up && tg <= entry) || (!up && tg >= entry) {
                continue;
            }
            tg
        } else {
            entry + ev.dir as f64 * 2.0 * risk
        };
        let (x, xp) = simulate(s, e, ev.dir, stop, target, h);
        busy_until = Some(x);
        out.push(TradeRec {
            sym,
            index: s.is_index,
            entry_day: s.day[e],
            exit_day: s.day[x],
            dir: ev.dir,
            r: net_r(ev.dir, entry, xp, risk, cost_bps),
            rr: (target - entry).abs() / risk,
            r_atr: risk / a,
            hold: (x - e + 1) as u32,
        });
    }
    out
}

/// Signal bars t with a valid next bar, grouped by calendar year.
pub fn entry_pools(s: &Series) -> BTreeMap<i32, Vec<usize>> {
    let mut m: BTreeMap<i32, Vec<usize>> = BTreeMap::new();
    for t in 0..s.bars.len() {
        if valid_signal(s, t) {
            m.entry(s.bars[t].ts.year()).or_default().push(t);
        }
    }
    m
}

/// Random-entry control: for every real trade, one random signal bar in the same symbol and
/// year, a random direction, the same stop distance in ATR, the same target multiple and the
/// same exit rules and costs. Returns the expectancy (mean net R) of each run.
pub fn random_expectancies(
    prep: &[Prepared],
    trades: &[&TradeRec],
    cost_idx: f64,
    cost_stk: f64,
    h: usize,
    runs: usize,
    seed: u64,
) -> Vec<f64> {
    let mut out = Vec::with_capacity(runs);
    for r in 0..runs {
        let mut rng = ChaCha8Rng::seed_from_u64(seed.wrapping_add(r as u64));
        let (mut sum, mut cnt) = (0.0, 0usize);
        for tr in trades {
            let si = tr.sym as usize;
            let Some(list) = prep[si].pools.get(&year_of(tr.entry_day)) else { continue };
            if list.is_empty() {
                continue;
            }
            let t = list[rng.gen_range(0..list.len())];
            let s = &prep[si].s;
            let a = prep[si].atr[t];
            let dir: i8 = if rng.gen_bool(0.5) { 1 } else { -1 };
            let e = t + 1;
            let entry = s.bars[e].o;
            let risk = tr.r_atr * a;
            let stop = entry - dir as f64 * risk;
            let target = entry + dir as f64 * tr.rr * risk;
            let cost = if tr.index { cost_idx } else { cost_stk };
            let (_, xp) = simulate(s, e, dir, stop, target, h);
            sum += net_r(dir, entry, xp, risk, cost);
            cnt += 1;
        }
        out.push(if cnt > 0 { sum / cnt as f64 } else { 0.0 });
    }
    out
}

#[derive(Serialize, Clone, Debug, Default)]
pub struct Summary {
    pub n: usize,
    pub expectancy: f64,
    pub win_rate: f64,
    pub pf: f64,
    pub total_r: f64,
    pub cagr: f64,
    pub max_dd: f64,
    pub sharpe: f64,
}

/// Daily return series on `days` (sorted): the sum of RISK * R of trades exiting that day.
pub fn daily_returns(tr: &[&TradeRec], days: &[i32]) -> Vec<f64> {
    let mut by_day: BTreeMap<i32, f64> = BTreeMap::new();
    for t in tr {
        *by_day.entry(t.exit_day).or_insert(0.0) += RISK * t.r;
    }
    days.iter().map(|d| by_day.get(d).copied().unwrap_or(0.0)).collect()
}

pub fn summarize(tr: &[&TradeRec], days: &[i32]) -> Summary {
    let n = tr.len();
    if n == 0 || days.is_empty() {
        return Summary::default();
    }
    let total: f64 = tr.iter().map(|t| t.r).sum();
    let wins: f64 = tr.iter().filter(|t| t.r > 0.0).map(|t| t.r).sum();
    let losses: f64 = -tr.iter().filter(|t| t.r < 0.0).map(|t| t.r).sum::<f64>();
    let rets = daily_returns(tr, days);
    let (mut eq, mut peak, mut mdd) = (1.0f64, 1.0f64, 0.0f64);
    for r in &rets {
        eq = (eq * (1.0 + r)).max(1e-9);
        peak = peak.max(eq);
        mdd = mdd.max(1.0 - eq / peak);
    }
    let years = (days[days.len() - 1] - days[0]) as f64 / 365.25;
    let cagr = if years > 0.0 { eq.powf(1.0 / years) - 1.0 } else { 0.0 };
    Summary {
        n,
        expectancy: total / n as f64,
        win_rate: tr.iter().filter(|t| t.r > 0.0).count() as f64 / n as f64,
        pf: if losses > 0.0 { (wins / losses).min(99.0) } else { 99.0 },
        total_r: total,
        cagr,
        max_dd: mdd,
        sharpe: stats::sharpe_daily(&rets) * 252f64.sqrt(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{synthetic_15m, Bar};
    use chrono::NaiveDateTime;

    fn series(bars: Vec<Bar>) -> Series {
        Series::new(false, Tf::D1, bars)
    }

    fn bar(day: u32, o: f64, h: f64, l: f64, c: f64) -> Bar {
        let ts = NaiveDateTime::parse_from_str(&format!("2020-01-{:02} 00:00:00", day), "%Y-%m-%d %H:%M:%S").unwrap();
        Bar { ts, o, h, l, c, v: 1.0 }
    }

    #[test]
    fn stop_first_when_both_barriers_hit_in_one_bar() {
        // signal bar 1; entry at bar 2 open = 100, atr = 1; bar 2 spans 98..102 (both hit)
        let s = series(vec![
            bar(1, 100.0, 100.5, 99.5, 100.0),
            bar(2, 100.0, 100.5, 99.5, 100.0),
            bar(3, 100.0, 102.0, 98.0, 100.0),
        ]);
        assert_eq!(barrier_win(&s, 1.0, 1, 1, 1.0, 1.0, 5), Some(false));
        // only the upper barrier is reached in bar 2
        let s2 = series(vec![
            bar(1, 100.0, 100.5, 99.5, 100.0),
            bar(2, 100.0, 100.5, 99.5, 100.0),
            bar(3, 100.0, 101.2, 99.5, 100.0),
        ]);
        assert_eq!(barrier_win(&s2, 1.0, 1, 1, 1.0, 1.0, 5), Some(true));
        // timeout counts as a loss
        let s3 = series(vec![bar(1, 100.0, 100.5, 99.5, 100.0), bar(2, 100.0, 100.4, 99.6, 100.0)]);
        assert_eq!(barrier_win(&s3, 1.0, 0, 1, 1.0, 1.0, 5), Some(false));
    }

    #[test]
    fn cost_math() {
        // entry 100, exit 102 long, risk 1, cost 13 bps of 100 = 0.13 price
        let r = net_r(1, 100.0, 102.0, 1.0, 13.0);
        assert!((r - (2.0 - 0.13)).abs() < 1e-12);
        // short losing 1 price unit with 0 cost
        assert!((net_r(-1, 100.0, 101.0, 0.5, 0.0) + 2.0).abs() < 1e-12);
    }

    #[test]
    fn intraday_window_stops_at_session_end() {
        let bars = synthetic_15m(3, 3, 0.002);
        let s = Series::new(false, Tf::M15, bars);
        let t = s.sess_end[0] - 1; // last signal bar with a next bar in session
        assert!(valid_signal(&s, t));
        assert!(!valid_signal(&s, s.sess_end[0]));
        assert_eq!(window_end(&s, t, 16), s.sess_end[0]);
    }

    #[test]
    fn random_walk_expectancy_is_negative_by_costs() {
        // a stop-and-target trade on a flat path loses the round-trip cost in R
        let r = net_r(1, 100.0, 100.0, 1.0, 46.0);
        assert!((r + 0.46).abs() < 1e-9);
    }
}
