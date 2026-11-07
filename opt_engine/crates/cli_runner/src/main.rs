//! `opt_engine` — headless CLI for the agent loop.
//!
//!   opt_engine build-cache --parquet-dir DIR [--parquet-dir DIR2 ...] --out FILE [--rank 0] [--step 50]
//!   opt_engine info        --cache FILE
//!   opt_engine backtest    --cache FILE --strategy-config CFG.json [--date-from N] [--date-to N] --out OUT.json
//!   opt_engine batch-sweep --cache FILE --batch-file GRID.jsonl [--date-from N] [--date-to N] --out OUT.json [--with-daily]
//!
//! A strategy config is either a bare `NdConfig` object, or
//! `{"strategy": {...}, "exec": {...}, "gates": {...}}`, or a portfolio
//! `{"portfolio": [cfg, cfg, ...], "exec": {...}, "gates": {...}}` whose daily P&L is summed.

mod metrics;

use core_types::{ChainCache, TradingDayData, MINUTES};
use metrics::{compute, DayRow, GateConfig};
use oms_simulator::{DayResult, ExecConfig, TradeRecord, VirtualOms};
use rayon::prelude::*;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::time::Instant;
use strategy_api::nd_seller::NdSeller;
use strategy_api::{IntradayStrategy, MarketView};

struct Args {
    cmd: String,
    kv: HashMap<String, Vec<String>>,
    flags: Vec<String>,
}

fn parse_args() -> Args {
    let mut it = std::env::args().skip(1);
    let cmd = it.next().unwrap_or_default();
    let mut kv: HashMap<String, Vec<String>> = HashMap::new();
    let mut flags = vec![];
    let rest: Vec<String> = it.collect();
    let mut i = 0;
    while i < rest.len() {
        let k = rest[i].trim_start_matches("--").to_string();
        if i + 1 < rest.len() && !rest[i + 1].starts_with("--") {
            kv.entry(k).or_default().push(rest[i + 1].clone());
            i += 2;
        } else {
            flags.push(k);
            i += 1;
        }
    }
    Args { cmd, kv, flags }
}

impl Args {
    fn get(&self, k: &str) -> Option<&str> {
        self.kv.get(k).and_then(|v| v.first()).map(|s| s.as_str())
    }
    fn req(&self, k: &str) -> &str {
        self.get(k).unwrap_or_else(|| {
            eprintln!("missing --{}", k);
            std::process::exit(2)
        })
    }
    fn num(&self, k: &str, d: u32) -> u32 {
        self.get(k).map(|s| s.parse().expect("number")).unwrap_or(d)
    }
}

pub struct DayOut {
    active: bool,
    result: DayResult,
    trades: Vec<TradeRecord>,
}

/// Engine loop for one strategy across a slice of days.
fn run_single(days: &[TradingDayData], strat_cfg: &Value, exec: &ExecConfig, keep_trades: bool) -> Result<Vec<DayOut>, String> {
    let mut strat = NdSeller::from_value(strat_cfg.clone())?;
    let mut out = Vec::with_capacity(days.len());
    for day in days {
        let meta = day.meta();
        let mut oms = VirtualOms::new(day, exec);
        let active = strat.on_day_start(&meta);
        if active {
            for m in 0..MINUTES {
                oms.process_triggers(m);
                if m >= exec.eod_minute {
                    oms.square_off_all("EOD");
                    break;
                }
                let view = MarketView::new(day, m);
                strat.on_minute(m, &view, &mut oms);
            }
            strat.on_day_end(&mut oms);
        }
        out.push(DayOut { active, result: oms.result(), trades: if keep_trades { oms.trade_records() } else { vec![] } });
    }
    Ok(out)
}

fn split_config(v: &Value) -> (Vec<Value>, ExecConfig, GateConfig) {
    let exec: ExecConfig = v.get("exec").map(|e| serde_json::from_value(e.clone()).expect("exec config")).unwrap_or_default();
    let gates: GateConfig = v.get("gates").map(|e| serde_json::from_value(e.clone()).expect("gates config")).unwrap_or_default();
    let strats = if let Some(Value::Array(p)) = v.get("portfolio") {
        p.iter().map(|x| x.get("strategy").cloned().unwrap_or_else(|| x.clone())).collect()
    } else if let Some(s) = v.get("strategy") {
        vec![s.clone()]
    } else {
        vec![v.clone()]
    };
    (strats, exec, gates)
}

