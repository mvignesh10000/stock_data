#!/usr/bin/env python3
"""Run Strategy B on several broker accounts in parallel (one executor process per account).

Usage:  python execution/run_b.py [--accounts execution/accounts.json]     (schedule at 09:12 IST on weekdays;
        each executor exits immediately when today is not a NIFTY expiry day)
Every account gets its own token (UPSTOX_TOKEN_FILE), log (data/upstox/exec_<name>.log) and ledger
(data/upstox/b_ledger_<name>.csv) with its own kill-switch. Accounts run independently: if one fails, the others continue.
"""
import argparse, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accounts", default=os.path.join(HERE, "accounts.json"))
    ap.add_argument("--force", action="store_true", help="paper test on a non-expiry day")
    a = ap.parse_args()
    cfg = json.load(open(a.accounts))["accounts"]
    procs = []
    for acc in cfg:
        tf = os.path.expanduser(acc["token_file"])
        if not os.path.exists(tf):
            print(f"[{acc['name']}] token file {tf} missing - skipped")
            continue
        cmd = [sys.executable, os.path.join(HERE, "upstox_ironfly.py"), "NIFTY", "--lots", str(acc.get("lots", 1)), "--account", acc["name"]]
        if acc.get("live"):
            cmd.append("--live")
        if a.force:
            cmd.append("--force")
        env = dict(os.environ, UPSTOX_TOKEN_FILE=tf)
        log = open(os.path.join(ROOT, "data/upstox", f"run_{acc['name']}.out"), "a")
        procs.append((acc["name"], subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)))
        print(f"[{acc['name']}] started: {acc.get('lots', 1)} lot(s), {'LIVE' if acc.get('live') else 'paper'}")
    for name, p in procs:
        p.wait()
        print(f"[{name}] finished with exit code {p.returncode}; see data/upstox/exec_{name}.log")


if __name__ == "__main__":
    main()
