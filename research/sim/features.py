#!/usr/bin/env python3
"""Daily feature table (only information available at 09:20 of that day) -> data/sim/features.parquet

Columns: date, weekday, expiry, tdte, spot (09:20), prev_close, gap_pct, or5_pct (09:15-09:19 range), prev_ret_pct,
prev_range_pct, rv5, rv20 (close-to-close, annualised %), vix, vix_chg (VIX open vs previous close, 2022+),
straddle (ATM CE+PE at 09:20, current expiry), iv (annualised %, Brenner-Subrahmanyam: straddle = 0.8 S sigma sqrt(T),
T in trading minutes to expiry / (252 x 375)), iv_next (next expiry, same method), iv_rv5, iv_rv20, iv_rank (percentile of
iv among the previous 50 observations in the same tdte bucket min(tdte, 4), about one year), pcr (put OI / call OI, strikes within +/-2 % of spot,
current expiry, at 09:20), pcr_chg, maxpain_pct (max-pain strike vs spot, %), ce_wall_pct / pe_wall_pct (strike with the
largest call OI above / put OI below spot, % distance).
"""
import math, os, sys
import numpy as np
import polars as pl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
from engine import Ctx

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
M = 4  # 09:20


def main():
    days = store.load()
    dates = np.array(sorted(days), dtype=np.int64)
    ctx = Ctx(days, {}, dates)
    vix = pl.read_parquet(f"{ROOT}/data/upstox/index/VIX_1min.parquet").with_columns(pl.col("ts").dt.strftime("%Y%m%d").cast(pl.Int64).alias("d"))
    vo = dict(vix.group_by("d").agg(pl.col("open").first()).iter_rows())
    vc = dict(vix.group_by("d").agg(pl.col("close").last()).iter_rows())
    rows, closes = [], []
    prev = None
    for d in dates:
        d = int(d)
        day = days[d]
        ctx.date, ctx.day = d, day
        sp = day["spot"]
        s920 = ctx.spot(M)
        last = sp[~np.isnan(sp[:, 3])]
        close = float(last[-1, 3]) if len(last) else None
        r = {"date": d, "weekday": (int(str(d)[:4]) and __import__("datetime").date(d // 10000, d // 100 % 100, d % 100).weekday()), "spot": s920}
        exps = sorted(e for e in day["chains"] if e >= d)
        if not exps or s920 is None:
            closes.append(close)
            prev = (d, close, sp)
            continue
        e0 = exps[0]
        r["expiry"], r["tdte"] = e0, ctx.tdte(e0)
        if prev and prev[1]:
            pc = prev[1]
            r["prev_close"] = pc
            r["gap_pct"] = (float(sp[0, 0]) / pc - 1) * 100 if not np.isnan(sp[0, 0]) else None
            psp = prev[2][~np.isnan(prev[2][:, 3])]
            if len(psp):
                r["prev_ret_pct"] = (pc / float(psp[0, 0]) - 1) * 100
                r["prev_range_pct"] = (float(np.nanmax(psp[:, 1])) - float(np.nanmin(psp[:, 2]))) / pc * 100
        r["or5_pct"] = (float(np.nanmax(sp[:M + 1, 1])) - float(np.nanmin(sp[:M + 1, 2]))) / s920 * 100
        cl = [c for c in closes if c]
        for n in (5, 20):
            if len(cl) > n:
                lr = np.diff(np.log(cl[-(n + 1):]))
                r[f"rv{n}"] = float(np.std(lr, ddof=1) * math.sqrt(252) * 100)
        if d in vo:
            r["vix"] = float(vo[d])
            pd_ = prev[0] if prev else None
            if pd_ in vc:
                r["vix_chg"] = float(vo[d]) - float(vc[pd_])

        def iv_of(e):
            k = ctx.atm(M)
            c, p = ctx.px(e, k, "CE", M), ctx.px(e, k, "PE", M)
            if c is None or p is None:
                return None, None
            T = ((375 - M - 1) + ctx.tdte(e) * 375) / (252 * 375)
            st = c + p
            return st, st / (0.8 * s920 * math.sqrt(T)) * 100

        r["straddle"], r["iv"] = iv_of(e0)
        if len(exps) > 1:
            r["iv_next"] = iv_of(exps[1])[1]
        if r.get("iv") and r.get("rv5"):
            r["iv_rv5"] = r["iv"] / r["rv5"]
        if r.get("iv") and r.get("rv20"):
            r["iv_rv20"] = r["iv"] / r["rv20"]
        # OI features (current expiry, 09:20)
        ks, oc = ctx.oi(e0, "CE", M)
        _, op = ctx.oi(e0, "PE", M)
        if ks is not None:
            band = np.abs(ks - s920) <= 0.02 * s920
            sc, spp = np.nansum(oc[band]), np.nansum(op[band])
            if sc > 0:
                r["pcr"] = float(spp / sc)
            ok = ~np.isnan(oc) & ~np.isnan(op)
            if ok.sum() > 5:
                K = ks[ok].astype(float)
                pain = [np.sum(oc[ok] * np.maximum(0, x - K)) + np.sum(op[ok] * np.maximum(0, K - x)) for x in K]
                r["maxpain_pct"] = (K[int(np.argmin(pain))] / s920 - 1) * 100
                up, dn = (K > s920), (K < s920)
                if up.any():
                    r["ce_wall_pct"] = (K[up][int(np.argmax(oc[ok][up]))] / s920 - 1) * 100
                if dn.any():
                    r["pe_wall_pct"] = (K[dn][int(np.argmax(op[ok][dn]))] / s920 - 1) * 100
        rows.append(r)
        closes.append(close)
        prev = (d, close, sp)
    df = pl.DataFrame(rows, infer_schema_length=None).sort("date")
    df = df.with_columns((pl.col("pcr") - pl.col("pcr").shift(1)).alias("pcr_chg"))
    # IV rank vs previous 250 days in the same tdte bucket (no look-ahead)
    ivr = []
    hist = {}
    for d, iv, t in df.select("date", "iv", "tdte").iter_rows():
        b = min(t or 0, 4)
        h = hist.setdefault(b, [])
        ivr.append(None if iv is None or len(h) < 20 else float(np.mean(np.array(h[-50:]) < iv) * 100))
        if iv is not None:
            h.append(iv)
    df = df.with_columns(pl.Series("iv_rank", ivr, dtype=pl.Float64))
    df.write_parquet(f"{ROOT}/data/sim/features.parquet")
    print(df.shape)
    print(df.select(pl.all().exclude("date", "expiry", "weekday").is_not_null().mean().round(2)).to_dicts()[0])
    print(df.select("iv", "rv5", "rv20", "vix", "iv_rv5", "pcr", "maxpain_pct").describe())


def load():
    df = pl.read_parquet(f"{ROOT}/data/sim/features.parquet")
    return {r["date"]: r for r in df.iter_rows(named=True)}


if __name__ == "__main__":
    main()
