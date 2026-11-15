//! Loading, session filtering, resampling and E0 integrity statistics.
//! Vendor timestamps are naive wall-clock times already in IST (first bar 09:15),
//! so no timezone conversion is applied.
use chrono::{Datelike, Duration, NaiveDate, NaiveDateTime, NaiveTime, Timelike};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde::{Deserialize, Serialize};
use std::error::Error;
use std::path::Path;

pub type Res<T> = Result<T, Box<dyn Error>>;

#[derive(Clone, Copy, Debug)]
pub struct Bar {
    pub ts: NaiveDateTime,
    pub o: f64,
    pub h: f64,
    pub l: f64,
    pub c: f64,
    pub v: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Tf {
    M15,
    D1,
}

impl Tf {
    pub fn label(self) -> &'static str {
        match self {
            Tf::M15 => "15m",
            Tf::D1 => "1d",
        }
    }
}

pub struct Series {
    pub is_index: bool,
    pub tf: Tf,
    pub bars: Vec<Bar>,
    /// days since 0001-01-01 (chrono `num_days_from_ce`) for each bar
    pub day: Vec<i32>,
    /// index of the last bar of the session containing bar i (i itself for daily)
    pub sess_end: Vec<usize>,
}

pub fn year_of(day: i32) -> i32 {
    NaiveDate::from_num_days_from_ce_opt(day).map_or(0, |d| d.year())
}

impl Series {
    pub fn new(is_index: bool, tf: Tf, bars: Vec<Bar>) -> Series {
        let n = bars.len();
        let day: Vec<i32> = bars.iter().map(|b| b.ts.date().num_days_from_ce()).collect();
        let mut sess_end = vec![0usize; n];
        for i in (0..n).rev() {
            sess_end[i] = if tf == Tf::D1 || i + 1 >= n || day[i + 1] != day[i] {
                i
            } else {
                sess_end[i + 1]
            };
        }
        Series { is_index, tf, bars, day, sess_end }
    }
}

#[derive(Deserialize)]
struct Row {
    date: String,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
}

pub fn read_csv(path: &Path) -> Res<Vec<Bar>> {
    let mut rdr = csv::Reader::from_path(path)?;
    let mut out = Vec::new();
    for row in rdr.deserialize::<Row>() {
        let r = row?;
        out.push(Bar {
            ts: NaiveDateTime::parse_from_str(&r.date, "%Y-%m-%d %H:%M:%S")?,
            o: r.open,
            h: r.high,
            l: r.low,
            c: r.close,
            v: r.volume,
        });
    }
    Ok(out)
}

#[derive(Serialize, Clone, Default, Debug)]
pub struct CleanStats {
    pub name: String,
    pub raw_rows: usize,
    pub out_of_session: usize,
    pub bad_ohlc: usize,
    pub duplicates: usize,
    pub bars: usize,
    pub sessions: usize,
    pub expected_bars: usize,
    pub missing_bars: usize,
    pub zero_volume_bars: usize,
    pub first: String,
    pub last: String,
}

/// Keeps 09:15 <= t < 15:30, drops bad OHLC and duplicate timestamps, sorts.
/// `slot_min` is the bar size in minutes (1 or 15) and gives the expected bars per session.
pub fn clean(name: &str, mut raw: Vec<Bar>, slot_min: i64) -> (Vec<Bar>, CleanStats) {
    let mut st = CleanStats { name: name.to_string(), raw_rows: raw.len(), ..Default::default() };
    let open_t = NaiveTime::from_hms_opt(9, 15, 0).unwrap();
    let close_t = NaiveTime::from_hms_opt(15, 30, 0).unwrap();
    raw.retain(|b| {
        let ok = b.ts.time() >= open_t && b.ts.time() < close_t;
        if !ok {
            st.out_of_session += 1;
        }
        ok
    });
    raw.retain(|b| {
        let ok = b.l > 0.0 && b.h >= b.l && b.h >= b.o.max(b.c) && b.l <= b.o.min(b.c);
        if !ok {
            st.bad_ohlc += 1;
        }
        ok
    });
    raw.sort_by_key(|b| b.ts);
    let before = raw.len();
    raw.dedup_by_key(|b| b.ts);
    st.duplicates = before - raw.len();
    st.bars = raw.len();
    st.zero_volume_bars = raw.iter().filter(|b| b.v == 0.0).count();
    let per_day = (375 / slot_min) as usize;
    let mut i = 0;
    while i < raw.len() {
        let d = raw[i].ts.date();
        let mut j = i;
        while j < raw.len() && raw[j].ts.date() == d {
            j += 1;
        }
        st.sessions += 1;
        st.expected_bars += per_day;
        st.missing_bars += per_day.saturating_sub(j - i);
        i = j;
    }
    if let (Some(f), Some(l)) = (raw.first(), raw.last()) {
        st.first = f.ts.to_string();
        st.last = l.ts.to_string();
    }
    (raw, st)
}

