//! Touch events for HPZ and the baselines. A zone (OB or pool) yields its first touch only.
use crate::data::{Bar, Series};
use crate::detect::{fib_levels, is_sweep, pf_max, Analysis};
use serde::Serialize;

pub const NK: usize = 7;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Kind {
    Hpz = 0,
    HpzOb = 1,
    HpzFvg = 2,
    HpzVol = 3,
    Fib = 4,
    Smc = 5,
    Ma = 6,
}

pub const KINDS: [Kind; NK] = [Kind::Hpz, Kind::HpzOb, Kind::HpzFvg, Kind::HpzVol, Kind::Fib, Kind::Smc, Kind::Ma];

impl Kind {
    pub fn label(self) -> &'static str {
        match self {
            Kind::Hpz => "HPZ (OB/pool x Fib)",
            Kind::HpzOb => "HPZ (OB x Fib)",
            Kind::HpzFvg => "HPZ (OB x Fib, FVG)",
            Kind::HpzVol => "HPZ (volume-weighted)",
            Kind::Fib => "Fib-only",
            Kind::Smc => "SMC-only (OB)",
            Kind::Ma => "MA20/50 touch",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Event {
    pub bar: usize,
    pub dir: i8,
    pub kind: Kind,
    pub zlo: f64,
    pub zhi: f64,
    pub leg: Option<usize>,
}

#[derive(Clone, Copy, Debug)]
pub struct Zp {
    pub variant: usize,
    pub n: usize,
    pub c: f64,
    pub tau: f64,
}

fn touches(b: &Bar, lo: f64, hi: f64) -> bool {
    b.h >= lo && b.l <= hi
}

/// All touch events for one zone parameter set, sorted by bar.
pub fn generate(s: &Series, an: &Analysis, zp: Zp) -> Vec<Event> {
    let bars = &s.bars;
    let n = bars.len();
    let mut out = Vec::new();

    for z in &an.zones {
        let (lo, hi) = z.bounds[zp.variant];
        let last = (z.act + zp.n).min(n - 1);
        for t in (z.act + 1)..=last {
            let b = &bars[t];
            if (z.dir > 0 && b.c < lo) || (z.dir < 0 && b.c > hi) {
                break; // invalidated by a close through the zone
            }
            if !touches(b, lo, hi) {
                continue;
            }
            let a = an.atr[t];
            if !a.is_finite() {
                break;
            }
            let leg = if z.pool { an.leg_at[t] } else { z.leg };
            let pf = match leg {
                Some(li) => pf_max(&fib_levels(&an.legs[li]), zp.c * a, b.l.max(lo), b.h.min(hi)),
                None => 0.0,
            };
            let mk = |kind: Kind, leg: Option<usize>| Event { bar: t, dir: z.dir, kind, zlo: lo, zhi: hi, leg };
            if !z.pool {
                out.push(mk(Kind::Smc, z.leg));
            }
            if pf >= zp.tau {
                out.push(mk(Kind::Hpz, leg));
                if !z.pool {
                    out.push(mk(Kind::HpzOb, z.leg));
                    if z.fvg {
                        out.push(mk(Kind::HpzFvg, z.leg));
                    }
                }
            }
            if pf * z.relvol.min(1.0) >= zp.tau {
                out.push(mk(Kind::HpzVol, leg));
            }
            break; // one touch per zone
        }
    }

    for (li, leg) in an.legs.iter().enumerate() {
        let next = an.legs.get(li + 1).map_or(n, |x| x.brk);
        let last = (leg.brk + zp.n).min(next.saturating_sub(1)).min(n - 1);
        let mu = fib_levels(leg);
        for t in (leg.brk + 1)..=last {
            let b = &bars[t];
            if (leg.dir > 0 && b.c < leg.lo) || (leg.dir < 0 && b.c > leg.hi) {
                break;
            }
            let a = an.atr[t];
            if !a.is_finite() {
                break;
            }
            let sig = zp.c * a;
            if pf_max(&mu, sig, b.l, b.h) >= zp.tau {
                let w = sig * (2.0 * (1.0 / zp.tau).ln()).sqrt();
                let mn = mu.iter().cloned().fold(f64::MAX, f64::min) - w;
                let mx = mu.iter().cloned().fold(f64::MIN, f64::max) + w;
                out.push(Event { bar: t, dir: leg.dir, kind: Kind::Fib, zlo: mn, zhi: mx, leg: Some(li) });
                break;
            }
        }
    }

    for t in 1..n {
        let tr = an.trend[t];
        if tr == 0 {
            continue;
        }
        let (e20, e50) = (an.ema20[t], an.ema50[t]);
        let now = [e20, e50].into_iter().find(|&e| touches(&bars[t], e, e));
        let prev = [an.ema20[t - 1], an.ema50[t - 1]].iter().any(|&e| touches(&bars[t - 1], e, e));
        if let (Some(e), false) = (now, prev) {
            out.push(Event { bar: t, dir: tr, kind: Kind::Ma, zlo: e, zhi: e, leg: an.leg_at[t] });
        }
    }

    out.sort_by_key(|e| (e.bar, e.kind as u8));
    out
}

/// Number of liquidity sweeps of pools (N-bar life, variant A). Diagnostic only.
pub fn sweep_count(s: &Series, an: &Analysis, n: usize) -> usize {
    let bars = &s.bars;
    let last_idx = bars.len() - 1;
    let mut c = 0;
    for z in an.zones.iter().filter(|z| z.pool) {
        let (lo, hi) = z.bounds[0];
        for t in (z.act + 1)..=(z.act + n).min(last_idx) {
            let b = &bars[t];
            if (z.dir > 0 && b.c < lo) || (z.dir < 0 && b.c > hi) {
                break;
            }
            if is_sweep(b, z.dir, lo, hi) {
                c += 1;
            }
        }
    }
    c
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{synthetic_15m, Tf};
    use crate::detect::analyze;

    #[test]
    fn events_do_not_depend_on_future_bars() {
        let full = synthetic_15m(11, 200, 0.004);
        let t_cut = 2400;
        let sf = Series::new(false, Tf::M15, full.clone());
        let st = Series::new(false, Tf::M15, full[..=t_cut].to_vec());
        let zp = Zp { variant: 0, n: 100, c: 0.5, tau: 0.5 };
        let ea = generate(&sf, &analyze(&sf, 2, 1.0), zp);
        let eb = generate(&st, &analyze(&st, 2, 1.0), zp);
        let fa: Vec<(usize, i8, Kind)> = ea.iter().filter(|e| e.bar <= t_cut).map(|e| (e.bar, e.dir, e.kind)).collect();
        let fb: Vec<(usize, i8, Kind)> = eb.iter().map(|e| (e.bar, e.dir, e.kind)).collect();
        assert!(!fb.is_empty());
        assert_eq!(fa, fb);
    }

    #[test]
    fn hpz_is_subset_of_smc_touches() {
        let full = synthetic_15m(5, 150, 0.004);
        let s = Series::new(false, Tf::M15, full);
        let an = analyze(&s, 2, 1.0);
        let ev = generate(&s, &an, Zp { variant: 0, n: 100, c: 0.5, tau: 0.5 });
        let smc: Vec<usize> = ev.iter().filter(|e| e.kind == Kind::Smc).map(|e| e.bar).collect();
        for e in ev.iter().filter(|e| e.kind == Kind::HpzOb) {
            assert!(smc.contains(&e.bar));
        }
    }
}
