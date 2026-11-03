#!/bin/bash
# VM cron 평일 08:50: main 최신 커밋을 받아 검사하고, 통과하면 그 코드로, 실패하면 마지막 통과 커밋으로 둔다
# 검사 = 전체 컴파일 + 모듈 import + rebalance dry-run(로그인·시세·DART·Gemini·주문계획까지, 주문은 안 냄)
cd "$HOME/Yangbong" || exit 1
mkdir -p agent/logs
LOG="agent/logs/$(date +%Y%m%d)_update.log"
GOOD_FILE="$HOME/.yangbong_good"   # 마지막으로 검사 통과한 커밋 (저장소 밖에 둬서 checkout에 안 휩쓸림)
export PYTHONIOENCODING=utf-8
exec >> "$LOG" 2>&1

echo "== $(date '+%F %T')"
git fetch -q origin || { echo "fetch 실패 → 현재 코드 유지"; exit 0; }
NEW=$(git rev-parse --short origin/main)
git checkout -q --detach origin/main
.venv/bin/pip install -q -r requirements.txt

if .venv/bin/python -m compileall -q agent \
   && .venv/bin/python -c "import agent.rebalance, agent.surge" \
   && .venv/bin/python -m agent.rebalance; then
    echo "$NEW" > "$GOOD_FILE"
    echo "검사 통과 → $NEW ($(git log --oneline -1))"
elif [ -s "$GOOD_FILE" ]; then
    GOOD=$(cat "$GOOD_FILE")
    git checkout -q --detach "$GOOD"
    .venv/bin/pip install -q -r requirements.txt
    echo "!!! $NEW 검사 실패 → 마지막 통과 커밋 $GOOD 로 되돌림"
else
    echo "!!! $NEW 검사 실패, 되돌릴 커밋 없음"
fi