fn run_config(days: &[TradingDayData], v: &Value, keep_trades: bool) -> Result<(Vec<DayOut>, GateConfig), String> {
    let (strats, exec, gates) = split_config(v);
    let mut acc: Option<Vec<DayOut>> = None;
    for (si, s) in strats.iter().enumerate() {
        let mut r = run_single(days, s, &exec, keep_trades)?;
        if strats.len() > 1 {
            let name = s.get("name").and_then(|x| x.as_str()).unwrap_or("s").to_string();
            for d in r.iter_mut() {
                for t in d.trades.iter_mut() {
                    t.tag = format!("{}:{}", name, t.tag);
                }
            }
            let _ = si;
        }
        acc = Some(match acc {
            None => r,
            Some(mut a) => {
                for (x, y) in a.iter_mut().zip(r.into_iter()) {
                    x.active |= y.active;
                    let (p, q) = (&mut x.result, &y.result);
                    p.traded |= q.traded;
                    p.points += q.points;
                    p.slippage_points += q.slippage_points;
                    p.charges_rupees += q.charges_rupees;
                    p.net_rupees += q.net_rupees;
                    p.n_orders += q.n_orders;
                    p.n_stops += q.n_stops;
                    p.max_lots += q.max_lots;
                    if q.traded {
                        p.exit_reason = format!("{}{}{}", p.exit_reason, if p.exit_reason.is_empty() { "" } else { "+" }, q.exit_reason);
                        p.last_exit_minute = p.last_exit_minute.max(q.last_exit_minute);
                    }
                    x.trades.extend(y.trades);
                }
                a
            }
        });
    }
    Ok((acc.unwrap_or_default(), gates))
}

fn slice_days<'a>(cache: &'a ChainCache, from: u32, to: u32) -> &'a [TradingDayData] {
    let a = cache.days.partition_point(|d| d.trade_date < from);
    let b = cache.days.partition_point(|d| d.trade_date <= to);
    &cache.days[a..b]
}

fn day_rows(outs: &[DayOut]) -> Vec<DayRow<'_>> {
    outs.iter().map(|d| DayRow { active: d.active, r: &d.result }).collect()
}

