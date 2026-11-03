# 양봉기도회 AQuA 에이전트

가설 A(공시 필터) + B(급등+호재 공시) + C(대형주 6개월 모멘텀)를 결합한 실전 코드.

| 파일 | 역할 | 실행 시점 |
| --- | --- | --- |
| `rebalance.py` | **C + A**. 총자산 80%로 시총 상위 30 중 6개월 모멘텀 상위 5종목 보유. 20거래일마다 전체 교체, 그 사이엔 악재 공시 종목만 빼고 다음 순위로 채움 | 평일 09:05 1회 |
| `surge.py` | **B**. 시총 상위 200 종목을 1분마다 감시, +10% 도달 + 전일~당일 호재 공시면 매수(총자산 20%, 최대 3종목). -5% 손절, 14:50에 음봉이면 청산 | 평일 09:02 ~ 15:00 상주 |
| `dart_filter.py` | A. 최근 3일 DART 공시를 키워드 + Gemini로 판독해 매수 금지 종목 반환 | 위 두 개가 호출 |
| `momentum.py` | C. 모멘텀 순위 계산 (`python -m agent.momentum`으로 현재 순위 확인) | |
| `aqua.py` | AQuA REST API 클라이언트 | |

## 실행

```
pip install -r requirements.txt
# .env 에 TEAM_CODE, DART_KEY, GEMINI_KEY 입력 (.env.example 참고, 커밋 금지)
python -m agent.rebalance             # 주문 계획만 출력
python -m agent.rebalance --execute   # 실제 주문
python -m agent.surge --execute       # 장중 상주
```

`agent\run.bat rebalance|surge` 는 작업 스케줄러용 래퍼로, 로그를 `agent/logs/`에 남긴다.

## 주의

- 상태 파일 `agent/state/`(C 목표 종목, B 포지션)는 실행한 PC에만 있다. 한 대에서만 돌릴 것.
- 같은 종목 30분 재거래 제한 때문에 B는 진입 후 30분간 손절이 안 된다.
- KOSPI200 구성종목 대신 시총 상위 200을 쓴다.
- 공급계약 공시는 가설 A 결과대로 C에서 제외 대상이다(B에서는 +10% 동반 시 호재로 본다).
