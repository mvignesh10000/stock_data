//! Experiment runner: loading, E0 integrity, E1 event study with controls, E2 tradable
//! backtest with random-entry control, E3 walk-forward with go/no-go checks.
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;
use std::process::Command;

use chrono::{Datelike, NaiveDateTime};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rayon::prelude::*;
use serde::Serialize;

use crate::data::{clean, read_csv, to_15m, to_daily, Bar, CleanStats, Res, Series, Tf, year_of};
use crate::detect::{analyze, Analysis};
use crate::events::{generate, sweep_count, Event, Kind, Zp, KINDS, NK};
use crate::indicators::{atr, sma};
use crate::stats::{self, wilson};
use crate::trade::{barrier_win, daily_returns, e2_trades, entry_pools, random_expectancies, summarize, Summary, TradeRec};
use crate::Config;

#[derive(Clone, Copy, Default, Debug, Serialize)]
pub struct Cnt {
    pub n: u64,
    pub w: u64,
}

impl Cnt {
    fn add(&mut self, win: bool) {
        self.n += 1;
        self.w += win as u64;
    }
    fn plus(&mut self, o: Cnt) {
        self.n += o.n;
        self.w += o.w;
    }
}

/// [kind][dir: 0 = long, 1 = short][barrier config]
pub type Tab = [[[Cnt; 2]; 2]; NK];
/// [dir][barrier config]
pub type Base = [[Cnt; 2]; 2];

fn di(dir: i8) -> usize {
    if dir > 0 {
        0
    } else {
        1
    }
}

fn add_tab(a: &mut Tab, b: &Tab) {
    for k in 0..NK {
        for d in 0..2 {
            for c in 0..2 {
                a[k][d][c].plus(b[k][d][c]);
            }
        }
    }
}

fn add_base(a: &mut Base, b: &Base) {
    for d in 0..2 {
        for c in 0..2 {
            a[d][c].plus(b[d][c]);
        }
    }
}

pub struct Prepared {
    pub s: Series,
    pub atr: Vec<f64>,
    pub pools: BTreeMap<i32, Vec<usize>>,
}

impl Prepared {
    fn new(s: Series) -> Prepared {
        let atr = atr(&s.bars, 14);
        let pools = entry_pools(&s);
        Prepared { s, atr, pools }
    }
}

#[derive(Serialize, Clone, Debug)]
pub struct XCheck {
    pub vendor_bars: usize,
    pub matched_15m: usize,
    pub share_15m_close_within_5bp: f64,
    pub max_abs_close_diff_pts: f64,
    pub daily_matched: usize,
    pub share_daily_close_within_5bp: f64,
}

pub struct Loaded {
    pub m15: Vec<Prepared>,
    pub d1: Vec<Prepared>,
    pub e0: Vec<CleanStats>,
    pub xcheck: XCheck,
    /// day -> NIFTY close above its 200-day SMA
    pub regime: BTreeMap<i32, bool>,
    /// per symbol: liquidity tercile 0 (low) .. 2 (high), 3 = index
    pub liq: Vec<u8>,
}

fn xcheck(idx15: &[Bar], idxd: &[Bar], ven15: &[Bar]) -> XCheck {
    let by_ts: BTreeMap<NaiveDateTime, &Bar> = idx15.iter().map(|b| (b.ts, b)).collect();
    let (mut matched, mut within, mut maxd) = (0usize, 0usize, 0.0f64);
    for v in ven15 {
        if let Some(b) = by_ts.get(&v.ts) {
            matched += 1;
            let d = (b.c - v.c).abs();
            maxd = maxd.max(d);
            if d / v.c <= 0.0005 {
                within += 1;
            }
        }
    }
    let vend = to_daily(ven15);
    let by_day: BTreeMap<i32, &Bar> = idxd.iter().map(|b| (b.ts.date().num_days_from_ce(), b)).collect();
    let (mut dm, mut dw) = (0usize, 0usize);
    for v in &vend {
        if let Some(b) = by_day.get(&v.ts.date().num_days_from_ce()) {
            dm += 1;
            if (b.c - v.c).abs() / v.c <= 0.0005 {
                dw += 1;
            }
        }
    }
    let ratio = |a: usize, b: usize| if b > 0 { a as f64 / b as f64 } else { f64::NAN };
    XCheck {
        vendor_bars: ven15.len(),
        matched_15m: matched,
        share_15m_close_within_5bp: ratio(within, matched),
        max_abs_close_diff_pts: maxd,
        daily_matched: dm,
        share_daily_close_within_5bp: ratio(dw, dm),
    }
}

