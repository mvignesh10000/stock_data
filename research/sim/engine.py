#!/usr/bin/env python3
"""Flexible NIFTY options simulator (multi-day positions, adjustments, signal-driven entries).

Execution model = opt_engine / AlgoTest (validated in research/sim/validate.py):
  * time "HH:MM" means the close of the 1-min bar that starts at HH:MM-1 (minute index m = HH*60+MM-556)
  * market orders fill at that close +/- slip, slip = max(0.5 % x price, Rs 0.10)
  * leg stops / targets are checked on the bar high/low BEFORE the strategy runs that minute (pessimistic);
    stop fill = max(trigger, bar open) x 1.01 + slip (shorts), mirrored for longs
  * positions may be held overnight; an expiring contract still open after its expiry day's last bar is settled at
    that bar's close (exchange settles on the last-30-min average, close is a good proxy)
  * charges at today's rates (brokerage Rs 20/order, STT 0.15 % sells, NSE 0.03503 %, SEBI, stamp 0.003 % buys, GST 18 %)
  * margin (approximate SPAN): worst loss over spot shocks +/-9.3 % (7 points, options repriced at intrinsic + 1.5x time value)
    + 2 % exposure on short notional + 2 % ELM on short legs on their expiry day; recorded per day (max over the day)

Strategy API: subclass Strategy and override on_day(ctx) and/or on_minute(ctx, m). ctx gives:
  ctx.date, ctx.f (features dict for the day), ctx.spot(m), ctx.atm(m), ctx.expiries (sorted, rank order), ctx.tdte(expiry)
  ctx.px(expiry, strike, opt, m) -> close or None; ctx.strike_by_premium(expiry, opt, target, m, otm=True)
  ctx.open(expiry, strike, opt, side, lots, m, tag="", sl=None, tgt=None) -> leg or None   (sl/tgt = absolute premium levels)
  ctx.close(leg, m, why), ctx.close_all(m, why), ctx.legs (open legs), ctx.mtm(m) (Rs, incl. realised today & open, before charges)
"""
import math
import numpy as np

LOT = 65
IDX = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:5]) - 556


def slip(p):
    return max(0.005 * p, 0.10)


def charges(side, price, qty):
    t = price * qty
    brok, exch, sebi = 20.0, t * 0.0003503, t * 1e-6
    return brok + (t * 0.0015 if side == "S" else 0) + exch + sebi + (t * 0.00003 if side == "B" else 0) + 0.18 * (brok + exch + sebi)


class Leg:
    __slots__ = ("expiry", "strike", "opt", "side", "lots", "entry", "entry_date", "entry_m", "exit", "exit_date", "exit_m", "why", "sl", "tgt", "tag", "last")

    def __init__(self, **k):
        for s in self.__slots__:
            setattr(self, s, k.get(s))

    @property
    def sign(self):
        return -1 if self.side == "S" else 1

    def pnl(self, price):
        return self.sign * (price - self.entry) * self.lots * LOT


class Strategy:
    name = "base"

    def on_day(self, ctx):
        pass

    def on_minute(self, ctx, m):
        pass

    def on_stop(self, ctx, legs, m):
        pass


