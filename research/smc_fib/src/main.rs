//! CLI: `smc_fib run --config configs/hpz.toml` runs E0-E3 on the data in `data_dir`.
//! `smc_fib sanity --config configs/hpz.toml` runs the same pipeline on random-walk data.
mod data;
mod detect;
mod events;
mod experiments;
mod indicators;
mod report;
mod stats;
mod trade;

use std::{env, fs, path::Path};

use serde::Deserialize;

#[derive(Deserialize, Clone, Debug)]
pub struct Costs {
    pub stock_d1_rt_bps: f64,
    pub stock_m15_rt_bps: f64,
    pub stock_slip_bps: f64,
    pub index_rt_bps: f64,
    pub index_slip_bps: f64,
}

#[derive(Deserialize, Clone, Debug)]
pub struct Grid {
    pub k: Vec<usize>,
    pub d: Vec<f64>,
    pub n: Vec<usize>,
    pub variant: Vec<String>,
    pub tau: Vec<f64>,
    pub target: Vec<String>,
}

#[derive(Deserialize, Clone, Debug)]
pub struct Reference {
    pub k: usize,
    pub d: f64,
    pub n: usize,
    pub variant: String,
    pub tau: f64,
}

#[derive(Deserialize, Clone, Debug)]
pub struct Config {
    pub run_id: String,
    pub seed: u64,
    pub data_dir: String,
    pub results_dir: String,
    pub c: f64,
    pub random_draws: usize,
    pub random_entry_runs: usize,
    pub bootstrap_reps: usize,
    pub bootstrap_seed: u64,
    pub horizon_m15: usize,
    pub horizon_d1: usize,
    pub barriers: Vec<[f64; 2]>,
    pub wf_first_year: i32,
    pub wf_last_year: i32,
    pub wf_train_years: i32,
    pub wf_min_trades: usize,
    pub grid: Grid,
    pub reference: Reference,
    pub costs: Costs,
}

fn main() -> data::Res<()> {
    let args: Vec<String> = env::args().collect();
    let (cmd, cfg_path) = match (args.get(1), args.get(2), args.get(3)) {
        (Some(c), Some(flag), Some(p)) if flag == "--config" => (c.as_str(), p.as_str()),
        _ => {
            eprintln!("usage: smc_fib <run|sanity> --config <path.toml>");
            std::process::exit(2);
        }
    };
    let cfg: Config = toml::from_str(&fs::read_to_string(cfg_path)?)?;
    assert_eq!(cfg.barriers.len(), 2, "config must give exactly two barrier pairs");
    match cmd {
        "run" => {
            let loaded = experiments::load(&cfg)?;
            let out = experiments::analyse(&cfg, &loaded, &cfg.run_id);
            let dir = Path::new(&cfg.results_dir).join(&cfg.run_id);
            fs::create_dir_all(&dir)?;
            fs::copy(cfg_path, dir.join("config.toml"))?;
            let manifest = Path::new(&cfg.data_dir).join("MANIFEST");
            if manifest.exists() {
                fs::copy(&manifest, dir.join("data_manifest.txt"))?;
            }
            fs::write(dir.join("results.json"), serde_json::to_string_pretty(&out)?)?;
            fs::write(dir.join("report.md"), report::render(&out))?;
            for v in &out.verdict {
                println!("{}: E1 {} · E3 {} → {}", v.tf, v.e1_pass, v.e3_pass, if v.go { "GO" } else { "NO-GO" });
            }
            println!("wrote {}", dir.display());
        }
        "sanity" => {
            let loaded = experiments::synthetic(cfg.seed);
            let out = experiments::analyse(&cfg, &loaded, &format!("sanity_{}", cfg.run_id));
            let dir = Path::new(&cfg.results_dir).join(&out.run_id);
            fs::create_dir_all(&dir)?;
            fs::write(dir.join("results.json"), serde_json::to_string_pretty(&out)?)?;
            fs::write(dir.join("report.md"), report::render(&out))?;
            println!("wrote {}", dir.display());
        }
        other => {
            eprintln!("unknown command {other}");
            std::process::exit(2);
        }
    }
    Ok(())
}
