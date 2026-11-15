//! Causal indicators: Wilder ATR, EMA, SMA. Values before warm-up are NaN.
use crate::data::Bar;

pub fn atr(bars: &[Bar], n: usize) -> Vec<f64> {
    let len = bars.len();
    let mut out = vec![f64::NAN; len];
    if len <= n {
        return out;
    }
    let mut tr = vec![0.0; len];
    for i in 1..len {
        let p = bars[i - 1].c;
        let b = &bars[i];
        tr[i] = (b.h - b.l).max((b.h - p).abs()).max((b.l - p).abs());
    }
    let nf = n as f64;
    let mut a = tr[1..=n].iter().sum::<f64>() / nf;
    out[n] = a;
    for i in n + 1..len {
        a = (a * (nf - 1.0) + tr[i]) / nf;
        out[i] = a;
    }
    out
}

pub fn ema(x: &[f64], n: usize) -> Vec<f64> {
    let mut out = vec![f64::NAN; x.len()];
    if x.len() < n {
        return out;
    }
    let alpha = 2.0 / (n as f64 + 1.0);
    let mut e = x[..n].iter().sum::<f64>() / n as f64;
    out[n - 1] = e;
    for i in n..x.len() {
        e = alpha * x[i] + (1.0 - alpha) * e;
        out[i] = e;
    }
    out
}

pub fn sma(x: &[f64], n: usize) -> Vec<f64> {
    let mut out = vec![f64::NAN; x.len()];
    let mut s = 0.0;
    for i in 0..x.len() {
        s += x[i];
        if i >= n {
            s -= x[i - n];
        }
        if i + 1 >= n {
            out[i] = s / n as f64;
        }
    }
    out
}
