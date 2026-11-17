# 안전선 전환 시 쓰는 지수 추종(시총 상위 10, 시총 비중, 한 종목 최대 20%)이 KODEX 200을 얼마나 잘 따라가나
#   python research/index_track_test.py
# 현재 시총 비중을 고정해 2024-01 이후 모든 9거래일 구간의 수익 차이(추종 - KODEX)를 본다.
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common
from agent.rebalance import index_weights

BENCH, HOLD, COST = "069500", 9, 0.0023
lst = kospi_common()
marcap = dict(zip(lst["Code"], lst["Marcap"]))
close = pd.DataFrame({c: fdr.DataReader(c, "2023-06-01")["Close"] for c in list(lst["Code"][:20]) + [BENCH]}).ffill()
dates = close.index
rows = []
for n in (5, 10, 15, 20):
    w = index_weights(list(lst["Code"][:n]), marcap)
    for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
        r = sum(w[c] * (close[c].iloc[t + HOLD] / close[c].iloc[t] - 1) for c in w if not np.isnan(close[c].iloc[t]))
        b = close[BENCH].iloc[t + HOLD] / close[BENCH].iloc[t] - 1
        rows.append(dict(n=n, diff=0.95 * r - COST - b))
df = pd.DataFrame(rows)
print("9거래일 (주식 95% 추종 - KODEX 200), 전환 비용 0.23% 포함")
print(df.groupby("n")["diff"].describe(percentiles=[.05, .5, .95]).map(lambda v: f"{v:+.2%}" if abs(v) < 5 else f"{v:.0f}").to_string())
print("\n앞선 폭 3%p를 다 까먹을 확률 (차이 < -3%p):")
print(df.groupby("n")["diff"].apply(lambda x: f"{(x < -0.03).mean():.1%}").to_string())
