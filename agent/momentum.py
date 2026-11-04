# 가설 C: 시총 상위 30 중 6개월 모멘텀(mom_skip) 순위 (은겸님 research 결과 기준)
# mom_skip = 5거래일 전 종가 / 120거래일 전 종가 - 1, 20일 평균 거래대금 50억 미만 제외
from datetime import date, timedelta
import pandas as pd
import FinanceDataReader as fdr

from agent.listing import kospi_common

TOP_N, LOOKBACK, SKIP, MIN_AMOUNT = 30, 120, 5, 5e9


def ranked(top_n=TOP_N, lookback=LOOKBACK, skip=SKIP):
    """모멘텀 높은 순으로 정렬한 DataFrame(code, name, mom, amount20). 신호는 전 거래일 종가까지만 사용."""
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
        rows.append(dict(code=code, name=name, mom=c.iloc[-1 - skip] / c.iloc[-1 - lookback] - 1, amount20=amount20))
    return pd.DataFrame(rows).sort_values("mom", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    r = ranked()
    r["mom"] = (r["mom"] * 100).round(1)
    r["amount20"] = (r["amount20"] / 1e8).round(0)
    print(r.rename(columns={"mom": "mom(%)", "amount20": "거래대금20(억)"}).to_string())
