//! Markdown report from the run output.
use std::fmt::Write;

use crate::experiments::{ArmReport, RunOut};

fn f(x: f64, d: usize) -> String {
    if x.is_finite() {
        format!("{:.*}", d, x)
    } else {
        "n/a".into()
    }
}

fn pct(x: f64) -> String {
    if x.is_finite() {
        format!("{:.1} %", 100.0 * x)
    } else {
        "n/a".into()
    }
}

fn yn(b: bool) -> &'static str {
    if b {
        "PASS"
    } else {
        "fail"
    }
}

pub fn render(out: &RunOut) -> String {
    let mut s = String::new();
    let _ = writeln!(s, "# SMC + Fibonacci High-Probability Zone (HPZ): local test report\n");
    let _ = writeln!(s, "- run: `{}`  |  git: `{}`  |  seed: {}", out.run_id, out.git_commit, out.seed);
    let _ = writeln!(s, "- data: NIFTY 50 index (1-min vendor file, resampled) and {} Nifty 100 stocks (15-min vendor files). Index-only and stock-only splits are shown where relevant.", out.universe_size - 1);
    let _ = writeln!(s, "- Survivorship bias: the stock list is today's Nifty 100 constituents, so every stock is a survivor. Results for stocks are optimistic.\n");

    let _ = writeln!(s, "## Verdict\n");
    for v in &out.verdict {
        let _ = writeln!(
            s,
            "- **{}**: E1 event criteria {} · E3 walk-forward criteria {} → **{}**",
            v.tf,
            yn(v.e1_pass),
            yn(v.e3_pass),
            if v.go { "GO (research-only screener variant may be proposed)" } else { "NO-GO" }
        );
    }
    let _ = writeln!(s);

    let _ = writeln!(s, "## E0 Data integrity\n");
    let _ = writeln!(s, "| series | raw rows | out of session | bad OHLC | duplicates | bars | sessions | missing slots | zero-volume bars | first | last |");
    let _ = writeln!(s, "|---|---|---|---|---|---|---|---|---|---|---|");
    for c in &out.e0 {
        let _ = writeln!(
            s,
            "| {} | {} | {} | {} | {} | {} | {} | {} ({}) | {} | {} | {} |",
            c.name,
            c.raw_rows,
            c.out_of_session,
            c.bad_ohlc,
            c.duplicates,
            c.bars,
            c.sessions,
            c.missing_bars,
            pct(c.missing_bars as f64 / c.expected_bars.max(1) as f64),
            c.zero_volume_bars,
            c.first,
            c.last
        );
    }
    let x = &out.xcheck;
    let _ = writeln!(
        s,
        "\nCross-check of NIFTY resampled from 1-min against the vendor 15-min file: {} of {} bars match on timestamp; {} of matched 15-min closes are within 5 bp (max abs difference {} points). Daily: {} of {} days match, {} within 5 bp.\n",
        x.matched_15m,
        x.vendor_bars,
        pct(x.share_15m_close_within_5bp),
        f(x.max_abs_close_diff_pts, 2),
        x.daily_matched,
        x.daily_matched,
        pct(x.share_daily_close_within_5bp)
    );
    let _ = writeln!(
        s,
        "Index volume is zero in every bar (vendor), so volume-based rules apply to stocks only. Buy-and-hold NIFTY daily ({} to {}): CAGR {}, max drawdown {}.\n",
        out.buyhold.first,
        out.buyhold.last,
        pct(out.buyhold.cagr),
        pct(out.buyhold.max_dd)
    );

    for a in &out.arms {
        arm_section(&mut s, a);
    }

    let _ = writeln!(s, "## Caveats\n");
    let _ = writeln!(s, "- The paper gives no exact rules, event definition, base rate or costs. Rules here are our reading (see the plan); the paper's 72 % is compared against controls, not taken as given.");
    let _ = writeln!(s, "- HPZ score = P_F * P_L with P_L = 1 inside an active order block or liquidity pool. max over the bar's price range inside the zone, as in the plan.");
    let _ = writeln!(s, "- Stock daily shorts are not possible in cash delivery; short trades on daily bars are theoretical (futures-only names). Read the long-only rows for the tradable version.");
    let _ = writeln!(s, "- Stock daily costs (46 bps total) are applied to daily trades; intraday MIS costs (13 bps) to 15-min trades; index 5 bps.");
    let _ = writeln!(s, "- Sector robustness not run: the data has no sector mapping.");
    let _ = writeln!(s, "- The walk-forward selects on train trades only; the OOS years are not used to choose parameters. The reference cell for E1 and E2 was fixed before running (k=2, d=1.0, N=100, variant A, tau=0.5, c=0.5).");
    let _ = writeln!(s, "- Results are per-symbol trades pooled over the universe with 1 % risk per trade; daily returns add the R of trades that exit on the same day (no margin or capacity constraints).");
    s
}

