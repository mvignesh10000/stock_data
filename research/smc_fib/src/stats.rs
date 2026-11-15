//! Wilson intervals, block bootstrap, deflated Sharpe ratio, moments.
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use statrs::distribution::{ContinuousCDF, Normal};

const Z95: f64 = 1.959_963_984_540_054;
const EULER_GAMMA: f64 = 0.577_215_664_901_532_9;

/// (p, lower, upper) Wilson 95 % interval for k successes in n trials.
pub fn wilson(k: u64, n: u64) -> (f64, f64, f64) {
    if n == 0 {
        return (f64::NAN, f64::NAN, f64::NAN);
    }
    let nf = n as f64;
    let p = k as f64 / nf;
    let z2 = Z95 * Z95;
    let den = 1.0 + z2 / nf;
    let c = (p + z2 / (2.0 * nf)) / den;
    let h = Z95 * (p * (1.0 - p) / nf + z2 / (4.0 * nf * nf)).sqrt() / den;
    (p, c - h, c + h)
}

pub fn mean(x: &[f64]) -> f64 {
    if x.is_empty() {
        0.0
    } else {
        x.iter().sum::<f64>() / x.len() as f64
    }
}

pub fn sample_var(x: &[f64]) -> f64 {
    if x.len() < 2 {
        return 0.0;
    }
    let m = mean(x);
    x.iter().map(|v| (v - m).powi(2)).sum::<f64>() / (x.len() - 1) as f64
}

/// Per-period Sharpe (not annualised).
pub fn sharpe_daily(x: &[f64]) -> f64 {
    let sd = sample_var(x).sqrt();
    if sd > 0.0 {
        mean(x) / sd
    } else {
        0.0
    }
}

/// (skewness, raw kurtosis) of a sample; normal kurtosis is 3.
pub fn moments(x: &[f64]) -> (f64, f64) {
    let n = x.len() as f64;
    if x.len() < 4 {
        return (0.0, 3.0);
    }
    let m = mean(x);
    let s2 = x.iter().map(|v| (v - m).powi(2)).sum::<f64>() / n;
    if s2 <= 0.0 {
        return (0.0, 3.0);
    }
    let m3 = x.iter().map(|v| (v - m).powi(3)).sum::<f64>() / n;
    let m4 = x.iter().map(|v| (v - m).powi(4)).sum::<f64>() / n;
    (m3 / s2.powf(1.5), m4 / (s2 * s2))
}

/// 95 % interval of the mean from a moving-block bootstrap (blocks of `block` consecutive values).
pub fn block_bootstrap_ci(x: &[f64], block: usize, reps: usize, seed: u64) -> (f64, f64) {
    let n = x.len();
    if n < block || n == 0 {
        return (f64::NAN, f64::NAN);
    }
    let mut rng = ChaCha8Rng::seed_from_u64(seed);
    let nb = n.div_ceil(block);
    let mut means = Vec::with_capacity(reps);
    for _ in 0..reps {
        let mut s = 0.0;
        let mut cnt = 0;
        for _ in 0..nb {
            let st = rng.gen_range(0..=n - block);
            for v in &x[st..st + block] {
                if cnt < n {
                    s += v;
                    cnt += 1;
                }
            }
        }
        means.push(s / n as f64);
    }
    means.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let lo = means[(0.025 * reps as f64) as usize];
    let hi = means[((0.975 * reps as f64) as usize).min(reps - 1)];
    (lo, hi)
}

/// One-sided p-value: share of random runs at or above the observed statistic (with +1 correction).
pub fn pvalue_ge(samples: &[f64], obs: f64) -> f64 {
    let k = samples.iter().filter(|&&s| s >= obs).count();
    (k as f64 + 1.0) / (samples.len() as f64 + 1.0)
}

/// Deflated Sharpe ratio (Bailey & Lopez de Prado). `sr` and `sr_var` are per-period.
/// Returns (SR0 = expected maximum Sharpe over `trials`, DSR probability).
pub fn dsr(sr: f64, sr_var: f64, trials: usize, t: usize, skew: f64, kurt: f64) -> (f64, f64) {
    let nd = Normal::new(0.0, 1.0).unwrap();
    let n = trials as f64;
    let sr0 = sr_var.max(0.0).sqrt()
        * ((1.0 - EULER_GAMMA) * nd.inverse_cdf(1.0 - 1.0 / n)
            + EULER_GAMMA * nd.inverse_cdf(1.0 - 1.0 / (n * std::f64::consts::E)));
    let denom = (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr).max(1e-12).sqrt();
    let z = (sr - sr0) * ((t as f64 - 1.0).max(1.0)).sqrt() / denom;
    (sr0, nd.cdf(z))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wilson_matches_known_value() {
        // 8 of 10 successes: Wilson 95 % is about (0.490, 0.943)
        let (p, lo, hi) = wilson(8, 10);
        assert!((p - 0.8).abs() < 1e-12);
        assert!((lo - 0.4902).abs() < 1e-3 && (hi - 0.9433).abs() < 1e-3);
    }

    #[test]
    fn dsr_deflates_with_more_trials() {
        let (sr0_small, _) = dsr(0.05, 0.01, 2, 1000, 0.0, 3.0);
        let (sr0_big, p_big) = dsr(0.05, 0.01, 64, 1000, 0.0, 3.0);
        assert!(sr0_big > sr0_small);
        assert!(p_big < 0.5 + 1e-9 || 0.05 > sr0_big);
    }

    #[test]
    fn bootstrap_interval_brackets_mean() {
        let x: Vec<f64> = (0..500).map(|i| if i % 3 == 0 { 1.0 } else { -0.2 }).collect();
        let m = mean(&x);
        let (lo, hi) = block_bootstrap_ci(&x, 10, 2000, 42);
        assert!(lo < m && m < hi);
    }
}