/// Assembles the per-symbol inputs. Index is symbol 0, stocks follow in file-name order.
fn assemble(idx1: Vec<Bar>, stocks: Vec<(String, Vec<Bar>)>, xcheck: XCheck, e0: Vec<CleanStats>) -> Loaded {
    let idx15 = to_15m(&idx1);
    let idxd = to_daily(&idx1);
    let mut m15 = vec![Prepared::new(Series::new(true, Tf::M15, idx15))];
    let mut d1 = vec![Prepared::new(Series::new(true, Tf::D1, idxd))];
    for (_, bars) in stocks {
        d1.push(Prepared::new(Series::new(false, Tf::D1, to_daily(&bars))));
        m15.push(Prepared::new(Series::new(false, Tf::M15, bars)));
    }
    let closes: Vec<f64> = d1[0].s.bars.iter().map(|b| b.c).collect();
    let s200 = sma(&closes, 200);
    let regime = d1[0]
        .s
        .day
        .iter()
        .zip(closes.iter().zip(s200.iter()))
        .filter(|(_, (_, s))| s.is_finite())
        .map(|(d, (c, s))| (*d, c > s))
        .collect();
    let mut turnover: Vec<(f64, usize)> = (1..d1.len())
        .map(|i| {
            let b = &d1[i].s.bars;
            (b.iter().map(|x| x.c * x.v).sum::<f64>() / b.len().max(1) as f64, i)
        })
        .collect();
    turnover.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap().then(a.1.cmp(&b.1)));
    let mut liq = vec![3u8; d1.len()];
    let m = turnover.len().max(1);
    for (rank, (_, i)) in turnover.iter().enumerate() {
        liq[*i] = (rank * 3 / m) as u8;
    }
    Loaded { m15, d1, e0, xcheck, regime, liq }
}

pub fn load(cfg: &Config) -> Res<Loaded> {
    let dir = Path::new(&cfg.data_dir);
    let (idx1, st_idx) = clean("NIFTY 50 (1-min)", read_csv(&dir.join("index/NIFTY50_minute.csv"))?, 1);
    let (ven, st_ven) = clean("NIFTY 50 (15-min vendor, check only)", read_csv(&dir.join("stocks15/NIFTY 50_15minutedata.csv"))?, 15);
    let xc = xcheck(&to_15m(&idx1), &to_daily(&idx1), &ven);
    let mut files: Vec<_> = fs::read_dir(dir.join("stocks15"))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.file_name().and_then(|s| s.to_str()).is_some_and(|s| s.ends_with("_15minute.csv")))
        .collect();
    files.sort();
    let mut e0 = vec![st_idx, st_ven];
    let mut stocks = Vec::new();
    for f in files {
        let name = f.file_name().unwrap().to_string_lossy().trim_end_matches("_15minute.csv").to_string();
        let (bars, st) = clean(&name, read_csv(&f)?, 15);
        e0.push(st);
        stocks.push((name, bars));
    }
    Ok(assemble(idx1, stocks, xc, e0))
}

/// Random-walk universe for the sanity check (index + 40 stocks, 10 years of 15-minute bars).
pub fn synthetic(seed: u64) -> Loaded {
    use crate::data::synthetic_15m;
    let idx1 = synthetic_15m(seed, 2600, 0.0006);
    let stocks: Vec<(String, Vec<Bar>)> =
        (0..40).map(|i| (format!("RW{i:02}"), synthetic_15m(seed + 1 + i as u64, 2600, 0.0015))).collect();
    let xc = XCheck {
        vendor_bars: 0,
        matched_15m: 0,
        share_15m_close_within_5bp: f64::NAN,
        max_abs_close_diff_pts: f64::NAN,
        daily_matched: 0,
        share_daily_close_within_5bp: f64::NAN,
    };
    assemble(idx1, stocks, xc, Vec::new())
}

#[derive(Serialize, Clone)]
pub struct Combo {
    pub k: usize,
    pub d: f64,
    pub n: usize,
    pub variant: String,
    pub tau: f64,
    pub label: String,
    #[serde(skip)]
    pub vi: usize,
}

pub struct Ctx {
    pub combos: Vec<Combo>,
    pub kd: Vec<(usize, f64)>,
    pub ref_combo: usize,
    pub targets: Vec<String>,
    pub h: usize,
    pub cost_idx: f64,
    pub cost_stk: f64,
    pub barriers: Vec<[f64; 2]>,
    pub draws: usize,
    pub seed: u64,
    pub c: f64,
}

fn build_ctx(cfg: &Config, tf: Tf) -> Ctx {
    let g = &cfg.grid;
    let mut combos = Vec::new();
    for &k in &g.k {
        for &d in &g.d {
            for &n in &g.n {
                for (vi, v) in g.variant.iter().enumerate() {
                    for &tau in &g.tau {
                        combos.push(Combo {
                            k,
                            d,
                            n,
                            variant: v.clone(),
                            tau,
                            label: format!("k{k} d{d} n{n} {v} tau{tau}"),
                            vi,
                        });
                    }
                }
            }
        }
    }
    let kd: Vec<(usize, f64)> = g.k.iter().flat_map(|&k| g.d.iter().map(move |&d| (k, d))).collect();
    let r = &cfg.reference;
    let ref_combo = combos
        .iter()
        .position(|c| c.k == r.k && c.d == r.d && c.n == r.n && c.variant == r.variant && c.tau == r.tau)
        .expect("reference combo must be in the grid");
    let cs = &cfg.costs;
    Ctx {
        combos,
        kd,
        ref_combo,
        targets: g.target.clone(),
        h: match tf {
            Tf::M15 => cfg.horizon_m15,
            Tf::D1 => cfg.horizon_d1,
        },
        cost_idx: cs.index_rt_bps + cs.index_slip_bps,
        cost_stk: match tf {
            Tf::M15 => cs.stock_m15_rt_bps,
            Tf::D1 => cs.stock_d1_rt_bps,
        } + cs.stock_slip_bps,
        barriers: cfg.barriers.clone(),
        draws: cfg.random_draws,
        seed: cfg.seed,
        c: cfg.c,
    }
}

