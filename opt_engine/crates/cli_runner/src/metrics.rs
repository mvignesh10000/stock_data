//! Performance metrics, drawdown analytics and the drawdown-penalised fitness gate.

use oms_simulator::DayResult;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct GateConfig {
    /// Capital deployed per backtested lot (₹). ROI, DD% and Ulcer use this.
    pub capital: f64,
    pub min_expectancy_rupees: f64,
    pub worst_day_vs_p90_win: f64,
    pub worst_day_pct_capital: f64,
    pub max_losing_months_pct: f64,
    pub max_dd_duration_days: usize,
}

impl Default for GateConfig {
    fn default() -> Self {
        GateConfig {
            capital: 200_000.0,
            min_expectancy_rupees: 450.0,
            worst_day_vs_p90_win: 2.5,
            worst_day_pct_capital: 1.5,
            max_losing_months_pct: 15.0,
            max_dd_duration_days: 25,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct DdEpisode {
    pub start_date: u32,
    pub trough_date: u32,
    pub recovery_date: Option<u32>,
    pub dd_rupees: f64,
    pub duration_active_days: usize,
}

#[derive(Clone, Debug, Serialize, Default)]
pub struct Metrics {
    pub trading_days: usize,
    pub active_days: usize,
    pub traded_days: usize,
    pub gross_pnl_points: f64,
    pub total_slippage_points: f64,
    pub statutory_charges_rupees: f64,
    pub net_pnl_points: f64,
    pub net_pnl_rupees: f64,
    pub annual_net_rupees: f64,
    pub roi_annual_pct: f64,
    pub max_drawdown_rupees: f64,
    pub max_drawdown_pct: f64,
    pub max_dd_duration_active_days: usize,
    pub max_dd_duration_trading_days: usize,
    pub calmar_ratio: f64,
    pub sharpe_ratio: f64,
    pub sortino_ratio: f64,
    pub profit_factor: f64,
    pub win_rate_pct: f64,
    pub avg_win_rupees: f64,
    pub avg_loss_rupees: f64,
    pub expectancy_per_trade_rupees: f64,
    pub max_consecutive_losing_days: usize,
    pub worst_day_rupees: f64,
    pub best_day_rupees: f64,
    pub p90_win_rupees: f64,
    pub months: usize,
    pub profitable_months_pct: f64,
    pub losing_months_pct: f64,
    pub ulcer_index: f64,
    pub avg_stops_per_day: f64,
    pub peak_margin_max: f64,
    pub peak_margin_avg: f64,
    pub fitness: f64,
    pub soft_fitness: f64,
    pub gate_passed: bool,
    pub gate_failures: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Default)]
pub struct Breakdowns {
    pub monthly: BTreeMap<String, f64>,
    pub quarterly: BTreeMap<String, f64>,
    pub yearly: BTreeMap<String, f64>,
    pub dte: BTreeMap<String, serde_json::Value>,
    pub weekday: BTreeMap<String, f64>,
    pub worst_drawdown_episodes: Vec<DdEpisode>,
}

pub struct DayRow<'a> {
    pub active: bool,
    pub r: &'a DayResult,
}

fn std(v: &[f64]) -> f64 {
    if v.len() < 2 {
        return 0.0;
    }
    let m = v.iter().sum::<f64>() / v.len() as f64;
    (v.iter().map(|x| (x - m).powi(2)).sum::<f64>() / (v.len() - 1) as f64).sqrt()
}

pub fn compute(rows: &[DayRow], g: &GateConfig) -> (Metrics, Breakdowns) {
    let mut mt = Metrics { trading_days: rows.len(), ..Default::default() };
    let mut bd = Breakdowns::default();
    if rows.is_empty() {
        return (mt, bd);
    }
    let net: Vec<f64> = rows.iter().map(|d| d.r.net_rupees).collect();
    mt.active_days = rows.iter().filter(|d| d.active).count();
    let traded: Vec<&DayRow> = rows.iter().filter(|d| d.r.traded).collect();
    mt.traded_days = traded.len();
    mt.gross_pnl_points = rows.iter().map(|d| d.r.points + d.r.slippage_points).sum();
    mt.total_slippage_points = rows.iter().map(|d| d.r.slippage_points).sum();
    mt.statutory_charges_rupees = rows.iter().map(|d| d.r.charges_rupees).sum();
    mt.net_pnl_points = rows.iter().map(|d| d.r.points).sum();
    mt.net_pnl_rupees = net.iter().sum();
    let years = rows.len() as f64 / 252.0;
    mt.annual_net_rupees = mt.net_pnl_rupees / years;
    mt.roi_annual_pct = mt.annual_net_rupees / g.capital * 100.0;

    // drawdown on the cumulative curve
    let (mut cum, mut peak, mut peak_eq) = (0.0f64, 0.0f64, g.capital);
    let mut ulcer_acc = 0.0;
    let mut cur_ep: Option<DdEpisode> = None;
    let mut episodes: Vec<DdEpisode> = vec![];
    let mut uw_active = 0usize;
    let mut uw_all = 0usize;
    for d in rows.iter() {
        cum += d.r.net_rupees;
        let eq = g.capital + cum;
        if eq > peak_eq {
            peak_eq = eq;
        }
        let ddp = (peak_eq - eq) / peak_eq * 100.0;
        ulcer_acc += ddp * ddp;
        if cum >= peak - 1e-9 {
            if let Some(mut e) = cur_ep.take() {
                e.recovery_date = Some(d.r.trade_date);
                episodes.push(e);
            }
            peak = cum;
            uw_active = 0;
            uw_all = 0;
        } else {
            uw_all += 1;
            if d.active {
                uw_active += 1;
            }
            mt.max_dd_duration_active_days = mt.max_dd_duration_active_days.max(uw_active);
            mt.max_dd_duration_trading_days = mt.max_dd_duration_trading_days.max(uw_all);
            let dd = peak - cum;
            let e = cur_ep.get_or_insert(DdEpisode { start_date: d.r.trade_date, trough_date: d.r.trade_date, recovery_date: None, dd_rupees: 0.0, duration_active_days: 0 });
            if dd > e.dd_rupees {
                e.dd_rupees = dd;
                e.trough_date = d.r.trade_date;
            }
            e.duration_active_days = uw_active;
            if dd > mt.max_drawdown_rupees {
                mt.max_drawdown_rupees = dd;
                mt.max_drawdown_pct = (peak - cum) / (g.capital + peak) * 100.0;
            }
        }
    }
    if let Some(e) = cur_ep.take() {
        episodes.push(e);
    }
    episodes.sort_by(|a, b| b.dd_rupees.partial_cmp(&a.dd_rupees).unwrap());
    episodes.truncate(5);
    bd.worst_drawdown_episodes = episodes;
    mt.ulcer_index = (ulcer_acc / rows.len() as f64).sqrt();
    mt.calmar_ratio = if mt.max_drawdown_rupees > 0.0 { mt.annual_net_rupees / mt.max_drawdown_rupees } else if mt.net_pnl_rupees > 0.0 { 99.0 } else { 0.0 };
    let s = std(&net);
    let mean = mt.net_pnl_rupees / rows.len() as f64;
    mt.sharpe_ratio = if s > 0.0 { mean / s * 252f64.sqrt() } else { 0.0 };
    let downside: Vec<f64> = net.iter().map(|x| x.min(0.0)).collect();
    let ds = (downside.iter().map(|x| x * x).sum::<f64>() / net.len() as f64).sqrt();
    mt.sortino_ratio = if ds > 0.0 { mean / ds * 252f64.sqrt() } else { 0.0 };

    let tn: Vec<f64> = traded.iter().map(|d| d.r.net_rupees).collect();
    let wins: Vec<f64> = tn.iter().cloned().filter(|x| *x > 0.0).collect();
    let losses: Vec<f64> = tn.iter().cloned().filter(|x| *x <= 0.0).collect();
    let sw: f64 = wins.iter().sum();
    let sl: f64 = -losses.iter().sum::<f64>();
    mt.profit_factor = if sl > 0.0 { sw / sl } else if sw > 0.0 { 99.0 } else { 0.0 };
    if !tn.is_empty() {
        mt.win_rate_pct = wins.len() as f64 / tn.len() as f64 * 100.0;
        mt.expectancy_per_trade_rupees = tn.iter().sum::<f64>() / tn.len() as f64;
        mt.avg_stops_per_day = traded.iter().map(|d| d.r.n_stops as f64).sum::<f64>() / tn.len() as f64;
        mt.peak_margin_max = traded.iter().map(|d| d.r.peak_margin).fold(0.0, f64::max);
        mt.peak_margin_avg = traded.iter().map(|d| d.r.peak_margin).sum::<f64>() / tn.len() as f64;
    }
    mt.avg_win_rupees = if wins.is_empty() { 0.0 } else { sw / wins.len() as f64 };
    mt.avg_loss_rupees = if losses.is_empty() { 0.0 } else { -sl / losses.len() as f64 };
    let mut run = 0;
    for x in &tn {
        if *x <= 0.0 {
            run += 1;
            mt.max_consecutive_losing_days = mt.max_consecutive_losing_days.max(run);
        } else {
            run = 0;
        }
    }
    mt.worst_day_rupees = tn.iter().cloned().fold(0.0, f64::min);
    mt.best_day_rupees = tn.iter().cloned().fold(0.0, f64::max);
    let mut ws = wins.clone();
    ws.sort_by(|a, b| a.partial_cmp(b).unwrap());
    mt.p90_win_rupees = if ws.is_empty() { 0.0 } else { ws[((ws.len() as f64 * 0.9) as usize).min(ws.len() - 1)] };

    // calendar breakdowns
    let mut month_active: BTreeMap<String, bool> = BTreeMap::new();
    let mut dte_acc: BTreeMap<u8, Vec<f64>> = BTreeMap::new();
    for d in rows {
        let y = d.r.trade_date / 10000;
        let mo = (d.r.trade_date / 100) % 100;
        let mk = format!("{}-{:02}", y, mo);
        *bd.monthly.entry(mk.clone()).or_insert(0.0) += d.r.net_rupees;
        *month_active.entry(mk).or_insert(false) |= d.r.traded;
        *bd.quarterly.entry(format!("{}-Q{}", y, (mo - 1) / 3 + 1)).or_insert(0.0) += d.r.net_rupees;
        *bd.yearly.entry(format!("{}", y)).or_insert(0.0) += d.r.net_rupees;
        if d.r.traded {
            dte_acc.entry(d.r.dte).or_default().push(d.r.net_rupees);
            *bd.weekday.entry(["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d.r.weekday as usize].to_string()).or_insert(0.0) += d.r.net_rupees;
        }
    }
    let active_months: Vec<f64> = bd.monthly.iter().filter(|(k, _)| month_active[*k]).map(|(_, v)| *v).collect();
    mt.months = active_months.len();
    if mt.months > 0 {
        mt.profitable_months_pct = active_months.iter().filter(|x| **x > 0.0).count() as f64 / mt.months as f64 * 100.0;
        mt.losing_months_pct = 100.0 - mt.profitable_months_pct;
    }
    for (k, v) in dte_acc {
        let mut c = 0.0f64;
        let mut p = 0.0f64;
        let mut dd = 0.0f64;
        for x in &v {
            c += x;
            p = p.max(c);
            dd = dd.max(p - c);
        }
        let w = v.iter().filter(|x| **x > 0.0).count() as f64 / v.len() as f64 * 100.0;
        bd.dte.insert(k.to_string(), serde_json::json!({"days": v.len(), "net_rupees": c, "max_dd": dd, "win_rate": w}));
    }

    // fitness
    let ratio = if mt.max_drawdown_rupees > 0.0 { mt.annual_net_rupees / mt.max_drawdown_rupees } else { mt.annual_net_rupees.max(0.0) / 1.0 };
    let wm = mt.profitable_months_pct / 100.0;
    let ui = mt.ulcer_index.max(0.05);
    mt.soft_fitness = if mt.net_pnl_rupees > 0.0 { ratio * mt.profit_factor.min(10.0) * wm * wm / ui } else { mt.net_pnl_rupees / g.capital };
    let mut fails = vec![];
    if mt.traded_days < 10 {
        fails.push(format!("too few trades ({})", mt.traded_days));
    }
    if mt.expectancy_per_trade_rupees < g.min_expectancy_rupees {
        fails.push(format!("thin edge: expectancy ₹{:.0} < ₹{:.0}", mt.expectancy_per_trade_rupees, g.min_expectancy_rupees));
    }
    let worst = -mt.worst_day_rupees;
    if mt.p90_win_rupees > 0.0 && worst > g.worst_day_vs_p90_win * mt.p90_win_rupees {
        fails.push(format!("tail: worst day ₹{:.0} > {:.1}x p90 win ₹{:.0}", worst, g.worst_day_vs_p90_win, mt.p90_win_rupees));
    }
    if worst > g.worst_day_pct_capital / 100.0 * g.capital {
        fails.push(format!("tail: worst day ₹{:.0} > {:.1}% of capital", worst, g.worst_day_pct_capital));
    }
    if mt.losing_months_pct > g.max_losing_months_pct {
        fails.push(format!("losing months {:.1}% > {:.0}%", mt.losing_months_pct, g.max_losing_months_pct));
    }
    if mt.max_dd_duration_active_days > g.max_dd_duration_days {
        fails.push(format!("underwater {} active days > {}", mt.max_dd_duration_active_days, g.max_dd_duration_days));
    }
    mt.gate_passed = fails.is_empty();
    mt.gate_failures = fails;
    mt.fitness = if mt.gate_passed { mt.soft_fitness } else { 0.0 };
    (mt, bd)
}
