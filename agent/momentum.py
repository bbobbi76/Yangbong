# 가설 C: 시총 상위 30 중 6개월 모멘텀(mom_skip) 순위 (은겸님 research 결과 기준)
# mom_skip = 5거래일 전 종가 / 120거래일 전 종가 - 1, 20일 평균 거래대금 50억 미만 제외
from datetime import date, timedelta
import pandas as pd
import FinanceDataReader as fdr

from agent.listing import kospi_common

TOP_N, LOOKBACK, SKIP, MIN_AMOUNT = 30, 120, 5, 5e9
# 정렬 기준. 11/16부터 "vol60"(최근 60거래일 일간 수익률 표준편차가 큰 순 = 고변동성).
# 근거: research/short_horizon_result.md — 남은 기간에 +9% 이상 낼 확률이 지금 국면에서 가장 높았다.
# 이전 값 "mom"(6개월 모멘텀)으로 되돌리면 원래 전략.
SIGNAL = "vol60"


def ranked(top_n=TOP_N, lookback=LOOKBACK, skip=SKIP, by=SIGNAL):
    """by 기준 내림차순 DataFrame(code, name, mom, vol60, amount20). 신호는 전 거래일 종가까지만 사용."""
    lst = kospi_common().head(top_n)

    start = date.today() - timedelta(days=lookback * 2)
    rows = []
    for code, name in zip(lst["Code"], lst["Name"]):
        df = fdr.DataReader(code, start)
        df = df[df.index.date < date.today()]  # 장중 실행 시 오늘 미완성 봉 제외
        if len(df) <= lookback:
            continue
        c = df["Close"]
        amount20 = (c * df["Volume"]).tail(20).mean()
        if amount20 < MIN_AMOUNT:
            continue
        rows.append(dict(code=code, name=name, mom=c.iloc[-1 - skip] / c.iloc[-1 - lookback] - 1,
                         vol60=c.pct_change().tail(60).std(), amount20=amount20))
    return pd.DataFrame(rows).sort_values(by, ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    r = ranked()
    r["mom"] = (r["mom"] * 100).round(1)
    r["vol60"] = (r["vol60"] * 100).round(2)
    r["amount20"] = (r["amount20"] / 1e8).round(0)
    print(f"정렬 기준: {SIGNAL}")
    print(r.rename(columns={"mom": "mom(%)", "vol60": "vol60(%)", "amount20": "거래대금20(억)"}).to_string())
