//! Parquet data lake -> flat binary cache (`bincode`), and fast cache loading (`memmap2`).
//!
//! The Parquet files follow the canonical schema written by the Python ETL
//! (`etl/*.py`): trade_date, expiry_date, dte, expiry_rank, minute_idx, spot_{ohlc},
//! strike, is_call, open, high, low, close, volume, oi — physically sorted by
//! (trade_date, expiry_rank, is_call, strike, minute_idx).

use arrow_array::{Array, BooleanArray, Float32Array, RecordBatch, UInt16Array, UInt32Array, UInt8Array};
use core_types::{ChainCache, OhlcBar, SpotBar, TradingDayData, MINUTES};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use rustc_hash::FxHashSet;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

fn list_parquet(dir: &Path, out: &mut Vec<PathBuf>) {
    if let Ok(rd) = std::fs::read_dir(dir) {
        let mut entries: Vec<_> = rd.flatten().map(|e| e.path()).collect();
        entries.sort();
        for p in entries {
            if p.is_dir() {
                list_parquet(&p, out);
            } else if p.extension().map(|e| e == "parquet").unwrap_or(false) {
                out.push(p);
            }
        }
    }
}

struct DayAcc {
    trade_date: u32,
    expiry_date: u32,
    dte: u8,
    spot: Vec<SpotBar>,
    rows: Vec<(u32, bool, u16, OhlcBar)>,
}

impl DayAcc {
    fn new(trade_date: u32, expiry_date: u32, dte: u8) -> Self {
        DayAcc { trade_date, expiry_date, dte, spot: vec![SpotBar::default(); MINUTES], rows: Vec::with_capacity(60_000) }
    }

    fn finish(self, rank: u8, step: u32) -> Option<TradingDayData> {
        if self.rows.is_empty() {
            return None;
        }
        let min_s = self.rows.iter().map(|r| r.0).min().unwrap();
        let max_s = self.rows.iter().map(|r| r.0).max().unwrap();
        let min_strike = min_s - (min_s % step);
        let n = ((max_s - min_strike) / step + 1) as usize;
        let mut calls = vec![OhlcBar::default(); n * MINUTES];
        let mut puts = vec![OhlcBar::default(); n * MINUTES];
        for (strike, is_call, m, bar) in self.rows {
            if (strike - min_strike) % step != 0 {
                continue; // off-grid strike (e.g. 25 pt), ignored
            }
            let i = ((strike - min_strike) / step) as usize;
            let v = if is_call { &mut calls } else { &mut puts };
            v[i * MINUTES + m as usize] = bar;
        }
        // forward-fill spot holes defensively
        let mut spot = self.spot;
        for m in 1..MINUTES {
            if spot[m].close <= 0.0 {
                spot[m] = spot[m - 1];
            }
        }
        let y = (self.trade_date / 10000) as i32;
        let mo = ((self.trade_date / 100) % 100) as u32;
        let d = (self.trade_date % 100) as u32;
        Some(TradingDayData {
            trade_date: self.trade_date,
            expiry_date: self.expiry_date,
            dte: self.dte,
            expiry_rank: rank,
            weekday: weekday(y, mo, d),
            strike_step: step,
            min_strike,
            n_strikes: n as u32,
            spot,
            calls,
            puts,
        })
    }
}

/// ISO weekday, 1 = Monday (Sakamoto's algorithm).
pub fn weekday(y: i32, m: u32, d: u32) -> u8 {
    let t = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
    let y = if m < 3 { y - 1 } else { y };
    let w = (y + y / 4 - y / 100 + y / 400 + t[(m - 1) as usize] + d as i32) % 7; // 0 = Sunday
    if w == 0 {
        7
    } else {
        w as u8
    }
}

macro_rules! col {
    ($b:expr, $name:expr, $t:ty) => {
        $b.column_by_name($name)
            .unwrap_or_else(|| panic!("missing column {}", $name))
            .as_any()
            .downcast_ref::<$t>()
            .unwrap_or_else(|| panic!("bad type for column {}", $name))
    };
}

