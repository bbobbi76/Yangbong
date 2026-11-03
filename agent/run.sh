#!/bin/bash
# VM cron용: agent/run.sh rebalance  /  agent/run.sh surge
cd "$(dirname "$0")/.." || exit 1
mkdir -p agent/logs
export PYTHONIOENCODING=utf-8
.venv/bin/python -m agent."$1" --execute >> "agent/logs/$(date +%Y%m%d)_$1.log" 2>&1