fn arm_section(s: &mut String, a: &ArmReport) {
    let _ = writeln!(s, "## {} arm (horizon {} bars; costs: index {} bps, stocks {} bps)\n", a.tf, a.horizon, a.cost_idx_bps, a.cost_stk_bps);

    let _ = writeln!(s, "### E1 event study ({})\n", a.ref_label);
    let _ = writeln!(s, "Hit rate = +barrier before -1 ATR within H bars from the next open (timeouts and same-bar hits are losses). Control (a) = same bars, zone shifted by U(-3,3) ATR, 1000 seeded draws. Control (b) = every bar, same direction and barrier.\n");
    let _ = writeln!(s, "| kind | barrier | universe | dir | N | hit rate | Wilson 95 % | control (a) mean [95 % draws] | control (b) base | lift vs (a) | lift vs (b) |");
    let _ = writeln!(s, "|---|---|---|---|---|---|---|---|---|---|---|");
    for r in a.e1_rows.iter().filter(|r| r.universe == "pooled" && r.dir == "all" || r.dir == "all" && r.universe != "pooled") {
        if r.n == 0 {
            continue;
        }
        let _ = writeln!(
            s,
            "| {} | {} | {} | {} | {} | {} | [{}, {}] | {} [{}, {}] | {} | {} | {} |",
            r.kind,
            r.barrier,
            r.universe,
            r.dir,
            r.n,
            pct(r.rate),
            pct(r.ci_lo),
            pct(r.ci_hi),
            pct(r.ctrl_a),
            pct(r.ctrl_a_lo),
            pct(r.ctrl_a_hi),
            pct(r.base_b),
            f(100.0 * r.lift_a, 2),
            f(100.0 * r.lift_b, 2)
        );
    }
    let c = &a.e1_crit;
    let _ = writeln!(
        s,
        "\nPrimary barrier (+1/-1), pooled, both directions: HPZ {} (Wilson lower {}) vs random-level control {}; Fib-only {}; SMC-only {}.\n",
        pct(c.hpz_rate),
        pct(c.hpz_ci_lo),
        pct(c.ctrl_a),
        pct(c.fib_rate),
        pct(c.smc_rate)
    );
    let cells_beating = a.e1_grid.iter().filter(|g| g.hpz_rate > g.smc_rate && g.hpz_rate > g.fib_rate).count();
    let _ = writeln!(
        s,
        "Grid of {} zone-parameter sets (all structural choices, +1/-1 barrier, no controls): HPZ beats both SMC-only and Fib-only in {} of {} sets. Median HPZ hit rate {}, median SMC-only {}.\n",
        a.e1_grid.len(),
        cells_beating,
        a.e1_grid.len(),
        pct(median(a.e1_grid.iter().map(|g| g.hpz_rate).collect())),
        pct(median(a.e1_grid.iter().map(|g| g.smc_rate).collect()))
    );
    let _ = writeln!(s, "Calendar-year hit rates (reference cell, +1/-1, both directions, pooled universe):\n");
    let mut years: Vec<i32> = a.e1_ref_years.iter().map(|y| y.year).collect();
    years.dedup();
    let _ = writeln!(s, "| year | HPZ | N | SMC-only | N | Fib-only | N | base (every bar) |");
    let _ = writeln!(s, "|---|---|---|---|---|---|---|---|");
    for y in years {
        let get = |k: &str| a.e1_ref_years.iter().find(|r| r.year == y && r.kind == k);
        if let (Some(h), Some(sm), Some(fb)) = (get("HPZ (OB/pool x Fib)"), get("SMC-only (OB)"), get("Fib-only")) {
            let _ = writeln!(
                s,
                "| {} | {} | {} | {} | {} | {} | {} | {} |",
                y,
                pct(h.rate),
                h.n,
                pct(sm.rate),
                sm.n,
                pct(fb.rate),
                fb.n,
                pct(h.base)
            );
        }
    }
    let _ = writeln!(s);

    let _ = writeln!(s, "### E2 tradable backtest (reference cell, after costs)\n");
    let _ = writeln!(s, "| strategy | target | split | N | expectancy (R) | win rate | PF | total R | CAGR | max DD | Sharpe |");
    let _ = writeln!(s, "|---|---|---|---|---|---|---|---|---|---|---|");
    for r in a.e2.rows.iter().chain(a.e2.baseline_strategies.iter()) {
        let _ = writeln!(
            s,
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |",
            r.strategy,
            r.target,
            r.split,
            r.s.n,
            f(r.s.expectancy, 3),
            pct(r.s.win_rate),
            f(r.s.pf, 2),
            f(r.s.total_r, 1),
            pct(r.s.cagr),
            pct(r.s.max_dd),
            f(r.s.sharpe, 2)
        );
    }
    let _ = writeln!(s, "\nRandom-entry control (same symbol, year, count, stop distance, target multiple and costs; 1000 seeded runs):\n");
    let _ = writeln!(s, "| target | observed expectancy | random mean | random 95 % | p-value |");
    let _ = writeln!(s, "|---|---|---|---|---|");
    for r in &a.e2.random {
        let _ = writeln!(
            s,
            "| {} | {} | {} | [{}, {}] | {} |",
            r.target,
            f(r.observed, 3),
            f(r.random_mean, 3),
            f(r.random_lo, 3),
            f(r.random_hi, 3),
            f(r.p_value, 4)
        );
    }
    let _ = writeln!(s);

    let _ = writeln!(s, "### E3 walk-forward (grid of 64 cells; select on trailing 3 years, trade next year unchanged)\n");
    let _ = writeln!(s, "| test year | selected cell | train N | train exp (R) | test N | test exp (R) | test R sum |");
    let _ = writeln!(s, "|---|---|---|---|---|---|---|");
    for fo in &a.e3.folds {
        let _ = writeln!(
            s,
            "| {} | {} | {} | {} | {} | {} | {} |",
            fo.year,
            fo.cell,
            fo.train_n,
            f(fo.train_exp, 3),
            fo.test_n,
            f(fo.test_exp, 3),
            f(fo.test_r_sum, 1)
        );
    }
    let o = &a.e3.oos;
    let _ = writeln!(
        s,
        "\nConcatenated OOS: N {}, expectancy {} R, win rate {}, PF {}, CAGR {}, max DD {}, daily Sharpe (annualised) {}.",
        o.n,
        f(o.expectancy, 3),
        pct(o.win_rate),
        f(o.pf, 2),
        pct(o.cagr),
        pct(o.max_dd),
        f(o.sharpe, 2)
    );
    let _ = writeln!(
        s,
        "Block bootstrap (10 consecutive trades per block, 10,000 resamples, seed 42) 95 % interval of expectancy: [{}, {}] R. Random-entry p-value {} (random mean {} R). Daily SR {} vs expected maximum SR over 64 trials {} (grid variance {}); DSR probability {}.\n",
        f(a.e3.boot_lo, 3),
        f(a.e3.boot_hi, 3),
        f(a.e3.random_p, 4),
        f(a.e3.random_mean, 3),
        f(a.e3.sr_daily, 4),
        f(a.e3.sr0_daily, 4),
        f(a.e3.sr_var_across_grid, 6),
        f(a.e3.dsr_prob, 3)
    );
    let _ = writeln!(s, "Robustness slices (OOS trades):\n");
    let _ = writeln!(s, "| slice | N | expectancy (R) | win rate | PF | total R |");
    let _ = writeln!(s, "|---|---|---|---|---|---|");
    for sl in &a.e3.slices {
        let _ = writeln!(s, "| {} | {} | {} | {} | {} | {} |", sl.name, sl.s.n, f(sl.s.expectancy, 3), pct(sl.s.win_rate), f(sl.s.pf, 2), f(sl.s.total_r, 1));
    }
    let _ = writeln!(s);

    let c = &a.e3.crit;
    let _ = writeln!(s, "### Go / no-go checklist ({})\n", a.tf);
    let _ = writeln!(s, "| criterion | result |");
    let _ = writeln!(s, "|---|---|");
    let rows = [
        ("E1: HPZ beats random-level control with Wilson lower bound above it", c_e1(a, 0)),
        ("E1: HPZ beats Fib-only and SMC-only (point estimates)", c_e1(a, 1)),
        ("E3: OOS expectancy after costs > 0", c.edge_pos),
        ("E3: block-bootstrap lower bound > 0", c.boot_lo_pos),
        ("E3: at least 200 OOS trades", c.n_ge_200),
        ("E3: beats random entry at p < 0.05", c.beats_random),
        ("E3: deflated Sharpe > 0 (daily SR above the expected maximum over the grid)", c.dsr_pos),
        ("E3: positive in >= 60 % of folds", c.folds_60pct),
        ("E3: no single year above half of the PnL", c.year_at_most_half),
    ];
    for (name, ok) in rows {
        let _ = writeln!(s, "| {} | {} |", name, yn(ok));
    }
    let _ = writeln!(s, "| **Overall** | **{}** |\n", if a.e1_crit.pass && c.pass { "GO" } else { "NO-GO" });
}

fn c_e1(a: &ArmReport, which: u8) -> bool {
    if which == 0 {
        a.e1_crit.beats_random_level
    } else {
        a.e1_crit.beats_fib_and_smc
    }
}

fn median(mut v: Vec<f64>) -> f64 {
    v.retain(|x| x.is_finite());
    if v.is_empty() {
        return f64::NAN;
    }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let m = v.len() / 2;
    if v.len() % 2 == 1 {
        v[m]
    } else {
        0.5 * (v[m - 1] + v[m])
    }
}
