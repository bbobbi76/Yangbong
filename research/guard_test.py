# 지수 대비 안전선 기준(앞선 폭 몇 %p 아래면 지수 추종 전환)에 따라 1위·추락 확률이 어떻게 바뀌나
#   python research/guard_test.py
# 11/17 마감 상태(팀 -8.07%, KODEX 200 -14.83%)에서 남은 9거래일을 과거 모든 9거래일 구간으로 재생한다.
# 기본: 고변동성 상위 5, 주식 95%. 매일 종가 기준 앞선 폭이 안전선 아래면 다음 날부터 KODEX 200과 똑같이 움직인다고 본다.
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST = 9, 0.95, 0.0023
ME0, IDX0, FIRST = 1 - 0.0807, 1 - 0.1483, 1.0023   # 시작 자산(1억 대비), 1위 수익
BENCH = "069500"

lst = kospi_common().head(30)
names = list(lst["Code"])
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in names + [BENCH]}).ffill()
ret = close.pct_change()


def run(t, gap):
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in names if close[c].iloc[t - 60: t + 1].notna().all()}
    picks = sorted(vol, key=vol.get, reverse=True)[:5]
    me, idx, guarded = ME0 * (1 - W * COST / 2), IDX0, False
    for k in range(1, HOLD + 1):
        b = close[BENCH].iloc[t + k] / close[BENCH].iloc[t + k - 1] - 1
        r = b if guarded else W * np.mean([close[c].iloc[t + k] / close[c].iloc[t + k - 1] - 1 for c in picks])
        me, idx = me * (1 + r), idx * (1 + b)
        if not guarded and gap is not None and (me - idx) * 100 < gap:
            guarded = True
            me *= 1 - W * COST  # 지수 추종으로 갈아타는 비용
    return me, idx, guarded


rows, dates = [], close.index
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    below_ma = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for gap in (None, 2.0, 3.0, 4.0, 5.0):
        me, idx, g = run(t, gap)
        rows.append(dict(gap="없음" if gap is None else f"{gap:.0f}%p", below_ma=below_ma,
                         first=me >= FIRST, fourth=me >= 0.96, under=me < idx, guarded=g, final=me - 1))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("gap", sort=False).agg(
        구간수=("first", "size"), 평균최종=("final", lambda x: f"{x.mean():+.1%}"),
        **{"1위(+0.23%↑)": ("first", lambda x: f"{x.mean():.0%}")}, **{"4위(-4%↑)": ("fourth", lambda x: f"{x.mean():.0%}")},
        지수아래=("under", lambda x: f"{x.mean():.1%}"), 전환비율=("guarded", lambda x: f"{x.mean():.0%}"))


pd.set_option("display.unicode.east_asian_width", True)
print("남은 9거래일 재생 (시작: 팀 -8.07%, 지수 -14.83%), 고변동성 상위 5 + 안전선\n")
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면]\n" + summary(df[df.below_ma]).to_string())
