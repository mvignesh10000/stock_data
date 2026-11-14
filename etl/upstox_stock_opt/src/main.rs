//! Upstox Plus expired-contract downloader for single-stock monthly options.
//!
//! For each stock in `symbols.csv` and each monthly expiry in [--from, --to]:
//!   * contracts  : GET /v2/expired-instruments/option/contract
//!   * strike band: underlying daily low/high over [expiry-35d, expiry], widened by +/-8 %
//!   * candles    : GET /v2/expired-instruments/historical-candle/{key}/15minute/{expiry}/{expiry-92d}
//! Output per expiry: one Parquet file (OHLC, volume, OI per contract per 15 min).
//! Output per stock : one private Kaggle dataset `upstox-stock-options-15m-<symbol>` holding those
//! files plus the underlying's daily candles. The stock's folder is deleted after a successful upload.
//!
//! Resumable: stocks whose dataset already exists on Kaggle are skipped, and expiries whose Parquet
//! already exists locally are skipped. Rate limit: 960 calls per 30 min (and 240 per minute).
//!
//! Usage:
//!   KAGGLE_API_TOKEN=... UPSTOX_ACCESS_TOKEN=... upstox_stock_opt \
//!     --symbols symbols.csv --from 2024-10-01 --to 2026-11-14 --work DIR \
//!     [--owner mvignesh2k19] [--only RELIANCE,TCS]

use arrow_array::{ArrayRef, Float64Array, Int64Array, RecordBatch, StringArray, TimestampMicrosecondArray};
use arrow_schema::{DataType, Field, Schema, TimeUnit};
use chrono::{Duration, NaiveDate, NaiveDateTime};
use parquet::arrow::ArrowWriter;
use parquet::basic::{Compression, ZstdLevel};
use parquet::file::properties::WriterProperties;
use serde_json::{json, Value};
use std::collections::{HashSet, VecDeque};
use std::fs::{self, File};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Arc;
use std::thread;
use std::time::{Duration as StdDuration, Instant};

type Res<T> = Result<T, Box<dyn std::error::Error>>;

const BASE: &str = "https://api.upstox.com";
const MONEYNESS: f64 = 0.08;
const BAND_DAYS: i64 = 35;
const LOOKBACK_DAYS: i64 = 92;
const DATE_FMT: &str = "%Y-%m-%d";

/// Sliding-window limiter for 960 requests / 30 min and 240 / min.
struct Limiter {
    hist: VecDeque<Instant>,
}

impl Limiter {
    fn wait(&mut self) {
        loop {
            let now = Instant::now();
            while self.hist.front().map_or(false, |t| now.duration_since(*t) > StdDuration::from_secs(1800)) {
                self.hist.pop_front();
            }
            let n60 = self.hist.iter().rev().take_while(|t| now.duration_since(**t) < StdDuration::from_secs(60)).count();
            let block = if self.hist.len() >= 960 {
                Some(StdDuration::from_secs(1800) - now.duration_since(self.hist[0]))
            } else if n60 >= 240 {
                Some(StdDuration::from_secs(60) - now.duration_since(self.hist[self.hist.len() - n60]))
            } else {
                None
            };
            match block {
                Some(d) => thread::sleep(d + StdDuration::from_millis(100)),
                None => break,
            }
        }
        self.hist.push_back(Instant::now());
    }
}

struct Api {
    agent: ureq::Agent,
    token: String,
    lim: Limiter,
    calls: u64,
}

impl Api {
    /// GET + JSON. Ok(None) for a 4xx (for example, no data for that key); retries 429/401/5xx/transport errors.
    fn get(&mut self, url: &str) -> Res<Option<Value>> {
        for attempt in 0..6u64 {
            self.lim.wait();
            self.calls += 1;
            let r = self
                .agent
                .get(url)
                .set("Authorization", &format!("Bearer {}", self.token))
                .set("Accept", "application/json")
                .call();
            match r {
                Ok(resp) => return Ok(Some(serde_json::from_str(&resp.into_string()?)?)),
                Err(ureq::Error::Status(code, _)) if code == 429 || code == 401 => {
                    eprintln!("  HTTP {code}: waiting 60 s");
                    thread::sleep(StdDuration::from_secs(60));
                }
                Err(ureq::Error::Status(code, _)) if code >= 500 => {
                    eprintln!("  HTTP {code} (attempt {attempt}): retrying");
                    thread::sleep(StdDuration::from_secs(10 * (attempt + 1)));
                }
                Err(ureq::Error::Status(code, resp)) => {
                    let body = resp.into_string().unwrap_or_default();
                    eprintln!("  HTTP {code} {}: {}", url, body.chars().take(160).collect::<String>());
                    return Ok(None);
                }
                Err(e) => {
                    eprintln!("  transport error (attempt {attempt}): {e}");
                    thread::sleep(StdDuration::from_secs(5 * (attempt + 1)));
                }
            }
        }
        Err(format!("gave up on {url}").into())
    }
}

