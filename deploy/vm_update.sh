#!/bin/bash
# VM cron 평일 08:50: main 최신 커밋을 받아 검사하고, 통과하면 그 코드로, 실패하면 마지막 통과 커밋으로 둔다
# 검사 = 전체 컴파일 + 모듈 import + rebalance dry-run(로그인·시세·DART·Gemini·주문계획까지, 주문은 안 냄)
cd "$HOME/Yangbong" || exit 1
mkdir -p agent/logs
LOG="agent/logs/$(date +%Y%m%d)_update.log"
GOOD_FILE="$HOME/.yangbong_good"   # 마지막으로 검사 통과한 커밋 (저장소 밖에 둬서 checkout에 안 휩쓸림)
VER_FILE="$HOME/.yangbong_strategy_ver"  # 지난번 종목 선정 코드(momentum.py + rebalance.py) 해시
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

# 종목 선정 코드가 지난번과 달라졌으면(전략 변경) 마지막 교체일을 비워 오늘 09:05에 바로 전체 교체.
# 팀원이 rebalance.py를 통째로 바꿔도 동작하도록 배포 스크립트에서 처리한다 (rebalance는 rebalanced가 없으면 전체 교체).
VER=$(cat agent/momentum.py agent/rebalance.py | sha1sum | cut -c1-12)
if [ -s "$VER_FILE" ] && [ "$(cat "$VER_FILE")" != "$VER" ] && [ -f agent/state/c_state.json ]; then
    .venv/bin/python - <<'PY'
import json
p = "agent/state/c_state.json"
s = json.load(open(p, encoding="utf-8"))
s["rebalanced"] = None
json.dump(s, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
    echo ">>> 종목 선정 코드 변경 감지 ($(cat "$VER_FILE") → $VER) → 오늘 09:05 전체 교체"
fi
echo "$VER" > "$VER_FILE"
