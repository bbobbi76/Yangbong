# 1위 선을 넘으면 현금으로 굳히는 규칙이 1위 확률을 올리나
#   python research/lock_test.py
# 11/18 리더보드: 1~3위가 +0.23% / 0.00% / -0.21%로 거의 현금(움직임 없음). 우리가 총수익 L% 이상이 되면
# 다음 날 아침 C 종목을 모두 팔고 현금으로 남은 기간을 버티는 규칙을 과거 9거래일 구간으로 재생한다.
# 기본: 고변동성 상위 4, 주식 95%, 지수 대비 +3%p 안전선 (실전과 같음).
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST, SELL, K, GAP = 9, 0.95, 0.0023, 0.00215, 4, 3.0
ME0, IDX0 = 1 - 0.0807, 1 - 0.1483
BENCH = "069500"

lst = kospi_common().head(30)
names = list(lst["Code"])
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in names + [BENCH]}).ffill()
ret = close.pct_change()


def run(t, lock, hold=HOLD):
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in names if close[c].iloc[t - 60: t + 1].notna().all()}
    picks = sorted(vol, key=vol.get, reverse=True)[:K]
    me, idx, mode = ME0 * (1 - W * COST / 2), IDX0, "mom"
    for k in range(1, hold + 1):
        b = close[BENCH].iloc[t + k] / close[BENCH].iloc[t + k - 1] - 1
        r = {"cash": 0.0, "index": W * b,
             "mom": W * np.mean([close[c].iloc[t + k] / close[c].iloc[t + k - 1] - 1 for c in picks])}[mode]
        me, idx = me * (1 + r), idx * (1 + b)
        if k == hold:
            break
        if mode != "cash" and lock is not None and me >= 1 + lock / 100:
            mode, me = "cash", me * (1 - W * SELL)
        elif mode == "mom" and (me - idx) * 100 < GAP:
            mode, me = "index", me * (1 - W * COST)
    return me, idx, mode


rows, dates = [], close.index
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    below_ma = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for lock in (None, 0.5, 1.0, 2.0, 3.0, 5.0):
        me, idx, mode = run(t, lock)
        rows.append(dict(lock="없음" if lock is None else f"+{lock:g}%", below_ma=below_ma, final=me - 1,
                         first=me >= 1.0023, first1=me >= 1.01, first2=me >= 1.02, under=me < idx, cash=mode == "cash"))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("lock", sort=False).agg(
        구간수=("first", "size"), 평균최종=("final", lambda x: f"{x.mean():+.1%}"),
        **{"1위(+0.23%↑)": ("first", lambda x: f"{x.mean():.0%}")},
        **{"+1%↑": ("first1", lambda x: f"{x.mean():.0%}")}, **{"+2%↑": ("first2", lambda x: f"{x.mean():.0%}")},
        지수아래=("under", lambda x: f"{x.mean():.1%}"), 현금전환=("cash", lambda x: f"{x.mean():.0%}"))


pd.set_option("display.unicode.east_asian_width", True)
print(f"남은 9거래일 재생 (팀 -8.07%, 지수 -14.83%), 고변동성 상위 {K} + 안전선 {GAP:g}%p + 1위 굳히기\n")
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면]\n" + summary(df[df.below_ma]).to_string())
half = dates[len(dates) // 2 + 120]
print(f"\n[최근 절반 ({half:%Y-%m} 이후 시작)]")
df["t"] = [d for d in dates[dates.searchsorted(pd.Timestamp('2024-01-01')): len(dates) - HOLD] for _ in range(6)]
print(summary(df[df.t >= half]).to_string())