struct SOut {
    index: bool,
    e1: Vec<Tab>,
    base: Base,
    base_year: BTreeMap<i32, Base>,
    ref_year: BTreeMap<i32, Tab>,
    draws: Vec<Tab>,
    trades: Vec<Vec<TradeRec>>,
    base_trades: Vec<Vec<TradeRec>>,
    sweeps: Vec<usize>,
}

fn series_job(p: &Prepared, idx: usize, ctx: &Ctx) -> SOut {
    let s = &p.s;
    let n = s.bars.len();
    let h = ctx.h;
    let nt = ctx.targets.len();
    let cost = if s.is_index { ctx.cost_idx } else { ctx.cost_stk };
    let mut out = SOut {
        index: s.is_index,
        e1: vec![Tab::default(); ctx.combos.len()],
        base: Base::default(),
        base_year: BTreeMap::new(),
        ref_year: BTreeMap::new(),
        draws: Vec::new(),
        trades: vec![Vec::new(); ctx.combos.len() * nt],
        base_trades: vec![Vec::new(); 3 * nt],
        sweeps: vec![0; ctx.kd.len()],
    };

    // E1 control (b): unconditional barrier outcome on every bar, both directions
    for t in 0..n {
        let y = s.bars[t].ts.year();
        for (d, dir) in [1i8, -1].into_iter().enumerate() {
            for (c, &[up, dn]) in ctx.barriers.iter().enumerate() {
                if let Some(w) = barrier_win(s, p.atr[t], t, dir, up, dn, h) {
                    out.base[d][c].add(w);
                    out.base_year.entry(y).or_default()[d][c].add(w);
                }
            }
        }
    }

    for (kdi, &(k, d)) in ctx.kd.iter().enumerate() {
        let an: Analysis = analyze(s, k, d);
        out.sweeps[kdi] = sweep_count(s, &an, 100);
        for (ci, combo) in ctx.combos.iter().enumerate() {
            if combo.k != k || combo.d != d {
                continue;
            }
            let evs = generate(s, &an, Zp { variant: combo.vi, n: combo.n, c: ctx.c, tau: combo.tau });
            let is_ref = ci == ctx.ref_combo;
            let mut ref_ev: Vec<(Event, [Option<bool>; 2], f64)> = Vec::new();
            for ev in &evs {
                let (ki, dd) = (ev.kind as usize, di(ev.dir));
                let mut res = [None; 2];
                for (c, &[up, dn]) in ctx.barriers.iter().enumerate().take(2) {
                    res[c] = barrier_win(s, p.atr[ev.bar], ev.bar, ev.dir, up, dn, h);
                }
                for c in 0..2 {
                    if let Some(w) = res[c] {
                        out.e1[ci][ki][dd][c].add(w);
                    }
                }
                if is_ref {
                    let y = s.bars[ev.bar].ts.year();
                    for c in 0..2 {
                        if let Some(w) = res[c] {
                            out.ref_year.entry(y).or_default()[ki][dd][c].add(w);
                        }
                    }
                    ref_ev.push((*ev, res, p.atr[ev.bar]));
                }
            }
            if is_ref {
                // random-level control (a): shift each real zone by U(-3, 3) ATR, keep the bar
                let mut rng = ChaCha8Rng::seed_from_u64(ctx.seed ^ (idx as u64 + 1).wrapping_mul(0x9E37_79B9_7F4A_7C15));
                out.draws = vec![Tab::default(); ctx.draws];
                for r in 0..ctx.draws {
                    for (ev, res, a) in &ref_ev {
                        let u: f64 = rng.gen_range(-3.0..3.0);
                        let sh = u * *a;
                        let b = &s.bars[ev.bar];
                        if b.h >= ev.zlo + sh && b.l <= ev.zhi + sh {
                            let (ki, dd) = (ev.kind as usize, di(ev.dir));
                            for c in 0..2 {
                                if let Some(w) = res[c] {
                                    out.draws[r][ki][dd][c].add(w);
                                }
                            }
                        }
                    }
                }
            }
            let hpz: Vec<Event> = evs.iter().filter(|e| e.kind == Kind::Hpz).copied().collect();
            for (ti, tg) in ctx.targets.iter().enumerate() {
                let ext = tg == "ext";
                out.trades[ci * nt + ti] = e2_trades(s, idx as u32, &an, &hpz, ext, cost, h);
                if is_ref {
                    for (bk, kind) in [Kind::Smc, Kind::Fib, Kind::Ma].into_iter().enumerate() {
                        let ek: Vec<Event> = evs.iter().filter(|e| e.kind == kind).copied().collect();
                        out.base_trades[bk * nt + ti] = e2_trades(s, idx as u32, &an, &ek, ext, cost, h);
                    }
                }
            }
        }
    }
    out
}

