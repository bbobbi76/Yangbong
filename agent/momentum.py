# 가설 C: 시총 상위 30 중 6개월 모멘텀(mom_skip) 순위 (은겸님 research 결과 기준)
# mom_skip = 5거래일 전 종가 / 120거래일 전 종가 - 1, 20일 평균 거래대금 50억 미만 제외
from datetime import date, timedelta
import pandas as pd
import FinanceDataReader as fdr

from agent.listing import kospi_common

TOP_N, LOOKBACK, SKIP, MIN_AMOUNT = 30, 120, 5, 5e9
# 종목 선정 기준. 11/16부터 "mom+lowvol": 6개월 모멘텀 상위 k + 60일 저변동성 상위 k를 반반 (이은겸 제안, 팀 합의).
# 은겸 백테스트(15거래일, 주식 80%): 모멘텀만 대비 손실은 줄고 평균 +2.7% → +2.2%.
# "mom" = 모멘텀만(원래 전략), "vol60" = 고변동성만(research/short_horizon_result.md 비교안)
SIGNAL = "mom+lowvol"


def ranked(top_n=TOP_N, lookback=LOOKBACK, skip=SKIP, by="mom"):
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


def groups(rank, signal=SIGNAL):
    """[(그룹 이름, 종목 순서)]. rebalance가 그룹마다 같은 수씩 고른다"""
    if signal == "mom+lowvol":
        return [("모멘텀", list(rank.sort_values("mom", ascending=False)["code"])),
                ("저변동", list(rank.sort_values("vol60")["code"]))]
    return [(signal, list(rank.sort_values(signal, ascending=False)["code"]))]


if __name__ == "__main__":
    r = ranked()
    r["mom"] = (r["mom"] * 100).round(1)
    r["vol60"] = (r["vol60"] * 100).round(2)
    r["amount20"] = (r["amount20"] / 1e8).round(0)
    print(f"선정 기준: {SIGNAL}")
    for g, order in groups(ranked()):
        print(f"  {g} 순서: " + ", ".join(dict(zip(r['code'], r['name']))[c] for c in order[:7]))
    print(r.rename(columns={"mom": "mom(%)", "vol60": "vol60(%)", "amount20": "거래대금20(억)"}).to_string())