#[derive(Clone)]
struct Candle {
    ts: NaiveDateTime,
    o: f64,
    h: f64,
    l: f64,
    c: f64,
    vol: i64,
    oi: i64,
}

/// Parses `data.candles`: [ts, open, high, low, close, volume, oi] rows.
fn parse_candles(v: Option<&Value>) -> Vec<Candle> {
    let Some(arr) = v.and_then(|x| x.pointer("/data/candles")).and_then(|x| x.as_array()) else {
        return vec![];
    };
    let mut out = Vec::with_capacity(arr.len());
    for row in arr {
        let Some(a) = row.as_array() else { continue };
        if a.len() < 7 {
            continue;
        }
        let Some(ts) = a[0]
            .as_str()
            .and_then(|s| s.get(..19))
            .and_then(|s| NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S").ok())
        else {
            continue;
        };
        out.push(Candle {
            ts,
            o: a[1].as_f64().unwrap_or(f64::NAN),
            h: a[2].as_f64().unwrap_or(f64::NAN),
            l: a[3].as_f64().unwrap_or(f64::NAN),
            c: a[4].as_f64().unwrap_or(f64::NAN),
            vol: a[5].as_i64().unwrap_or(0),
            oi: a[6].as_i64().unwrap_or(0),
        });
    }
    out
}

fn enc(key: &str) -> String {
    key.replace('|', "%7C")
}

fn sanitize(sym: &str) -> String {
    sym.chars()
        .map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_lowercase() } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

fn write_parquet(path: &Path, batch: RecordBatch) -> Res<()> {
    let tmp = PathBuf::from(format!("{}.tmp", path.display()));
    let props = WriterProperties::builder()
        .set_compression(Compression::ZSTD(ZstdLevel::default()))
        .build();
    let mut w = ArrowWriter::try_new(File::create(&tmp)?, batch.schema(), Some(props))?;
    w.write(&batch)?;
    w.close()?;
    fs::rename(tmp, path)?;
    Ok(())
}

struct OptRow {
    expiry: String,
    key: String,
    opt: String,
    strike: f64,
    lot: i64,
    c: Candle,
}

fn write_options(path: &Path, symbol: &str, rows: &[OptRow]) -> Res<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("symbol", DataType::Utf8, false),
        Field::new("expiry", DataType::Utf8, false),
        Field::new("instrument_key", DataType::Utf8, false),
        Field::new("opt", DataType::Utf8, false),
        Field::new("strike", DataType::Float64, false),
        Field::new("lot_size", DataType::Int64, false),
        Field::new("ts", DataType::Timestamp(TimeUnit::Microsecond, None), false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("volume", DataType::Int64, false),
        Field::new("oi", DataType::Int64, false),
    ]));
    let cols: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from_iter_values(rows.iter().map(|_| symbol))),
        Arc::new(StringArray::from_iter_values(rows.iter().map(|r| r.expiry.as_str()))),
        Arc::new(StringArray::from_iter_values(rows.iter().map(|r| r.key.as_str()))),
        Arc::new(StringArray::from_iter_values(rows.iter().map(|r| r.opt.as_str()))),
        Arc::new(Float64Array::from(rows.iter().map(|r| r.strike).collect::<Vec<_>>())),
        Arc::new(Int64Array::from(rows.iter().map(|r| r.lot).collect::<Vec<_>>())),
        Arc::new(TimestampMicrosecondArray::from(
            rows.iter().map(|r| r.c.ts.and_utc().timestamp_micros()).collect::<Vec<_>>(),
        )),
        Arc::new(Float64Array::from(rows.iter().map(|r| r.c.o).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|r| r.c.h).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|r| r.c.l).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(rows.iter().map(|r| r.c.c).collect::<Vec<_>>())),
        Arc::new(Int64Array::from(rows.iter().map(|r| r.c.vol).collect::<Vec<_>>())),
        Arc::new(Int64Array::from(rows.iter().map(|r| r.c.oi).collect::<Vec<_>>())),
    ];
    write_parquet(path, RecordBatch::try_new(schema, cols)?)
}

