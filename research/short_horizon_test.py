# 남은 12거래일 동안 1위(+9% 이상)를 노릴 때 어떤 대형주 전략이 유리한가
# 목표가 "평균 초과수익"이 아니라 "짧은 기간에 크게 오를 확률"이라, 과거 모든 12거래일 구간의 수익률 분포를 비교한다.
#   python research/short_horizon_test.py
# 유니버스: 현재 시총 상위 30 코스피 보통주 (생존 편향 있음 — 과거엔 30위 밖이던 종목도 포함)
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

START, EVAL_FROM = "2023-01-01", "2024-01-01"
HOLD, COST = 12, 0.0023          # 보유 12거래일, 왕복 비용 0.23%
TARGET, RUIN = 0.09, -0.10       # 1위에 필요한 수익률, 크게 잃는 기준
BENCH = "069500"

lst = kospi_common().head(30)
names = dict(zip(lst["Code"], lst["Name"]))
close = pd.DataFrame({c: fdr.DataReader(c, START)["Close"] for c in list(names) + [BENCH]}).dropna(how="all")
ret = close.pct_change()


def pick(t):
    """t일 종가까지 정보로 각 전략의 종목 바구니를 고른다 (가중치 dict)"""
    px = close.iloc[: t + 1]
    r = ret.iloc[t - 59: t + 1]
    ok = [c for c in names if px[c].iloc[-121:].notna().all()]
    mom6 = {c: px[c].iloc[-6] / px[c].iloc[-121] - 1 for c in ok}
    mom1 = {c: px[c].iloc[-6] / px[c].iloc[-26] - 1 for c in ok}
    beta = {c: r[c].cov(r[BENCH]) / r[BENCH].var() for c in ok}
    vol = {c: r[c].std() for c in ok}
    top = lambda d, k: {c: 1 / k for c in sorted(d, key=d.get, reverse=True)[:k]}
    return {
        "현재: 6개월 모멘텀 상위5": top(mom6, 5),
        "1개월 모멘텀 상위5": top(mom1, 5),
        "고베타 상위5 (60일)": top(beta, 5),
        "고베타 상위3 (60일)": top(beta, 3),
        "고변동성 상위5 (60일)": top(vol, 5),
        "삼성전자+SK하이닉스 반반": {"005930": 0.5, "000660": 0.5},
        "KODEX 200 (지수)": {BENCH: 1.0},
    }


rows = []
dates = close.index
for t in range(dates.searchsorted(pd.Timestamp(EVAL_FROM)), len(dates) - HOLD):
    bench = close[BENCH].iloc[t + HOLD] / close[BENCH].iloc[t] - 1
    above_ma = close[BENCH].iloc[t] > close[BENCH].iloc[t - 59: t + 1].mean()
    for name, w in pick(t).items():
        g = sum(wt * (close[c].iloc[t + HOLD] / close[c].iloc[t] - 1) for c, wt in w.items()) - COST * (name != "KODEX 200 (지수)")
        rows.append(dict(date=dates[t], strategy=name, ret=g, excess=g - bench, above_ma=above_ma))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("strategy", sort=False).agg(
        구간수=("ret", "size"),
        평균수익=("ret", lambda x: f"{x.mean():+.1%}"),
        **{f"+{TARGET:.0%}↑ 확률": ("ret", lambda x: f"{(x >= TARGET).mean():.0%}")},
        **{f"{RUIN:.0%}↓ 확률": ("ret", lambda x: f"{(x <= RUIN).mean():.0%}")},
        지수이김=("excess", lambda x: f"{(x > 0).mean():.0%}"),
    )


pd.set_option("display.unicode.east_asian_width", True)
print(f"12거래일 보유 수익률 분포, {df.date.min():%Y-%m-%d} ~ {df.date.max():%Y-%m-%d} 시작 구간 전부 (겹침 있음)\n")
print("[전체]")
print(summary(df).to_string())
print("\n[지수가 60일 이평 아래에서 시작한 구간 — 지금과 같은 국면]")
print(summary(df[~df.above_ma]).to_string())
print("\n[최근 6개월 시작 구간]")
print(summary(df[df.date >= dates[-HOLD] - pd.Timedelta(days=183)]).to_string())

t = len(dates) - 1
print(f"\n오늘({dates[t]:%Y-%m-%d} 종가 기준) 각 전략 종목:")
for name, w in pick(t).items():
    print(f"  {name}: " + ", ".join(names.get(c, c) for c in w))