pub struct ArmOut {
    pub combos: Vec<Combo>,
    pub targets: Vec<String>,
    pub ref_combo: usize,
    pub h: usize,
    pub cost_idx: f64,
    pub cost_stk: f64,
    /// [universe: 0 index, 1 stocks][combo]
    pub e1: [Vec<Tab>; 2],
    pub base: [Base; 2],
    pub base_year: BTreeMap<i32, Base>,
    pub ref_year: BTreeMap<i32, Tab>,
    /// [universe][draw]
    pub draws: [Vec<Tab>; 2],
    pub cell_trades: Vec<Vec<TradeRec>>,
    /// [strategy: 0 SMC, 1 Fib, 2 MA][target]
    pub base_trades: Vec<Vec<TradeRec>>,
    pub sweeps: Vec<usize>,
}

fn run_arm(cfg: &Config, prep: &[Prepared], tf: Tf) -> ArmOut {
    let ctx = build_ctx(cfg, tf);
    let outs: Vec<SOut> = prep.par_iter().enumerate().map(|(i, p)| series_job(p, i, &ctx)).collect();
    let nc = ctx.combos.len();
    let nt = ctx.targets.len();
    let r = ctx.draws;
    let mut arm = ArmOut {
        combos: ctx.combos.clone(),
        targets: ctx.targets.clone(),
        ref_combo: ctx.ref_combo,
        h: ctx.h,
        cost_idx: ctx.cost_idx,
        cost_stk: ctx.cost_stk,
        e1: [vec![Tab::default(); nc], vec![Tab::default(); nc]],
        base: [Base::default(); 2],
        base_year: BTreeMap::new(),
        ref_year: BTreeMap::new(),
        draws: [vec![Tab::default(); r], vec![Tab::default(); r]],
        cell_trades: vec![Vec::new(); nc * nt],
        base_trades: vec![Vec::new(); 3 * nt],
        sweeps: vec![0; ctx.kd.len()],
    };
    for o in outs {
        let u = if o.index { 0 } else { 1 };
        for c in 0..nc {
            add_tab(&mut arm.e1[u][c], &o.e1[c]);
        }
        add_base(&mut arm.base[u], &o.base);
        for (y, b) in o.base_year {
            add_base(arm.base_year.entry(y).or_default(), &b);
        }
        for (y, t) in o.ref_year {
            add_tab(arm.ref_year.entry(y).or_default(), &t);
        }
        for (rr, t) in o.draws.iter().enumerate() {
            add_tab(&mut arm.draws[u][rr], t);
        }
        for (c, tr) in o.trades.into_iter().enumerate() {
            arm.cell_trades[c].extend(tr);
        }
        for (c, tr) in o.base_trades.into_iter().enumerate() {
            arm.base_trades[c].extend(tr);
        }
        for (c, v) in o.sweeps.into_iter().enumerate() {
            arm.sweeps[c] += v;
        }
    }
    arm
}

// ---------- E1 ----------

#[derive(Serialize, Clone)]
pub struct E1Row {
    pub arm: String,
    pub kind: String,
    pub barrier: String,
    pub universe: String,
    pub dir: String,
    pub n: u64,
    pub hits: u64,
    pub rate: f64,
    pub ci_lo: f64,
    pub ci_hi: f64,
    pub ctrl_a: f64,
    pub ctrl_a_lo: f64,
    pub ctrl_a_hi: f64,
    pub base_b: f64,
    pub lift_a: f64,
    pub lift_b: f64,
}

#[derive(Serialize, Clone)]
pub struct GridRow {
    pub combo: String,
    pub hpz_n: u64,
    pub hpz_rate: f64,
    pub smc_rate: f64,
    pub fib_rate: f64,
}

#[derive(Serialize, Clone)]
pub struct E1Crit {
    pub hpz_rate: f64,
    pub hpz_ci_lo: f64,
    pub ctrl_a: f64,
    pub fib_rate: f64,
    pub smc_rate: f64,
    pub beats_random_level: bool,
    pub beats_fib_and_smc: bool,
    pub pass: bool,
}

#[derive(Serialize, Clone)]
pub struct YearRow {
    pub year: i32,
    pub kind: String,
    pub n: u64,
    pub rate: f64,
    pub base: f64,
}

fn tally(arm: &ArmOut, combo: usize, kind: usize, cfg: usize, univs: &[usize], dirs: &[usize]) -> Cnt {
    let mut c = Cnt::default();
    for &u in univs {
        for &d in dirs {
            c.plus(arm.e1[u][combo][kind][d][cfg]);
        }
    }
    c
}

fn pct(sorted: &[f64], q: f64) -> f64 {
    if sorted.is_empty() {
        return f64::NAN;
    }
    sorted[((q * sorted.len() as f64) as usize).min(sorted.len() - 1)]
}