/// Build the cache from one or more Parquet directories. Earlier directories take precedence
/// for any trade date present in several sources.
pub fn build_cache(dirs: &[PathBuf], rank: u8, step: u32, instrument: &str) -> ChainCache {
    let mut seen: FxHashSet<u32> = FxHashSet::default();
    let mut days: Vec<TradingDayData> = Vec::new();
    for dir in dirs {
        let mut files = Vec::new();
        list_parquet(dir, &mut files);
        let mut this_dir: FxHashSet<u32> = FxHashSet::default();
        for f in files {
            let file = File::open(&f).expect("open parquet");
            let reader = ParquetRecordBatchReaderBuilder::try_new(file).unwrap().with_batch_size(65536).build().unwrap();
            let mut acc: Option<DayAcc> = None;
            let mut flush = |acc: Option<DayAcc>, days: &mut Vec<TradingDayData>, this_dir: &mut FxHashSet<u32>| {
                if let Some(a) = acc {
                    let td = a.trade_date;
                    if let Some(d) = a.finish(rank, step) {
                        this_dir.insert(td);
                        days.push(d);
                    }
                }
            };
            for batch in reader {
                let b: RecordBatch = batch.unwrap();
                let td = col!(b, "trade_date", UInt32Array);
                let ed = col!(b, "expiry_date", UInt32Array);
                let dte = col!(b, "dte", UInt8Array);
                let er = col!(b, "expiry_rank", UInt8Array);
                let mi = col!(b, "minute_idx", UInt16Array);
                let so = col!(b, "spot_open", Float32Array);
                let sh = col!(b, "spot_high", Float32Array);
                let sl = col!(b, "spot_low", Float32Array);
                let sc = col!(b, "spot_close", Float32Array);
                let st = col!(b, "strike", UInt32Array);
                let ic = col!(b, "is_call", BooleanArray);
                let o = col!(b, "open", Float32Array);
                let h = col!(b, "high", Float32Array);
                let l = col!(b, "low", Float32Array);
                let c = col!(b, "close", Float32Array);
                let v = col!(b, "volume", UInt32Array);
                let oi = col!(b, "oi", UInt32Array);
                for i in 0..b.num_rows() {
                    if er.value(i) != rank {
                        continue;
                    }
                    let d = td.value(i);
                    if seen.contains(&d) {
                        continue;
                    }
                    if acc.as_ref().map(|a| a.trade_date != d).unwrap_or(true) {
                        flush(acc.take(), &mut days, &mut this_dir);
                        acc = Some(DayAcc::new(d, ed.value(i), dte.value(i)));
                    }
                    let a = acc.as_mut().unwrap();
                    let m = mi.value(i) as usize;
                    if m >= MINUTES {
                        continue;
                    }
                    a.spot[m] = SpotBar { open: so.value(i), high: sh.value(i), low: sl.value(i), close: sc.value(i) };
                    let bar = OhlcBar {
                        open: o.value(i),
                        high: h.value(i).max(c.value(i)).max(o.value(i)),
                        low: l.value(i).min(c.value(i)).min(o.value(i)),
                        close: c.value(i),
                        volume: if v.is_null(i) { 0 } else { v.value(i) },
                        oi: if oi.is_null(i) { 0 } else { oi.value(i) },
                    };
                    a.rows.push((st.value(i), ic.value(i), m as u16, bar));
                }
            }
            flush(acc.take(), &mut days, &mut this_dir);
        }
        seen.extend(this_dir);
    }
    days.sort_by_key(|d| d.trade_date);
    days.dedup_by_key(|d| d.trade_date);
    ChainCache { instrument: instrument.to_string(), days }
}

pub fn write_cache(cache: &ChainCache, out: &Path) {
    if let Some(p) = out.parent() {
        std::fs::create_dir_all(p).ok();
    }
    let f = File::create(out).expect("create cache");
    let mut w = BufWriter::new(f);
    bincode::serialize_into(&mut w, cache).expect("serialize cache");
    w.flush().unwrap();
}

/// Memory-map the cache file and deserialize it.
pub fn load_cache(path: &Path) -> ChainCache {
    let f = File::open(path).unwrap_or_else(|e| panic!("open cache {:?}: {}", path, e));
    let mmap = unsafe { memmap2::Mmap::map(&f).expect("mmap cache") };
    bincode::deserialize(&mmap[..]).expect("deserialize cache")
}
