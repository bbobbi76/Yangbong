#!/bin/bash
# VM cron: vm_run.sh surge (09:02) / vm_run.sh rebalance (09:05) / vm_run.sh rebalance --lock-only (장중 1위 굳히기 확인). 코드는 08:50 vm_update.sh가 고른 버전 그대로 실행
cd "$HOME/Yangbong" || exit 1
mkdir -p agent/logs
export PYTHONIOENCODING=utf-8
.venv/bin/python -m agent."$1" --execute "${@:2}" >> "agent/logs/$(date +%Y%m%d)_$1.log" 2>&1