fn write_underlying(path: &Path, symbol: &str, days: &[Candle]) -> Res<()> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("symbol", DataType::Utf8, false),
        Field::new("trade_date", DataType::Utf8, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("volume", DataType::Int64, false),
    ]));
    let dates: Vec<String> = days.iter().map(|d| d.ts.date().format(DATE_FMT).to_string()).collect();
    let cols: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from_iter_values(days.iter().map(|_| symbol))),
        Arc::new(StringArray::from_iter_values(dates.iter().map(|s| s.as_str()))),
        Arc::new(Float64Array::from(days.iter().map(|d| d.o).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(days.iter().map(|d| d.h).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(days.iter().map(|d| d.l).collect::<Vec<_>>())),
        Arc::new(Float64Array::from(days.iter().map(|d| d.c).collect::<Vec<_>>())),
        Arc::new(Int64Array::from(days.iter().map(|d| d.vol).collect::<Vec<_>>())),
    ];
    write_parquet(path, RecordBatch::try_new(schema, cols)?)
}

fn expiries(api: &mut Api, key: &str, from: NaiveDate, to: NaiveDate) -> Res<Vec<NaiveDate>> {
    let url = format!("{BASE}/v2/expired-instruments/expiries?instrument_key={}", enc(key));
    let v = api.get(&url)?.unwrap_or(json!({}));
    let mut out: Vec<NaiveDate> = v
        .get("data")
        .and_then(|d| d.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|s| s.as_str().and_then(|s| NaiveDate::parse_from_str(s, DATE_FMT).ok()))
                .filter(|d| *d >= from && *d <= to)
                .collect()
        })
        .unwrap_or_default();
    out.sort();
    Ok(out)
}

/// Contracts for one expiry: (instrument_key, CE|PE, strike, lot_size).
fn contracts(api: &mut Api, key: &str, expiry: NaiveDate) -> Res<Vec<(String, String, f64, i64)>> {
    let url = format!(
        "{BASE}/v2/expired-instruments/option/contract?instrument_key={}&expiry_date={}",
        enc(key),
        expiry.format(DATE_FMT)
    );
    let v = api.get(&url)?.unwrap_or(json!({}));
    Ok(v.get("data")
        .and_then(|d| d.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|c| {
                    Some((
                        c.get("instrument_key")?.as_str()?.to_string(),
                        c.get("instrument_type")?.as_str()?.to_string(),
                        c.get("strike_price")?.as_f64()?,
                        c.get("lot_size").and_then(|x| x.as_i64()).unwrap_or(0),
                    ))
                })
                .collect()
        })
        .unwrap_or_default())
}

fn existing_datasets(owner: &str) -> Res<HashSet<String>> {
    let out = Command::new("kaggle")
        .args(["datasets", "list", "--mine", "-v", "--page-size", "200"])
        .output()?;
    if !out.status.success() {
        return Err(format!("kaggle list failed: {}", String::from_utf8_lossy(&out.stderr)).into());
    }
    let mut set = HashSet::new();
    for line in String::from_utf8_lossy(&out.stdout).lines() {
        if let Some(r) = line.split(',').next() {
            if r.starts_with(&format!("{owner}/")) {
                set.insert(r.to_string());
            }
        }
    }
    Ok(set)
}

fn upload(owner: &str, slug: &str, dir: &Path) -> Res<()> {
    let id = format!("{owner}/{slug}");
    let title = slug.replace('-', " ");
    let meta = json!({ "title": title, "id": id, "licenses": [{ "name": "other" }] });
    fs::write(dir.join("dataset-metadata.json"), serde_json::to_string_pretty(&meta)?)?;
    let st = Command::new("kaggle")
        .args(["datasets", "create", "-p", dir.to_str().unwrap()])
        .status()?;
    if !st.success() {
        return Err(format!("kaggle create failed for {id}").into());
    }
    Ok(())
}

