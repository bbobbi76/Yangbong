# 양봉기도회 — AQuA 모의투자 에이전트

AI 코딩 도구(Claude Code, Cursor, Codex, ChatGPT 등)로 이 저장소를 고칠 때 먼저 읽힐 문서.
ChatGPT처럼 저장소를 직접 못 읽는 도구는 이 파일 내용을 대화 첫머리에 붙여넣고 시작한다.

## 무엇을 하는 프로젝트인가

강원대 2026-2 자연어처리 팀 프로젝트. AQuA(Agent Quant Arena) 모의투자에서 KOSPI 200(KODEX 200)보다
높은 수익률을 내는 매매 에이전트. **2026-11-01 ~ 11-30 실제 점수 집계 중이고, main 브랜치 코드가 매일 실전 매매에 쓰인다.**

전략은 팀원 3명의 검증 결과를 결합했다 (`research/`):

| 가설 | 담당 | 실전 역할 | 코드 |
| --- | --- | --- | --- |
| A. DART 공시 이벤트 | 임규혁 | 악재 공시 종목 매수 금지 필터 (키워드 + Gemini 판독 = NLP 파트) | `agent/dart_filter.py` |
| B. +10% 급등 + 호재 공시 | 김형민 | 총자산 10%, 최대 2종목 단기 매매 (11/16부터, 이전 20%·3종목). +10~15%에서만 진입, 최고 +10% 갔다 +3% 아래면 매도 (`research/surge_exit_result.md`) | `agent/surge.py` |
| C. 대형주 6개월 모멘텀 | 이은겸 | 총자산 80%, 시총 상위 30 중. **11/16부터 모멘텀 상위 5 + 60일 저변동성 상위 5 반반 (10종목, 은겸 제안·팀 합의)** | `agent/momentum.py`, `agent/rebalance.py` |

## AQuA 규칙 (코드가 반드시 지켜야 함)

- API: `http://136.119.248.78`, 문서 `/docs`. 클라이언트는 `agent/aqua.py`.
- 초기 자금 1억, **코스피 보통주만** 거래 (ETF·우선주 불가), 09:00~15:00.
- **주문은 시간당 30회** (매시 정각 초기화). 체결 안 된 주문·거절된 주문은 횟수 안 씀.
- **같은 종목은 주문 후 30분간 매수·매도 모두 불가** (`429 SYMBOL_COOLDOWN`). 손절도 30분 막힌다.
- API 호출은 팀 전체 분당 100회. 시세는 한 번에 200종목까지 조회.
- 시장가 주문은 지금 호가 잔량만큼만 체결되고 나머지는 버려진다. 지정가 미체결분은 15분마다 재시도.
- 수수료 0.015%(매수·매도), 매도세 0.20% → 왕복 약 0.23%.

## 구조

```
agent/
  aqua.py         AQuA REST 클라이언트 (429 RATE_LIMIT 자동 재시도)
  momentum.py     C: 모멘텀 순위 (FinanceDataReader 일봉)
  dart_filter.py  A: 최근 DART 공시 → 매수 금지 종목 {symbol: 사유}
  rebalance.py    C+A: 하루 1회. 20거래일마다 전체 교체, 그 사이엔 악재 종목만 교체
  surge.py        B: 장중 상주 루프 (1분 간격)
  state/          (git 제외) c_state.json = C가 관리하는 종목, b_state.json = B 포지션
  logs/           (git 제외) 실행 로그
deploy/           GCP VM용 스크립트와 crontab
research/         가설 A·B·C 검증 코드와 결과 보고서
```

C와 B가 같은 계좌를 쓰므로 **서로의 종목을 건드리지 않게** state 파일로 구분한다.
rebalance는 `c_state.json`의 종목만 팔고, surge는 C 보유 종목을 매수 대상에서 뺀다.

## 개발 규칙

1. main에 바로 푸시해도 된다. 단, 푸시하면 **다음 날 아침부터 실전 매매에 반영**되니 아래 2번 확인은 꼭 하고 올린다.
2. 머지 전에 로컬에서 반드시 dry-run으로 확인:
   ```
   pip install -r requirements.txt
   python -m agent.rebalance        # 주문 없이 계획만 출력
   python -m agent.momentum         # 현재 모멘텀 순위
   ```
3. **로컬에서 `--execute` 금지.** 실전 주문은 VM만 낸다 (두 곳에서 돌면 주문이 중복된다).
4. 키(`TEAM_CODE`, `DART_KEY`, `GEMINI_KEY`)는 `.env`에만 둔다 (`.env.example` 참고). 코드·커밋·채팅에 붙이지 않는다.
5. 새 패키지를 쓰면 `requirements.txt`에 추가 (VM이 자동 설치).
6. 비중·손절폭 같은 숫자는 파일 상단 상수로 두고, 바꾸면 커밋 메시지에 근거(백테스트 결과)를 적는다.
7. 코드 스타일은 기존 파일을 따른다: 한국어 주석, 짧은 함수, 외부 프레임워크 추가 지양.

## 배포 (자동)

GCP VM `yangbong-agent` (asia-northeast3-a, 프로젝트 `gen-lang-client-0863302392`)가 main을 따라간다.

| 시각 (평일) | 동작 |
| --- | --- |
| 08:50 | `deploy/vm_update.sh`: main 최신 커밋을 받아 컴파일 + import + rebalance dry-run 검사. **실패하면 마지막 통과 커밋으로 자동 되돌림** |
| 09:02 | `surge` 시작 (15:00 종료) |
| 09:05 | `rebalance` 실행 |
| 11/30 15:30 | VM 자동 종료 |

- main 푸시·PR마다 GitHub Actions가 컴파일·import 검사 (`.github/workflows/check.yml`).
- 장중에 머지한 코드는 **다음 날 08:50**에 반영된다.
- 되돌림은 "실행이 죽는 코드"만 잡는다. 돌기는 하는데 판단이 틀린 코드(예: 비중 0.8 → 8)는 못 잡으니 푸시 전에 diff와 dry-run 결과를 한 번 더 본다.
- VM 로그 보기: `gcloud compute ssh yangbong-agent --zone=asia-northeast3-a --command="tail -50 ~/Yangbong/agent/logs/$(date +%Y%m%d)_*.log"`
  (VM 접근 권한은 규혁에게 요청)

## 알려진 한계 / 개선 아이디어

- B는 강세장(2026-01~09, 지수 +76%)에서만 검증됐다. 현재는 조정장이라 비중을 작게 뒀다.
- B 손절은 30분 쿨다운 때문에 진입 직후 30분간 불가.
- KOSPI 200 구성종목 대신 시총 상위 200을 쓴다.
- A 필터는 공시 **제목**만 본다. 본문(계약금액/매출액 비율, 자사주 취득 규모)을 LLM으로 읽는 게 다음 개선.
- 가설 A 결과대로 공급계약 공시도 C에서 제외한다. 대형주에선 과할 수 있어 팀 논의 필요.