fn ctrl_a(arm: &ArmOut, kind: usize, cfg: usize, univs: &[usize], dirs: &[usize]) -> (f64, f64, f64) {
    let (mut sn, mut sw) = (0u64, 0u64);
    let mut rates = Vec::new();
    for r in 0..arm.draws[0].len() {
        let mut t = Cnt::default();
        for &u in univs {
            for &d in dirs {
                t.plus(arm.draws[u][r][kind][d][cfg]);
            }
        }
        sn += t.n;
        sw += t.w;
        if t.n > 0 {
            rates.push(t.w as f64 / t.n as f64);
        }
    }
    rates.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let mean = if sn > 0 { sw as f64 / sn as f64 } else { f64::NAN };
    (mean, pct(&rates, 0.025), pct(&rates, 0.975))
}

fn base_rate(arm: &ArmOut, cfg: usize, univs: &[usize], dirs: &[usize]) -> f64 {
    let mut t = Cnt::default();
    for &u in univs {
        for &d in dirs {
            t.plus(arm.base[u][d][cfg]);
        }
    }
    if t.n > 0 {
        t.w as f64 / t.n as f64
    } else {
        f64::NAN
    }
}

fn e1_rows(arm: &ArmOut, combo: usize, tfl: &str, barriers: &[String; 2]) -> Vec<E1Row> {
    let mut rows = Vec::new();
    let universes: [(&str, Vec<usize>); 3] = [("pooled", vec![0, 1]), ("index", vec![0]), ("stocks", vec![1])];
    let dirsets: [(&str, Vec<usize>); 3] = [("all", vec![0, 1]), ("long", vec![0]), ("short", vec![1])];
    for (kind_i, kind) in KINDS.iter().enumerate() {
        for cfg in 0..2 {
            for (un, univs) in &universes {
                for (dn_, dirs) in &dirsets {
                    if *un != "pooled" && *dn_ != "all" {
                        continue;
                    }
                    let c = tally(arm, combo, kind_i, cfg, univs, dirs);
                    let (p, lo, hi) = wilson(c.w, c.n);
                    let (ca, ca_lo, ca_hi) = ctrl_a(arm, kind_i, cfg, univs, dirs);
                    let bb = base_rate(arm, cfg, univs, dirs);
                    rows.push(E1Row {
                        arm: tfl.into(),
                        kind: kind.label().into(),
                        barrier: barriers[cfg].clone(),
                        universe: (*un).into(),
                        dir: (*dn_).into(),
                        n: c.n,
                        hits: c.w,
                        rate: p,
                        ci_lo: lo,
                        ci_hi: hi,
                        ctrl_a: ca,
                        ctrl_a_lo: ca_lo,
                        ctrl_a_hi: ca_hi,
                        base_b: bb,
                        lift_a: p - ca,
                        lift_b: p - bb,
                    });
                }
            }
        }
    }
    rows
}

// ---------- E2 / E3 helpers ----------

#[derive(Serialize, Clone)]
pub struct E2Row {
    pub strategy: String,
    pub target: String,
    pub split: String,
    #[serde(flatten)]
    pub s: Summary,
}

#[derive(Serialize, Clone)]
pub struct RandomRow {
    pub target: String,
    pub observed: f64,
    pub random_mean: f64,
    pub random_lo: f64,
    pub random_hi: f64,
    pub p_value: f64,
}

#[derive(Serialize, Clone)]
pub struct Fold {
    pub year: i32,
    pub cell: String,
    pub train_n: usize,
    pub train_exp: f64,
    pub test_n: usize,
    pub test_exp: f64,
    pub test_r_sum: f64,
}

#[derive(Serialize, Clone)]
pub struct Slice {
    pub name: String,
    #[serde(flatten)]
    pub s: Summary,
}

#[derive(Serialize, Clone)]
pub struct E3Crit {
    pub edge_pos: bool,
    pub boot_lo_pos: bool,
    pub n_ge_200: bool,
    pub beats_random: bool,
    pub dsr_pos: bool,
    pub folds_60pct: bool,
    pub year_at_most_half: bool,
    pub pass: bool,
}

#[derive(Serialize, Clone)]
pub struct E3Arm {
    pub folds: Vec<Fold>,
    pub oos: Summary,
    pub boot_lo: f64,
    pub boot_hi: f64,
    pub random_p: f64,
    pub random_mean: f64,
    pub sr_daily: f64,
    pub sr0_daily: f64,
    pub sr_var_across_grid: f64,
    pub dsr_prob: f64,
    pub pos_fold_share: f64,
    pub max_year_share: f64,
    pub slices: Vec<Slice>,
    pub crit: E3Crit,
}

fn cell_label(arm: &ArmOut, c: usize) -> String {
    format!("{} | {}", arm.combos[c / arm.targets.len()].label, arm.targets[c % arm.targets.len()])
}

