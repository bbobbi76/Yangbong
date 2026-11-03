#!/bin/bash
# VM cron용: agent/run.sh rebalance  /  agent/run.sh surge
# 실행 전에 깃 최신 코드를 받아 온다 (푸시만 하면 다음 실행부터 반영)
cd "$(dirname "$0")/.." || exit 1
mkdir -p agent/logs
LOG="agent/logs/$(date +%Y%m%d)_$1.log"
export PYTHONIOENCODING=utf-8
{ echo "== $(date '+%F %T') $(git pull -q --ff-only 2>&1 && git log --oneline -1)"; } >> "$LOG"
.venv/bin/pip install -q -r requirements.txt >> "$LOG" 2>&1
.venv/bin/python -m agent."$1" --execute >> "$LOG" 2>&1