fn main() {
    let a = parse_args();
    match a.cmd.as_str() {
        "build-cache" => {
            let t = Instant::now();
            let dirs: Vec<PathBuf> = a.kv.get("parquet-dir").cloned().unwrap_or_default().into_iter().map(PathBuf::from).collect();
            let cache = data_loader::build_cache(&dirs, a.num("rank", 0) as u8, a.num("step", 50), a.get("instrument").unwrap_or("NIFTY"));
            data_loader::write_cache(&cache, &PathBuf::from(a.req("out")));
            println!(
                "{}",
                json!({"status": "SUCCESS", "days": cache.days.len(),
                       "from": cache.days.first().map(|d| d.trade_date), "to": cache.days.last().map(|d| d.trade_date),
                       "elapsed_ms": t.elapsed().as_millis() as u64})
            );
        }
        "info" => {
            let cache = data_loader::load_cache(&PathBuf::from(a.req("cache")));
            let dates: Vec<Value> = cache.days.iter().map(|d| json!([d.trade_date, d.dte, d.weekday, d.expiry_date, d.n_strikes])).collect();
            println!("{}", json!({"instrument": cache.instrument, "days": cache.days.len(), "dates": dates}));
        }
        "backtest" => {
            let t0 = Instant::now();
            let cache = data_loader::load_cache(&PathBuf::from(a.req("cache")));
            let load_ms = t0.elapsed().as_secs_f64() * 1000.0;
            let cfg: Value = serde_json::from_str(&std::fs::read_to_string(a.req("strategy-config")).expect("read config")).expect("parse config");
            let days = slice_days(&cache, a.num("date-from", 0), a.num("date-to", 99_999_999));
            let t1 = Instant::now();
            let (outs, gates) = match run_config(days, &cfg, true) {
                Ok(x) => x,
                Err(e) => {
                    println!("{}", json!({"status": "ERROR", "error": e}));
                    std::process::exit(1)
                }
            };
            let exec_ms = t1.elapsed().as_secs_f64() * 1000.0;
            let rows = day_rows(&outs);
            let (m, bd) = compute(&rows, &gates);
            let daily: Vec<Value> = outs
                .iter()
                .map(|d| {
                    let r = &d.result;
                    json!({"date": r.trade_date, "dte": r.dte, "wd": r.weekday, "active": d.active, "traded": r.traded,
                           "net": (r.net_rupees * 100.0).round() / 100.0, "points": (r.points * 100.0).round() / 100.0,
                           "charges": (r.charges_rupees * 100.0).round() / 100.0, "stops": r.n_stops, "orders": r.n_orders,
                           "exit": r.exit_reason, "exit_time": core_types::minute_to_hhmm(r.last_exit_minute)})
                })
                .collect();
            let trades: Vec<&TradeRecord> = outs.iter().flat_map(|d| d.trades.iter()).collect();
            let rep = json!({
                "status": "SUCCESS", "load_ms": load_ms, "execution_time_ms": exec_ms,
                "period": {"from": days.first().map(|d| d.trade_date), "to": days.last().map(|d| d.trade_date), "trading_days": days.len()},
                "config": cfg, "summary_metrics": m, "dte_breakdown": bd.dte, "monthly_pnl": bd.monthly,
                "quarterly_pnl": bd.quarterly, "yearly_pnl": bd.yearly, "weekday_pnl": bd.weekday,
                "worst_drawdown_episodes": bd.worst_drawdown_episodes, "daily": daily,
                "trades": if a.flags.iter().any(|f| f == "no-trades") { vec![] } else { trades },
            });
            let s = serde_json::to_string(&rep).unwrap();
            if let Some(o) = a.get("out") {
                std::fs::write(o, &s).expect("write out");
                println!("{}", json!({"status": "SUCCESS", "out": o, "net_pnl_rupees": m.net_pnl_rupees, "max_dd": m.max_drawdown_rupees, "calmar": m.calmar_ratio, "execution_time_ms": exec_ms}));
            } else {
                println!("{}", s);
            }
        }
        "batch-sweep" => {
            let t0 = Instant::now();
            let cache = data_loader::load_cache(&PathBuf::from(a.req("cache")));
            let from = a.num("date-from", 0);
            let to = a.num("date-to", 99_999_999);
            let with_daily = a.flags.iter().any(|f| f == "with-daily");
            let f = std::fs::File::open(a.req("batch-file")).expect("batch file");
            let lines: Vec<Value> = BufReader::new(f).lines().map_while(Result::ok).filter(|l| !l.trim().is_empty()).map(|l| serde_json::from_str(&l).expect("jsonl line")).collect();
            let t1 = Instant::now();
            let res: Vec<Value> = lines
                .par_iter()
                .map(|line| {
                    let id = line.get("id").cloned().unwrap_or(Value::Null);
                    let cfg = line.get("config").cloned().unwrap_or_else(|| line.clone());
                    let lf = line.get("date_from").and_then(|x| x.as_u64()).map(|x| x as u32).unwrap_or(from);
                    let lt = line.get("date_to").and_then(|x| x.as_u64()).map(|x| x as u32).unwrap_or(to);
                    let days = slice_days(&cache, lf, lt);
                    match run_config(days, &cfg, false) {
                        Ok((outs, gates)) => {
                            let rows = day_rows(&outs);
                            let (m, bd) = compute(&rows, &gates);
                            let mut v = json!({"id": id, "status": "SUCCESS", "summary_metrics": m, "monthly_pnl": bd.monthly, "dte_breakdown": bd.dte});
                            if with_daily {
                                v["daily"] = json!(outs.iter().map(|d| [d.result.trade_date as f64, (d.result.net_rupees * 100.0).round() / 100.0, d.result.dte as f64, d.result.n_stops as f64, d.result.last_exit_minute as f64]).collect::<Vec<_>>());
                                v["daily_exit"] = json!(outs.iter().map(|d| d.result.exit_reason.clone()).collect::<Vec<_>>());
                            }
                            v
                        }
                        Err(e) => json!({"id": id, "status": "ERROR", "error": e}),
                    }
                })
                .collect();
            let rep = json!({"status": "SUCCESS", "runs": res.len(), "load_ms": t1.duration_since(t0).as_millis() as u64,
                             "execution_time_ms": t1.elapsed().as_secs_f64() * 1000.0, "results": res});
            std::fs::write(a.req("out"), serde_json::to_string(&rep).unwrap()).expect("write");
            println!("{}", json!({"status": "SUCCESS", "runs": rep["runs"], "execution_time_ms": rep["execution_time_ms"]}));
        }
        _ => {
            eprintln!("usage: opt_engine <build-cache|info|backtest|batch-sweep> ...");
            std::process::exit(2);
        }
    }
}