fn walk_forward(cfg: &Config, arm: &ArmOut, prep: &[Prepared], days: &[i32], loaded: &Loaded) -> E3Arm {
    let nsym = prep.len();
    let (first, last) = (cfg.wf_first_year, cfg.wf_last_year);
    let mut folds = Vec::new();
    let mut oos: Vec<&TradeRec> = Vec::new();
    for y in first..=last {
        let mut best: Option<(usize, f64, usize)> = None;
        for (c, tr) in arm.cell_trades.iter().enumerate() {
            let train: Vec<&TradeRec> = tr
                .iter()
                .filter(|t| {
                    let yy = year_of(t.entry_day);
                    yy >= y - cfg.wf_train_years && yy < y
                })
                .collect();
            if train.len() < cfg.wf_min_trades {
                continue;
            }
            let e = train.iter().map(|t| t.r).sum::<f64>() / train.len() as f64;
            if best.is_none_or(|(_, be, _)| e > be) {
                best = Some((c, e, train.len()));
            }
        }
        match best {
            Some((c, te, tn)) => {
                let test: Vec<&TradeRec> = arm.cell_trades[c].iter().filter(|t| year_of(t.entry_day) == y).collect();
                let sum: f64 = test.iter().map(|t| t.r).sum();
                folds.push(Fold {
                    year: y,
                    cell: cell_label(arm, c),
                    train_n: tn,
                    train_exp: te,
                    test_n: test.len(),
                    test_exp: if test.is_empty() { 0.0 } else { sum / test.len() as f64 },
                    test_r_sum: sum,
                });
                oos.extend(test);
            }
            None => folds.push(Fold {
                year: y,
                cell: "no cell with >= min train trades".into(),
                train_n: 0,
                train_exp: 0.0,
                test_n: 0,
                test_exp: 0.0,
                test_r_sum: 0.0,
            }),
        }
    }
    oos.sort_by_key(|t| (t.entry_day, t.sym));
    let oos_days: Vec<i32> = days.iter().copied().filter(|d| (first..=last).contains(&year_of(*d))).collect();
    let oos_sum = summarize(&oos, &oos_days, nsym);
    let r_vec: Vec<f64> = oos.iter().map(|t| t.r).collect();
    let (blo, bhi) = stats::block_bootstrap_ci(&r_vec, 10, cfg.bootstrap_reps, cfg.bootstrap_seed);
    let rnd = random_expectancies(prep, &oos, arm.cost_idx, arm.cost_stk, arm.h, cfg.random_entry_runs, cfg.seed ^ 0xA5A5);
    let p = stats::pvalue_ge(&rnd, oos_sum.expectancy);
    let rets = daily_returns(&oos, &oos_days, nsym);
    let sr = stats::sharpe_daily(&rets);
    let cell_sr: Vec<f64> = arm
        .cell_trades
        .iter()
        .map(|tr| {
            let v: Vec<&TradeRec> = tr.iter().filter(|t| (first..=last).contains(&year_of(t.entry_day))).collect();
            stats::sharpe_daily(&daily_returns(&v, &oos_days, nsym))
        })
        .collect();
    let var = stats::sample_var(&cell_sr);
    let (m3, m4) = stats::moments(&rets);
    let (sr0, dsr_p) = stats::dsr(sr, var, cell_sr.len(), rets.len(), m3, m4);

    let traded: Vec<&Fold> = folds.iter().filter(|f| f.test_n > 0).collect();
    let pos_share = if traded.is_empty() {
        0.0
    } else {
        traded.iter().filter(|f| f.test_r_sum > 0.0).count() as f64 / traded.len() as f64
    };
    let total: f64 = folds.iter().map(|f| f.test_r_sum).sum();
    let max_y = folds.iter().map(|f| f.test_r_sum).fold(f64::MIN, f64::max);
    let max_year_share = if total > 0.0 { max_y / total } else { 1.0 };

    let regime_of = |t: &TradeRec| regime_at(&loaded.regime, t.entry_day);
    let mut slices = Vec::new();
    let mut add = |name: &str, v: Vec<&TradeRec>| slices.push(Slice { name: name.into(), s: summarize(&v, &oos_days, nsym) });
    add("NIFTY above 200-DMA", oos.iter().copied().filter(|t| regime_of(t) == Some(true)).collect());
    add("NIFTY below 200-DMA", oos.iter().copied().filter(|t| regime_of(t) == Some(false)).collect());
    for (lbl, q) in [("liquidity tercile low", 0u8), ("liquidity tercile mid", 1), ("liquidity tercile high", 2), ("index", 3)] {
        add(lbl, oos.iter().copied().filter(|t| loaded.liq[t.sym as usize] == q).collect());
    }
    add("long", oos.iter().copied().filter(|t| t.dir > 0).collect());
    add("short", oos.iter().copied().filter(|t| t.dir < 0).collect());
    add("all OOS", oos.clone());

    let crit = E3Crit {
        edge_pos: oos_sum.expectancy > 0.0,
        boot_lo_pos: blo > 0.0,
        n_ge_200: oos_sum.n >= 200,
        beats_random: p < 0.05,
        dsr_pos: sr > sr0,
        folds_60pct: pos_share >= 0.6,
        year_at_most_half: max_year_share <= 0.5,
        pass: false,
    };
    let crit = E3Crit {
        pass: crit.edge_pos
            && crit.boot_lo_pos
            && crit.n_ge_200
            && crit.beats_random
            && crit.dsr_pos
            && crit.folds_60pct
            && crit.year_at_most_half,
        ..crit
    };
    E3Arm {
        folds,
        oos: oos_sum,
        boot_lo: blo,
        boot_hi: bhi,
        random_p: p,
        random_mean: stats::mean(&rnd),
        sr_daily: sr,
        sr0_daily: sr0,
        sr_var_across_grid: var,
        dsr_prob: dsr_p,
        pos_fold_share: pos_share,
        max_year_share,
        slices,
        crit,
    }
}

