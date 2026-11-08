#!/usr/bin/env bash
# Weekday launcher for the bid/ask recorder (called by cron / systemd at 09:12 IST).
# Skips NSE holidays automatically: the recorder simply records nothing useful and exits at 15:41.
set -u
cd "$(dirname "$0")/../.."
mkdir -p data/upstox/bidask
exec python3 etl/bidask_recorder.py >> data/upstox/bidask/cron.out 2>&1
