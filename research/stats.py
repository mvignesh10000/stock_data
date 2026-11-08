"""Statistics used by the discovery loop and the report.

* Monte-Carlo drawdown (AlgoTest-style: 10,000 reshuffles of the trade-day P&L sequence).
* Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) -- probability that the observed Sharpe is
  > 0 after correcting for the number of configurations tried (selection bias), skew and kurtosis.
* Probabilistic Sharpe Ratio.
"""
import math, random
from statistics import NormalDist

N = NormalDist()


def max_dd(seq):
    c = p = d = 0.0
    for x in seq:
        c += x
        p = max(p, c)
        d = max(d, p - c)
    return d


def monte_carlo_dd(pnl, n=10000, pct=95, seed=1):
    pnl = [x for x in pnl if x != 0]
    if not pnl:
        return 0.0
    rng = random.Random(seed)
    dds = []
    for _ in range(n):
        s = pnl[:]
        rng.shuffle(s)
        dds.append(max_dd(s))
    dds.sort()
    return dds[min(len(dds) - 1, int(len(dds) * pct / 100))]


def moments(x):
    n = len(x)
    m = sum(x) / n
    v = sum((a - m) ** 2 for a in x) / (n - 1)
    sd = math.sqrt(v) if v > 0 else 0.0
    if sd == 0:
        return m, 0.0, 0.0, 3.0
    sk = sum((a - m) ** 3 for a in x) / n / sd ** 3
    ku = sum((a - m) ** 4 for a in x) / n / sd ** 4
    return m, sd, sk, ku


def psr(x, sr_star=0.0):
    """Probabilistic Sharpe ratio of per-period returns x against benchmark per-period SR sr_star."""
    m, sd, sk, ku = moments(x)
    if sd == 0:
        return 0.0
    sr = m / sd
    T = len(x)
    den = math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr * sr))
    return N.cdf((sr - sr_star) * math.sqrt(T - 1) / den)


def deflated_sharpe(x, n_trials, var_sr_trials):
    """x: per-period P&L of the selected strategy; n_trials: number of independent configs tried;
    var_sr_trials: variance of per-period Sharpe ratios across the trials."""
    g = 0.5772156649
    n_trials = max(2, n_trials)
    sr0 = math.sqrt(max(var_sr_trials, 0.0)) * ((1 - g) * N.inv_cdf(1 - 1 / n_trials) + g * N.inv_cdf(1 - 1 / (n_trials * math.e)))
    return psr(x, sr0), sr0
