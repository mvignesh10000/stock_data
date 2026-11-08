"""India VIX daily (NSE official historical API, fetched month by month) -> data/india_vix_daily.csv"""
import json, glob, sys, datetime as dt, polars as pl
rows = []
for f in glob.glob(f"{sys.argv[1]}/vix_*.json"):
    for d in json.load(open(f))["data"]:
        rows.append((int(dt.datetime.strptime(d["EOD_TIMESTAMP"], "%d-%b-%Y").strftime("%Y%m%d")), d["EOD_OPEN_INDEX_VAL"], d["EOD_HIGH_INDEX_VAL"], d["EOD_LOW_INDEX_VAL"], d["EOD_CLOSE_INDEX_VAL"], d["EOD_PREV_CLOSE"]))
v = pl.DataFrame(rows, schema=["date", "open", "high", "low", "close", "prev_close"], orient="row").unique("date").sort("date")
v.write_csv(sys.argv[2]); print(v.height, v["date"].min(), v["date"].max())