fn agg(group: &[Bar], ts: NaiveDateTime) -> Bar {
    Bar {
        ts,
        o: group[0].o,
        h: group.iter().map(|b| b.h).fold(f64::MIN, f64::max),
        l: group.iter().map(|b| b.l).fold(f64::MAX, f64::min),
        c: group[group.len() - 1].c,
        v: group.iter().map(|b| b.v).sum(),
    }
}

fn minute_of_session(b: &Bar) -> i64 {
    let t = b.ts.time();
    (t.hour() * 60 + t.minute()) as i64 - (9 * 60 + 15)
}

/// Cleaned 1-minute bars -> 15-minute bars anchored at 09:15; never crosses a session.
pub fn to_15m(bars: &[Bar]) -> Vec<Bar> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < bars.len() {
        let d = bars[i].ts.date();
        let bin = (minute_of_session(&bars[i]) / 15) * 15;
        let mut j = i;
        while j < bars.len() && bars[j].ts.date() == d && (minute_of_session(&bars[j]) / 15) * 15 == bin {
            j += 1;
        }
        let ts = d.and_time(NaiveTime::from_hms_opt(9, 15, 0).unwrap()) + Duration::minutes(bin);
        out.push(agg(&bars[i..j], ts));
        i = j;
    }
    out
}

/// Intraday bars (1-minute or 15-minute) -> one daily bar per session.
pub fn to_daily(bars: &[Bar]) -> Vec<Bar> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < bars.len() {
        let d = bars[i].ts.date();
        let mut j = i;
        while j < bars.len() && bars[j].ts.date() == d {
            j += 1;
        }
        out.push(agg(&bars[i..j], d.and_hms_opt(0, 0, 0).unwrap()));
        i = j;
    }
    out
}