class Ctx:
    def __init__(self, days, features, dates):
        self.days, self.features, self.dates = days, features, dates
        self.didx = {d: i for i, d in enumerate(dates)}
        self.legs, self.closed, self.cost = [], [], 0.0
        self.day = None

    # ---------------- market
    def _chain(self, expiry):
        return self.day["chains"].get(expiry)

    def spot(self, m):
        v = self.day["spot"][m, 3]
        return None if np.isnan(v) else float(v)

    def atm(self, m, step=50):
        s = self.spot(m)
        return None if s is None else int(round(s / step) * step)

    def tdte(self, expiry):
        i = self.didx[self.date]
        j = np.searchsorted(self.dates, expiry, side="right")
        n = j - i - 1
        if expiry > self.dates[-1]:  # beyond the data: count weekdays
            import datetime as dt
            a = dt.date(self.dates[-1] // 10000, self.dates[-1] // 100 % 100, self.dates[-1] % 100)
            b = dt.date(expiry // 10000, expiry // 100 % 100, expiry % 100)
            n += sum(1 for k in range(1, (b - a).days + 1) if (a + dt.timedelta(k)).weekday() < 5)
        return max(n, 0)

    def bar(self, expiry, strike, opt, m):
        ch = self._chain(expiry)
        if ch is None:
            return None
        i = np.searchsorted(ch["strikes"], strike)
        if i >= len(ch["strikes"]) or ch["strikes"][i] != strike:
            return None
        t = 0 if opt == "CE" else 1
        c = ch["c"][t, i, m]
        if np.isnan(c):
            return None
        return float(ch["o"][t, i, m]), float(ch["h"][t, i, m]), float(c)

    def px(self, expiry, strike, opt, m):
        b = self.bar(expiry, strike, opt, m)
        return None if b is None else b[2]

    def oi(self, expiry, opt, m):
        ch = self._chain(expiry)
        return None if ch is None else (ch["strikes"], ch["oi"][0 if opt == "CE" else 1, :, m])

    def strike_by_premium(self, expiry, opt, target, m, otm=True):
        ch = self._chain(expiry)
        if ch is None:
            return None
        s = self.spot(m)
        t = 0 if opt == "CE" else 1
        c = ch["c"][t, :, m]
        ks = ch["strikes"]
        ok = ~np.isnan(c)
        if otm:
            ok &= (ks > s) if opt == "CE" else (ks < s)
        if not ok.any():
            return None
        i = np.argmin(np.where(ok, np.abs(c - target), np.inf))
        return int(ks[i])

    # ---------------- orders
    def open(self, expiry, strike, opt, side, lots, m, tag="", sl=None, tgt=None):
        p = self.px(expiry, strike, opt, m)
        if p is None or p <= 0:
            return None
        fill = p + slip(p) if side == "B" else max(p - slip(p), 0.05)
        self.cost += charges(side, fill, lots * LOT)
        leg = Leg(expiry=expiry, strike=strike, opt=opt, side=side, lots=lots, entry=fill, entry_date=self.date, entry_m=m,
                  sl=sl, tgt=tgt, tag=tag, last=fill)
        self.legs.append(leg)
        return leg

    def _fill_close(self, leg, price, m, why, stop=False):
        side = "B" if leg.side == "S" else "S"
        if stop:  # stop fills already carry the 1 % stop slippage; add one tick like opt_engine's min_slippage_pts
            fill = price + 0.10 if side == "B" else max(price - 0.10, 0.05)
        else:
            fill = price + slip(price) if side == "B" else max(price - slip(price), 0.05)
        self.cost += charges(side, fill, leg.lots * LOT)
        leg.exit, leg.exit_date, leg.exit_m, leg.why = fill, self.date, m, why
        self.legs.remove(leg)
        self.closed.append(leg)
        self.realised_today += leg.pnl(fill)

    def close(self, leg, m, why="signal"):
        p = self.px(leg.expiry, leg.strike, leg.opt, m)
        self._fill_close(leg, p if p is not None else leg.last, m, why)

    def close_all(self, m, why="exit"):
        for leg in list(self.legs):
            self.close(leg, m, why)

    def mtm(self, m):
        """Rs P&L since today's open of the book: realised today + open legs vs their value at the previous mark."""
        u = 0.0
        for leg in self.legs:
            p = self.px(leg.expiry, leg.strike, leg.opt, m)
            u += leg.pnl(p if p is not None else leg.last)
        return self.realised_today + u - self.open_value_start

    def open_pnl(self, m):
        return sum(leg.pnl(p if (p := self.px(leg.expiry, leg.strike, leg.opt, m)) is not None else leg.last) for leg in self.legs)

    # ---------------- margin (approximate SPAN)
    def margin(self, m):
        s = self.spot(m)
        if s is None or not self.legs:
            return 0.0
        worst = 0.0
        for sh in (-0.093, -0.062, -0.031, 0.0, 0.031, 0.062, 0.093):
            S = s * (1 + sh)
            loss = 0.0
            for leg in self.legs:
                p = self.px(leg.expiry, leg.strike, leg.opt, m) or leg.last
                intr = max(0.0, (s - leg.strike) if leg.opt == "CE" else (leg.strike - s))
                tv = max(p - intr, 0.0)
                intr2 = max(0.0, (S - leg.strike) if leg.opt == "CE" else (leg.strike - S))
                loss -= leg.sign * (intr2 + 1.5 * tv - p) * leg.lots * LOT
            worst = max(worst, loss)
        shorts = sum(leg.lots for leg in self.legs if leg.side == "S")
        exp_day = sum(leg.lots for leg in self.legs if leg.side == "S" and leg.expiry == self.date)
        return worst + 0.02 * s * LOT * shorts + 0.02 * s * LOT * exp_day


def run(strategy, days, features, date_from=0, date_to=99999999):
    """-> dict(daily=[(date, net Rs, margin Rs, n_open_legs)], trades=[Leg...])"""
    dates = np.array(sorted(days), dtype=np.int64)
    ctx = Ctx(days, features, dates)
    daily = []
    for d in dates:
        if d < date_from or d > date_to:
            continue
        ctx.date, ctx.day, ctx.f = int(d), days[int(d)], features.get(int(d), {})
        ctx.expiries = sorted(e for e in ctx.day["chains"] if e >= d)
        ctx.realised_today, cost0, mmax = 0.0, ctx.cost, 0.0
        # value of carried positions at yesterday's last mark
        ctx.open_value_start = sum(leg.pnl(leg.last) for leg in ctx.legs)
        strategy.on_day(ctx)
        last_m = 0
        for m in range(375):
            if ctx.spot(m) is None:
                continue
            last_m = m
            # stops / targets on this bar (pessimistic: stop before target); strategies may react to a stop
            # (on_stop) and moved stops are re-checked on the same bar, like opt_engine's pessimistic same-bar rule
            for _pass in range(2):
                fired = []
                for leg in list(ctx.legs):
                    b = ctx.bar(leg.expiry, leg.strike, leg.opt, m)
                    if b is None or (leg.entry_date == d and leg.entry_m == m):
                        continue
                    o, h, c = b
                    if leg.side == "S":
                        if leg.sl is not None and h >= leg.sl:
                            ctx._fill_close(leg, max(leg.sl, o) * 1.01, m, "SL", stop=True)
                            fired.append(leg)
                            continue
                        if leg.tgt is not None and min(o, c) <= leg.tgt:
                            ctx._fill_close(leg, min(leg.tgt, o), m, "TGT")
                            continue
                    else:
                        if leg.sl is not None and min(o, c) <= leg.sl:
                            ctx._fill_close(leg, min(leg.sl, o) * 0.99, m, "SL", stop=True)
                            fired.append(leg)
                            continue
                        if leg.tgt is not None and h >= leg.tgt:
                            ctx._fill_close(leg, max(leg.tgt, o), m, "TGT")
                            continue
                    leg.last = c
                if not fired:
                    break
                strategy.on_stop(ctx, fired, m)
            strategy.on_minute(ctx, m)
            if ctx.legs and m % 15 == 0:
                mmax = max(mmax, ctx.margin(m))
        # settle legs whose expiry is today
        for leg in list(ctx.legs):
            if leg.expiry <= d:
                ctx.close(leg, last_m, "expiry")
        for leg in ctx.legs:
            p = ctx.px(leg.expiry, leg.strike, leg.opt, last_m)
            if p is not None:
                leg.last = p
        open_value_end = sum(leg.pnl(leg.last) for leg in ctx.legs)
        net = ctx.realised_today + open_value_end - ctx.open_value_start - (ctx.cost - cost0)
        daily.append((int(d), net, mmax, len(ctx.legs)))
    return {"daily": daily, "trades": ctx.closed + ctx.legs}
