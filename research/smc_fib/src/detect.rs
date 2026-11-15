//! Causal SMC / Fibonacci detectors. Every value at bar t uses bars <= t only.
//! Swing pivots (k-bar fractals) are usable from bar i+k. Displaced BOS/CHoCH create
//! an impulse leg and an order block (OB); equal lows/highs within 0.1 ATR create liquidity pools.
use crate::data::{Bar, Series};
use crate::indicators::{atr, ema, sma};

pub const FIB_RET: [f64; 5] = [0.382, 0.5, 0.618, 0.705, 0.786];
pub const FIB_EXT: f64 = 1.272;
const OB_LOOKBACK: usize = 10;
const POOL_TOL_ATR: f64 = 0.1;

#[derive(Clone, Debug)]
pub struct Leg {
    pub dir: i8,
    /// up leg: swing low -> impulse high; down leg: impulse low -> swing high
    pub lo: f64,
    pub hi: f64,
    /// bar of the break (BOS/CHoCH) that created the leg
    pub brk: usize,
}

#[derive(Clone, Debug)]
pub struct Zone {
    pub dir: i8,
    pub pool: bool,
    /// activation bar (the break bar for OBs, the confirming pivot bar for pools)
    pub act: usize,
    /// [variant A = full candle range, variant B = low..body edge] as (low, high)
    pub bounds: [(f64, f64); 2],
    pub leg: Option<usize>,
    pub fvg: bool,
    pub relvol: f64,
}

pub struct Analysis {
    pub atr: Vec<f64>,
    pub ema20: Vec<f64>,
    pub ema50: Vec<f64>,
    pub trend: Vec<i8>,
    pub legs: Vec<Leg>,
    pub leg_at: Vec<Option<usize>>,
    pub zones: Vec<Zone>,
}

/// Fibonacci retracement prices of a leg (the Gaussian means of P_F).
pub fn fib_levels(leg: &Leg) -> [f64; 5] {
    let r = leg.hi - leg.lo;
    FIB_RET.map(|f| if leg.dir > 0 { leg.hi - f * r } else { leg.lo + f * r })
}

/// max over x in [lo, hi] of max_i exp(-(x-mu_i)^2 / (2 sigma^2)).
/// Each component peaks at mu_i, so the maximum over an interval is at clamp(mu_i).
pub fn pf_max(mu: &[f64], sigma: f64, lo: f64, hi: f64) -> f64 {
    if !(sigma > 0.0) {
        return 0.0;
    }
    mu.iter()
        .map(|&m| {
            let x = m.clamp(lo, hi);
            (-(x - m).powi(2) / (2.0 * sigma * sigma)).exp()
        })
        .fold(0.0, f64::max)
}

/// Liquidity sweep: wick through the pool, close back inside it.
pub fn is_sweep(b: &Bar, dir: i8, lo: f64, hi: f64) -> bool {
    if dir > 0 {
        b.l < lo && b.c >= lo
    } else {
        b.h > hi && b.c <= hi
    }
}

fn pool_zone(dir: i8, act: usize, lo: f64, hi: f64) -> Zone {
    Zone { dir, pool: true, act, bounds: [(lo, hi); 2], leg: None, fvg: false, relvol: 1.0 }
}