/// Random-walk 15-minute bars (25 per weekday) for the sanity check.
pub fn synthetic_15m(seed: u64, days: usize, sigma: f64) -> Vec<Bar> {
    let mut rng = ChaCha8Rng::seed_from_u64(seed);
    let mut d = NaiveDate::from_ymd_opt(2015, 1, 1).unwrap();
    let mut px = 100.0_f64;
    let mut out = Vec::new();
    let mut made = 0;
    while made < days {
        if d.weekday().num_days_from_monday() < 5 {
            for k in 0..25 {
                let ts = d.and_hms_opt(9, 15, 0).unwrap() + Duration::minutes(15 * k);
                let u1: f64 = rng.gen::<f64>().max(1e-12);
                let u2: f64 = rng.gen();
                let z = (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos();
                let o = px;
                let c = o * (sigma * z).exp();
                let h = o.max(c) * (sigma * rng.gen::<f64>()).exp();
                let l = o.min(c) * (-sigma * rng.gen::<f64>()).exp();
                px = c;
                out.push(Bar { ts, o, h, l, c, v: 1000.0 + rng.gen::<f64>() * 500.0 });
            }
            made += 1;
        }
        d = d.succ_opt().unwrap();
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn b(ts: &str, o: f64, h: f64, l: f64, c: f64, v: f64) -> Bar {
        Bar { ts: NaiveDateTime::parse_from_str(ts, "%Y-%m-%d %H:%M:%S").unwrap(), o, h, l, c, v }
    }

    #[test]
    fn session_filter_keeps_0915_to_1530_exclusive() {
        let raw = vec![
            b("2020-01-06 09:14:00", 1.0, 1.0, 1.0, 1.0, 1.0),
            b("2020-01-06 09:15:00", 1.0, 1.0, 1.0, 1.0, 1.0),
            b("2020-01-06 15:29:00", 1.0, 1.0, 1.0, 1.0, 1.0),
            b("2020-01-06 15:30:00", 1.0, 1.0, 1.0, 1.0, 1.0),
            b("2020-01-06 20:15:00", 1.0, 1.0, 1.0, 1.0, 1.0),
        ];
        let (kept, st) = clean("t", raw, 1);
        assert_eq!(kept.len(), 2);
        assert_eq!(st.out_of_session, 3);
    }

    #[test]
    fn dedupe_keeps_first_and_drops_bad_ohlc() {
        let raw = vec![
            b("2020-01-06 09:15:00", 10.0, 11.0, 9.0, 10.5, 5.0),
            b("2020-01-06 09:15:00", 99.0, 99.0, 99.0, 99.0, 1.0),
            b("2020-01-06 09:16:00", 10.0, 9.0, 11.0, 10.0, 1.0), // h < l
        ];
        let (kept, st) = clean("t", raw, 1);
        assert_eq!(kept.len(), 1);
        assert_eq!(kept[0].o, 10.0);
        assert_eq!(st.duplicates, 1);
        assert_eq!(st.bad_ohlc, 1);
    }

    #[test]
    fn resample_15m_bins_never_cross_sessions() {
        // 09:15..09:31 on day 1 and 15:20..15:29 on day 1, then 09:15 on day 2
        let mut raw = Vec::new();
        for m in [0, 1, 15, 16] {
            let t = NaiveDateTime::parse_from_str("2020-01-06 09:15:00", "%Y-%m-%d %H:%M:%S").unwrap()
                + Duration::minutes(m);
            raw.push(Bar { ts: t, o: m as f64, h: m as f64 + 1.0, l: m as f64 - 1.0, c: m as f64 + 0.5, v: 1.0 });
        }
        let t = NaiveDateTime::parse_from_str("2020-01-07 09:15:00", "%Y-%m-%d %H:%M:%S").unwrap();
        raw.push(Bar { ts: t, o: 7.0, h: 8.0, l: 6.0, c: 7.5, v: 2.0 });
        let out = to_15m(&raw);
        assert_eq!(out.len(), 3);
        assert_eq!(out[0].ts.to_string(), "2020-01-06 09:15:00");
        assert_eq!(out[0].o, 0.0); // first open
        assert_eq!(out[0].c, 1.5); // last close of 09:15 bin (minute 1)
        assert_eq!(out[1].ts.to_string(), "2020-01-06 09:30:00");
        assert_eq!(out[1].v, 2.0);
        assert_eq!(out[2].ts.to_string(), "2020-01-07 09:15:00");
    }

    #[test]
    fn daily_ohlc_and_session_end() {
        let bars = vec![
            b("2020-01-06 09:15:00", 10.0, 12.0, 9.0, 11.0, 1.0),
            b("2020-01-06 09:30:00", 11.0, 13.0, 10.0, 12.5, 2.0),
            b("2020-01-07 09:15:00", 12.0, 12.0, 11.0, 11.5, 3.0),
        ];
        let d = to_daily(&bars);
        assert_eq!(d.len(), 2);
        assert_eq!((d[0].o, d[0].h, d[0].l, d[0].c, d[0].v), (10.0, 13.0, 9.0, 12.5, 3.0));
        let s = Series::new(false, Tf::M15, bars);
        assert_eq!(s.sess_end, vec![1, 1, 2]);
    }
}