fn run_symbol(api: &mut Api, owner: &str, sym: &str, key: &str, from: NaiveDate, to: NaiveDate, work: &Path) -> Res<()> {
    let slug_sym = sanitize(sym);
    let ds_slug = format!("upstox-stock-options-15m-{slug_sym}");
    let dir = work.join(&slug_sym);
    fs::create_dir_all(&dir)?;
    let t0 = Instant::now();

    let days_url = format!(
        "{BASE}/v3/historical-candle/{}/days/1/{}/{}",
        enc(key),
        to.format(DATE_FMT),
        (from - Duration::days(BAND_DAYS + 25)).format(DATE_FMT)
    );
    let days = parse_candles(api.get(&days_url)?.as_ref());
    write_underlying(&dir.join(format!("underlying_daily__{slug_sym}.parquet")), sym, &days)?;

    let exps = expiries(api, key, from, to)?;
    println!("{sym}: {} expiries, {} daily bars", exps.len(), days.len());
    for e in exps {
        let out = dir.join(format!("options__{slug_sym}__expiry_eq_{}.parquet", e.format(DATE_FMT)));
        if out.exists() {
            continue;
        }
        let lo_w = e - Duration::days(BAND_DAYS);
        let band: Vec<&Candle> = days.iter().filter(|d| d.ts.date() >= lo_w && d.ts.date() <= e).collect();
        if band.is_empty() {
            println!("  {sym} {e}: no underlying bars in band window, skipped");
            continue;
        }
        let lo = band.iter().map(|d| d.l).fold(f64::INFINITY, f64::min) * (1.0 - MONEYNESS);
        let hi = band.iter().map(|d| d.h).fold(f64::NEG_INFINITY, f64::max) * (1.0 + MONEYNESS);
        let all = contracts(api, key, e)?;
        let sel: Vec<_> = all
            .into_iter()
            .filter(|(_, t, k, _)| (t == "CE" || t == "PE") && *k >= lo && *k <= hi)
            .collect();

        let start = e - Duration::days(LOOKBACK_DAYS);
        let mut rows = Vec::new();
        for (ck, topt, strike, lot) in &sel {
            let url = format!(
                "{BASE}/v2/expired-instruments/historical-candle/{}/15minute/{}/{}",
                enc(ck),
                e.format(DATE_FMT),
                start.format(DATE_FMT)
            );
            let cs = parse_candles(api.get(&url)?.as_ref());
            for c in cs {
                rows.push(OptRow {
                    expiry: e.format(DATE_FMT).to_string(),
                    key: ck.clone(),
                    opt: topt.clone(),
                    strike: *strike,
                    lot: *lot,
                    c,
                });
            }
        }
        write_options(&out, sym, &rows)?;
        println!(
            "  {sym} {e}: {} contracts in band, {} rows, {} calls total, {:.0}s",
            sel.len(),
            rows.len(),
            api.calls,
            t0.elapsed().as_secs_f64()
        );
    }

    upload(owner, &ds_slug, &dir)?;
    println!("{sym}: uploaded dataset {owner}/{ds_slug}");
    fs::remove_dir_all(&dir)?;
    Ok(())
}

fn main() -> Res<()> {
    let args: Vec<String> = std::env::args().collect();
    let arg = |name: &str| -> Option<String> {
        args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
    };
    let symbols_path = PathBuf::from(arg("--symbols").ok_or("--symbols required")?);
    let from = NaiveDate::parse_from_str(&arg("--from").ok_or("--from required")?, DATE_FMT)?;
    let to = NaiveDate::parse_from_str(&arg("--to").ok_or("--to required")?, DATE_FMT)?;
    let work = PathBuf::from(arg("--work").ok_or("--work required")?);
    let owner = arg("--owner").unwrap_or_else(|| "mvignesh2k19".to_string());
    let only: Option<HashSet<String>> = arg("--only").map(|s| s.split(',').map(|x| x.trim().to_string()).collect());
    let token = std::env::var("UPSTOX_ACCESS_TOKEN").map_err(|_| "UPSTOX_ACCESS_TOKEN not set")?;

    let agent = ureq::AgentBuilder::new()
        .try_proxy_from_env(true)
        .timeout(StdDuration::from_secs(60))
        .build();
    let mut api = Api { agent, token, lim: Limiter { hist: VecDeque::new() }, calls: 0 };

    let on_kaggle = existing_datasets(&owner)?;
    println!("kaggle: {} datasets already under {owner}", on_kaggle.len());

    let text = fs::read_to_string(&symbols_path)?;
    for line in text.lines().skip(1) {
        let Some((sym, key)) = line.split_once(',') else { continue };
        if only.as_ref().map_or(false, |o| !o.contains(sym)) {
            continue;
        }
        let ds = format!("{owner}/upstox-stock-options-15m-{}", sanitize(sym));
        if on_kaggle.contains(&ds) {
            println!("{sym}: already on Kaggle ({ds}), skipped");
            continue;
        }
        if let Err(e) = run_symbol(&mut api, &owner, sym, key, from, to, &work) {
            eprintln!("{sym}: FAILED: {e} (will retry on the next run)");
        }
    }
    println!("done. upstox calls this run: {}", api.calls);
    Ok(())
}