pub fn analyze(s: &Series, k: usize, d: f64) -> Analysis {
    let bars = &s.bars;
    let n = bars.len();
    let atr_v = atr(bars, 14);
    let closes: Vec<f64> = bars.iter().map(|b| b.c).collect();
    let vols: Vec<f64> = bars.iter().map(|b| b.v).collect();
    let ema20 = ema(&closes, 20);
    let ema50 = ema(&closes, 50);
    let vsma = sma(&vols, 20);
    let relvol = |j: usize| {
        if vsma[j].is_finite() && vsma[j] > 0.0 && vols[j] > 0.0 {
            vols[j] / vsma[j]
        } else {
            1.0
        }
    };
    let is_ph = |i: usize| i >= k && i + k < n && (i - k..=i + k).all(|j| j == i || bars[j].h < bars[i].h);
    let is_pl = |i: usize| i >= k && i + k < n && (i - k..=i + k).all(|j| j == i || bars[j].l > bars[i].l);

    let mut legs: Vec<Leg> = Vec::new();
    let mut zones: Vec<Zone> = Vec::new();
    let mut trend = vec![0i8; n];
    let mut leg_at: Vec<Option<usize>> = vec![None; n];
    let mut cur_leg: Option<usize> = None;
    let mut cur_trend = 0i8;
    let mut sh: Option<(usize, f64)> = None; // latest confirmed swing high
    let mut sl: Option<(usize, f64)> = None; // latest confirmed swing low
    let mut sh_broken = true;
    let mut sl_broken = true;

    for t in 0..n {
        let a = atr_v[t];
        let ok_a = a.is_finite();
        if t >= k {
            let i = t - k;
            if is_ph(i) {
                if let (Some((_, p)), true) = (sh, ok_a) {
                    if (bars[i].h - p).abs() <= POOL_TOL_ATR * a {
                        zones.push(pool_zone(-1, t, p.min(bars[i].h), p.max(bars[i].h)));
                    }
                }
                sh = Some((i, bars[i].h));
                sh_broken = false;
            }
            if is_pl(i) {
                if let (Some((_, p)), true) = (sl, ok_a) {
                    if (bars[i].l - p).abs() <= POOL_TOL_ATR * a {
                        zones.push(pool_zone(1, t, p.min(bars[i].l), p.max(bars[i].l)));
                    }
                }
                sl = Some((i, bars[i].l));
                sl_broken = false;
            }
        }
        if ok_a {
            let c = bars[t].c;
            let mut broke_up = false;
            if let (Some((_, hp)), false) = (sh, sh_broken) {
                if c > hp {
                    if let Some((li, lp)) = sl {
                        let hmax = (li..=t).map(|j| bars[j].h).fold(f64::MIN, f64::max);
                        if hmax - lp >= d * a {
                            broke_up = true;
                            sh_broken = true;
                            legs.push(Leg { dir: 1, lo: lp, hi: hmax, brk: t });
                            cur_leg = Some(legs.len() - 1);
                            cur_trend = 1;
                            if let Some(j) = (li.saturating_sub(OB_LOOKBACK)..=li).rev().find(|&j| bars[j].c < bars[j].o) {
                                zones.push(Zone {
                                    dir: 1,
                                    pool: false,
                                    act: t,
                                    bounds: [
                                        (bars[j].l, bars[j].h),
                                        (bars[j].l, bars[j].o.max(bars[j].c)),
                                    ],
                                    leg: cur_leg,
                                    fvg: (li + 1..=t).any(|m| m >= 2 && bars[m - 2].h < bars[m].l),
                                    relvol: relvol(j),
                                });
                            }
                        }
                    }
                }
            }
            if let (false, Some((_, lp)), false) = (broke_up, sl, sl_broken) {
                if c < lp {
                    if let Some((hi_i, hp)) = sh {
                        let lmin = (hi_i..=t).map(|j| bars[j].l).fold(f64::MAX, f64::min);
                        if hp - lmin >= d * a {
                            sl_broken = true;
                            legs.push(Leg { dir: -1, lo: lmin, hi: hp, brk: t });
                            cur_leg = Some(legs.len() - 1);
                            cur_trend = -1;
                            if let Some(j) = (hi_i.saturating_sub(OB_LOOKBACK)..=hi_i).rev().find(|&j| bars[j].c > bars[j].o) {
                                zones.push(Zone {
                                    dir: -1,
                                    pool: false,
                                    act: t,
                                    bounds: [
                                        (bars[j].l, bars[j].h),
                                        (bars[j].o.min(bars[j].c), bars[j].h),
                                    ],
                                    leg: cur_leg,
                                    fvg: (hi_i + 1..=t).any(|m| m >= 2 && bars[m - 2].l > bars[m].h),
                                    relvol: relvol(j),
                                });
                            }
                        }
                    }
                }
            }
        }
        trend[t] = cur_trend;
        leg_at[t] = cur_leg;
    }
    Analysis { atr: atr_v, ema20, ema50, trend, legs, leg_at, zones }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{synthetic_15m, Tf};
    use chrono::NaiveDateTime;

    fn bar(i: usize, o: f64, h: f64, l: f64, c: f64) -> Bar {
        let ts = NaiveDateTime::parse_from_str("2020-01-06 09:15:00", "%Y-%m-%d %H:%M:%S").unwrap()
            + chrono::Duration::minutes(15 * i as i64);
        Bar { ts, o, h, l, c, v: 100.0 }
    }

    /// 14 warm-up bars of range 1 (ATR = 1), a swing high at 15, a swing low at 21,
    /// a bearish candle at 20 (the order block), and a displaced break at 24.
    fn fixture() -> Vec<Bar> {
        let mut v: Vec<Bar> = (0..14).map(|i| bar(i, 100.0, 100.5, 99.5, 100.0)).collect();
        v.push(bar(14, 100.0, 100.5, 99.5, 100.0));
        v.push(bar(15, 100.0, 101.0, 99.5, 100.8)); // swing high 101.0
        v.push(bar(16, 100.8, 100.5, 99.5, 100.0));
        v.push(bar(17, 100.0, 100.5, 99.5, 100.0));
        v.push(bar(18, 100.0, 100.5, 99.5, 99.8));
        v.push(bar(19, 99.8, 100.0, 99.5, 99.6));
        v.push(bar(20, 99.6, 99.8, 99.2, 99.4)); // bearish: the order block
        v.push(bar(21, 97.2, 98.0, 97.0, 97.9)); // swing low 97.0 (bullish candle)
        v.push(bar(22, 97.9, 98.6, 97.5, 98.4));
        v.push(bar(23, 98.4, 99.4, 98.2, 99.2));
        v.push(bar(24, 99.2, 101.8, 99.0, 101.5)); // displaced close above 101.0
        v
    }

    #[test]
    fn pivots_bos_ob_and_fvg_on_fixture() {
        let s = Series::new(false, Tf::M15, fixture());
        let an = analyze(&s, 2, 1.0);
        assert_eq!(an.legs.len(), 1);
        let leg = &an.legs[0];
        assert_eq!((leg.dir, leg.brk), (1, 24));
        assert!((leg.lo - 97.0).abs() < 1e-12 && (leg.hi - 101.8).abs() < 1e-12);
        assert_eq!(an.zones.len(), 1);
        let z = &an.zones[0];
        assert!(!z.pool && z.dir == 1 && z.act == 24);
        // OB = last bearish candle at or before the swing low (bar 20)
        assert_eq!(z.bounds[0], (99.2, 99.8));
        assert_eq!(z.bounds[1], (99.2, 99.6));
        // bar 24 low (99.0) is above bar 22 high (98.6): bullish FVG in the leg
        assert!(z.fvg);
        assert_eq!(an.trend[24], 1);
        assert_eq!(an.trend[23], 0);
    }

    #[test]
    fn fib_levels_and_probability_bounds() {
        let leg = Leg { dir: 1, lo: 100.0, hi: 200.0, brk: 0 };
        let mu = fib_levels(&leg);
        assert!((mu[2] - 138.2).abs() < 1e-9); // 0.618 retracement from the high
        // peak at a level inside the interval is 1
        assert!((pf_max(&mu, 5.0, 130.0, 140.0) - 1.0).abs() < 1e-12);
        // interval entirely above 138.2 by 1 sigma gives exp(-1/2)
        let p = pf_max(&[138.2], 1.0, 139.2, 150.0);
        assert!((p - (-0.5f64).exp()).abs() < 1e-12);
        assert_eq!(pf_max(&mu, 0.0, 0.0, 1.0), 0.0);
    }

    #[test]
    fn detector_outputs_do_not_depend_on_future_bars() {
        let full = synthetic_15m(7, 120, 0.004);
        let t_cut = 1100;
        let sf = Series::new(false, Tf::M15, full.clone());
        let st = Series::new(false, Tf::M15, full[..=t_cut].to_vec());
        for (k, d) in [(2usize, 1.0f64), (3, 1.5)] {
            let a = analyze(&sf, k, d);
            let b = analyze(&st, k, d);
            for t in 0..=t_cut {
                assert_eq!(a.atr[t].to_bits(), b.atr[t].to_bits(), "atr {t}");
                assert_eq!(a.ema50[t].to_bits(), b.ema50[t].to_bits(), "ema50 {t}");
                assert_eq!(a.trend[t], b.trend[t], "trend {t}");
                assert_eq!(a.leg_at[t], b.leg_at[t], "leg {t}");
            }
            let za: Vec<&Zone> = a.zones.iter().filter(|z| z.act <= t_cut).collect();
            let zb: Vec<&Zone> = b.zones.iter().collect();
            assert_eq!(za.len(), zb.len());
            for (x, y) in za.iter().zip(zb.iter()) {
                assert_eq!((x.dir, x.act, x.pool, x.leg, x.fvg), (y.dir, y.act, y.pool, y.leg, y.fvg));
                assert_eq!(x.bounds, y.bounds);
            }
            let la: Vec<&Leg> = a.legs.iter().filter(|l| l.brk <= t_cut).collect();
            assert_eq!(la.len(), b.legs.len());
        }
    }
}
