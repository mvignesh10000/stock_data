"""Translate an `algotest`-kind config into the exact fields of AlgoTest's strategy builder
(docs.algotest.in: Instrument settings, Entry settings, Legwise settings, Leg builder, Overall strategy
settings, Execution settings, Portfolio DTE / Auto-activation)."""

DTE_DAY_TUE = {0: "Tuesday (expiry day)", 1: "Monday", 2: "Friday", 3: "Thursday", 4: "Wednesday"}


def strike_text(s, und):
    syn = und == "synthetic"
    pre = "Synthetic Future → " if syn else ""
    m = s.get("mode", "atm")
    if m == "atm":
        return pre + "Strike Type: ATM"
    if m == "otm":
        return pre + f"Strike Type: OTM{s['n']}"
    if m == "itm":
        return pre + f"Strike Type: ITM{s['n']}"
    if m == "closest_premium":
        return f"Closest Premium: ₹{s['value']:g}"
    if m == "premium_gte":
        return f"Premium >= ₹{s['value']:g}"
    if m == "atm_premium_pct":
        return f"ATM Straddle Premium %: {s['value']:g}%"
    if m == "straddle_width":
        return f"Straddle Width: {s['value']:+g} × ATM straddle"
    return m


def sheet(cfg, multiplier_2l=1, multiplier_3l=1):
    und = cfg.get("underlying", "cash")
    rows = [
        ("Instrument settings", "Index: NIFTY · Underlying from: Cash"),
        ("Strategy type", "Intraday"),
        ("Entry time", cfg["entry_time"]),
        ("Exit time", cfg["exit_time"]),
        ("No re-entry after", cfg.get("no_reentry_after", "-")),
        ("Legwise settings → Square off", "Complete" if cfg.get("square_off") == "complete" else "Partial"),
        ("Legwise settings → Trail SL to break-even", {"none": "Off", "sl_legs": "On – SL legs", "all_legs": "On – All legs"}[cfg.get("trail_to_breakeven", "none")]),
    ]
    legs = []
    for i, l in enumerate(cfg["legs"], 1):
        legs.append({
            "#": i, "Segment": "Options", "Lots": l.get("lots", 1), "Position": l["side"].capitalize(), "Option type": "Call" if l["opt"] == "CE" else "Put",
            "Expiry": "Weekly", "Strike criteria": strike_text(l["strike"], und),
            "Stop loss": (f"{l['sl']['value']:g}%" if l.get("sl") and l["sl"]["kind"] == "pct" else (f"{l['sl']['value']:g} pts" if l.get("sl") else "-")),
            "Target": (f"{l['target']['value']:g}{'%' if l['target']['kind'] == 'pct' else ' pts'}" if l.get("target") else "-"),
            "Trail SL": (f"{l['trail']['x']:g}-{l['trail']['y']:g} ({'%' if l['trail']['kind'] == 'pct' else 'pts'})" if l.get("trail") else "-"),
            "Re-entry on SL": ({"cost": "RE COST", "asap": "RE ASAP", "momentum": "RE MOMENTUM"}[l["re_sl"]["kind"]] + f" × {l['re_sl']['count']}" if l.get("re_sl") else "-"),
            "Simple momentum": (f"Premium % ↓ {l['momentum']['value']:g}" if l.get("momentum") else "-"),
        })
    o = cfg.get("overall", {})
    ov = []
    if o.get("sl_mtm"):
        ov.append(("Overall stop loss", f"MTM ₹{o['sl_mtm']:,.0f} (per 1× quantity; AlgoTest multiplies by the quantity multiplier)"))
    if o.get("tgt_mtm"):
        ov.append(("Overall target", f"MTM ₹{o['tgt_mtm']:,.0f}"))
    if o.get("lock_reach"):
        if o.get("trail_every"):
            ov.append(("Trailing options → Lock and Trail", f"If profit reaches ₹{o['lock_reach']:,.0f}, lock ₹{o['lock_profit']:,.0f}; for every ₹{o['trail_every']:,.0f} more, trail by ₹{o['trail_by']:,.0f}"))
        else:
            ov.append(("Trailing options → Lock", f"If profit reaches ₹{o['lock_reach']:,.0f}, lock ₹{o['lock_profit']:,.0f}"))
    if o.get("trail_sl_x"):
        ov.append(("Trailing options → Overall Trail SL", f"{o['trail_sl_x']:,.0f} – {o['trail_sl_y']:,.0f}"))
    dte = cfg.get("dte") or []
    port = [
        ("Portfolio → DTE filter / Auto-activation", ", ".join(f"DTE {d} ({DTE_DAY_TUE.get(d, '?')} on the Tuesday-expiry calendar)" for d in dte) or "All days"),
        ("Quantity multiplier", f"₹2L capital: {multiplier_2l}× · ₹3L capital: {multiplier_3l}× (expiry-day margin includes SEBI's extra 2% ELM)"),
        ("Execution → Entry/Exit order type", "Limit (market orders are disabled since 1-Apr-2026); limit buffer 5–8% of premium, convert-to-market/chase on"),
        ("Execution → Delay entry by", "3–5 s on the SELL legs so the BUY (hedge) legs fill first and you get the hedge margin benefit"),
        ("Execution → Trade monitoring", "Candle Close (matches how the backtest evaluates Overall SL / Target / Lock)"),
        ("Execution → TGT/SL ref price", "Traded"),
        ("Execution → Product", "NRML (or make sure exit time is before your broker's MIS auto square-off, e.g. IIFL/Upstox 15:15)"),
        ("Execution → Auto square-off on margin error", "On"),
    ]
    return {"settings": rows, "legs": legs, "overall": ov, "portfolio": port}