fn regime_at(regime: &BTreeMap<i32, bool>, day: i32) -> Option<bool> {
    regime.range(..day).next_back().map(|(_, v)| *v)
}

// ---------- full run ----------

#[derive(Serialize)]
pub struct E2Arm {
    pub rows: Vec<E2Row>,
    pub random: Vec<RandomRow>,
    pub baseline_strategies: Vec<E2Row>,
}

#[derive(Serialize)]
pub struct ArmReport {
    pub tf: String,
    pub horizon: usize,
    pub cost_idx_bps: f64,
    pub cost_stk_bps: f64,
    pub ref_label: String,
    pub e1_rows: Vec<E1Row>,
    pub e1_grid: Vec<GridRow>,
    pub e1_ref_years: Vec<YearRow>,
    pub e1_crit: E1Crit,
    pub sweeps: Vec<(String, usize)>,
    pub e2: E2Arm,
    pub e3: E3Arm,
}

#[derive(Serialize)]
pub struct Verdict {
    pub tf: String,
    pub e1_pass: bool,
    pub e3_pass: bool,
    pub go: bool,
}

#[derive(Serialize)]
pub struct BuyHold {
    pub cagr: f64,
    pub max_dd: f64,
    pub first: String,
    pub last: String,
}

#[derive(Serialize)]
pub struct RunOut {
    pub run_id: String,
    pub git_commit: String,
    pub seed: u64,
    pub e0: Vec<CleanStats>,
    pub xcheck: XCheck,
    pub universe_size: usize,
    pub buyhold: BuyHold,
    pub arms: Vec<ArmReport>,
    pub verdict: Vec<Verdict>,
}

fn e1_crit(rows: &[E1Row], primary: &str) -> E1Crit {
    let pick = |k: Kind| rows.iter().find(|r| r.kind == k.label() && r.universe == "pooled" && r.dir == "all" && r.barrier == primary).cloned().expect("E1 row");
    let (hpz, fib, smc) = (pick(Kind::Hpz), pick(Kind::Fib), pick(Kind::Smc));
    let beats_random = hpz.ci_lo > hpz.ctrl_a;
    let beats_fs = hpz.rate > fib.rate && hpz.rate > smc.rate;
    E1Crit {
        hpz_rate: hpz.rate,
        hpz_ci_lo: hpz.ci_lo,
        ctrl_a: hpz.ctrl_a,
        fib_rate: fib.rate,
        smc_rate: smc.rate,
        beats_random_level: beats_random,
        beats_fib_and_smc: beats_fs,
        pass: beats_random && beats_fs,
    }
}

fn analyse_arm(cfg: &Config, prep: &[Prepared], tf: Tf, loaded: &Loaded, days: &[i32]) -> ArmReport {
    let nsym = prep.len();
    let arm = run_arm(cfg, prep, tf);
    let nt = arm.targets.len();
    let ref_label = arm.combos[arm.ref_combo].label.clone();
    let barriers: [String; 2] = [
        format!("+{}/-{} ATR", cfg.barriers[0][0], cfg.barriers[0][1]),
        format!("+{}/-{} ATR", cfg.barriers[1][0], cfg.barriers[1][1]),
    ];
    let e1_rows = e1_rows(&arm, arm.ref_combo, tf.label(), &barriers);
    let e1_grid: Vec<GridRow> = (0..arm.combos.len())
        .map(|c| {
            let g = |k: usize| tally(&arm, c, k, 0, &[0, 1], &[0, 1]);
            let (h, s, f) = (g(Kind::Hpz as usize), g(Kind::Smc as usize), g(Kind::Fib as usize));
            GridRow {
                combo: arm.combos[c].label.clone(),
                hpz_n: h.n,
                hpz_rate: wilson(h.w, h.n).0,
                smc_rate: wilson(s.w, s.n).0,
                fib_rate: wilson(f.w, f.n).0,
            }
        })
        .collect();
    let crit = e1_crit(&e1_rows, &barriers[0]);
    let mut e1_ref_years = Vec::new();
    for (y, t) in &arm.ref_year {
        for k in [Kind::Hpz, Kind::Smc, Kind::Fib] {
            let c = {
                let mut x = Cnt::default();
                for d in 0..2 {
                    x.plus(t[k as usize][d][0]);
                }
                x
            };
            let mut b = Cnt::default();
            if let Some(bb) = arm.base_year.get(y) {
                for d in 0..2 {
                    b.plus(bb[d][0]);
                }
            }
            e1_ref_years.push(YearRow {
                year: *y,
                kind: k.label().into(),
                n: c.n,
                rate: wilson(c.w, c.n).0,
                base: if b.n > 0 { b.w as f64 / b.n as f64 } else { f64::NAN },
            });
        }
    }
    let sweeps = ctx_kd_sweeps(cfg, &arm);

    // E2 on the reference cell
    let mut e2_rows = Vec::new();
    let mut e2_random = Vec::new();
    let mut baseline_rows = Vec::new();
    for ti in 0..nt {
        let cell = arm.ref_combo * nt + ti;
        let all: Vec<&TradeRec> = arm.cell_trades[cell].iter().collect();
        let tgt = arm.targets[ti].clone();
        let splits: [(&str, Vec<&TradeRec>); 5] = [
            ("pooled", all.clone()),
            ("index", all.iter().copied().filter(|t| t.index).collect()),
            ("stocks", all.iter().copied().filter(|t| !t.index).collect()),
            ("long", all.iter().copied().filter(|t| t.dir > 0).collect()),
            ("short", all.iter().copied().filter(|t| t.dir < 0).collect()),
        ];
        for (sp, v) in splits {
            let s = summarize(&v, days, nsym);
            e2_rows.push(E2Row { strategy: "HPZ".into(), target: tgt.clone(), split: sp.into(), s });
        }
        let rnd = random_expectancies(prep, &all, arm.cost_idx, arm.cost_stk, arm.h, cfg.random_entry_runs, cfg.seed ^ 0x5EED);
        let obs = summarize(&all, days, nsym).expectancy;
        e2_random.push(RandomRow {
            target: tgt.clone(),
            observed: obs,
            random_mean: stats::mean(&rnd),
            random_lo: pct_sorted(&rnd, 0.025),
            random_hi: pct_sorted(&rnd, 0.975),
            p_value: stats::pvalue_ge(&rnd, obs),
        });
        for (bk, name) in ["SMC-only (OB)", "Fib-only", "MA20/50 touch"].iter().enumerate() {
            let v: Vec<&TradeRec> = arm.base_trades[bk * nt + ti].iter().collect();
            baseline_rows.push(E2Row { strategy: (*name).into(), target: tgt.clone(), split: "pooled".into(), s: summarize(&v, days, nsym) });
        }
    }
    let e3 = walk_forward(cfg, &arm, prep, days, loaded);
    let cost_idx_bps = arm.cost_idx;
    let cost_stk_bps = arm.cost_stk;
    ArmReport {
        tf: tf.label().into(),
        horizon: arm.h,
        cost_idx_bps,
        cost_stk_bps,
        ref_label,
        e1_rows,
        e1_grid,
        e1_ref_years,
        e1_crit: crit,
        sweeps,
        e2: E2Arm { rows: e2_rows, random: e2_random, baseline_strategies: baseline_rows },
        e3,
    }
}

fn ctx_kd_sweeps(cfg: &Config, arm: &ArmOut) -> Vec<(String, usize)> {
    let kd: Vec<(usize, f64)> = cfg.grid.k.iter().flat_map(|&k| cfg.grid.d.iter().map(move |&d| (k, d))).collect();
    kd.iter().zip(arm.sweeps.iter()).map(|((k, d), s)| (format!("k{k} d{d}"), *s)).collect()
}

fn pct_sorted(v: &[f64], q: f64) -> f64 {
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    pct(&s, q)
}

fn buy_hold(bars: &[Bar]) -> BuyHold {
    let (c0, cl) = (bars[0].c, bars[bars.len() - 1].c);
    let years = (bars[bars.len() - 1].ts - bars[0].ts).num_days() as f64 / 365.25;
    let (mut peak, mut mdd) = (c0, 0.0f64);
    for b in bars {
        peak = peak.max(b.c);
        mdd = mdd.max(1.0 - b.c / peak);
    }
    BuyHold {
        cagr: (cl / c0).powf(1.0 / years) - 1.0,
        max_dd: mdd,
        first: bars[0].ts.date().to_string(),
        last: bars[bars.len() - 1].ts.date().to_string(),
    }
}

fn git_commit() -> String {
    Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "unknown".into())
}

pub fn analyse(cfg: &Config, loaded: &Loaded, run_id: &str) -> RunOut {
    let mut days = loaded.d1[0].s.day.clone();
    days.dedup();
    let m15_days = {
        let mut d = loaded.m15[0].s.day.clone();
        d.dedup();
        d
    };
    let arms = vec![
        analyse_arm(cfg, &loaded.m15, Tf::M15, loaded, &m15_days),
        analyse_arm(cfg, &loaded.d1, Tf::D1, loaded, &days),
    ];
    let verdict = arms
        .iter()
        .map(|a| Verdict {
            tf: a.tf.clone(),
            e1_pass: a.e1_crit.pass,
            e3_pass: a.e3.crit.pass,
            go: a.e1_crit.pass && a.e3.crit.pass,
        })
        .collect();
    RunOut {
        run_id: run_id.into(),
        git_commit: git_commit(),
        seed: cfg.seed,
        e0: loaded.e0.clone(),
        xcheck: loaded.xcheck.clone(),
        universe_size: loaded.d1.len(),
        buyhold: buy_hold(&loaded.d1[0].s.bars),
        arms,
        verdict,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counts_and_percentiles() {
        assert_eq!(pct(&[1.0, 2.0, 3.0, 4.0], 0.5), 3.0);
        let mut c = Cnt::default();
        c.add(true);
        c.add(false);
        assert_eq!((c.n, c.w), (2, 1));
    }
}
