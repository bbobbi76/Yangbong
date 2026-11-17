# 고변동성 상위 4의 후보 범위(시총 상위 20/30/50)와 변동성 기간(40/60/90일) 비교
#   python research/universe_lookback_test.py
# 실전과 같이 굳히기(+2%)·안전선 3%p·주식 95%, 시작 11/17 마감(팀 -8.07%, 지수 -14.83%), 남은 9거래일.
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST, SELL, K, GAP, LOCK = 9, 0.95, 0.0023, 0.00215, 4, 3.0, 2.0
BENCH = "069500"
lst = kospi_common().head(50)
codes = list(lst["Code"])
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in codes + [BENCH]}).ffill()
vals = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01").eval("Close * Volume") for c in codes}).reindex(close.index)
ret = close.pct_change()


def run(t, n, lb):
    pool = [c for c in codes[:n] if close[c].iloc[t - 120: t + 1].notna().all()
            and vals[c].iloc[t - 19: t + 1].mean() >= 5e9]  # 실전과 같은 20일 평균 거래대금 50억 이상
    vol = {c: ret[c].iloc[t - lb + 1: t + 1].std() for c in pool}
    picks = sorted(vol, key=vol.get, reverse=True)[:K]
    me, idx, mode = 0.9193 * (1 - W * COST / 2), 0.8517, "mom"
    for k in range(1, HOLD + 1):
        b = close[BENCH].iloc[t + k] / close[BENCH].iloc[t + k - 1] - 1
        r = {"cash": 0.0, "index": W * b,
             "mom": W * np.mean([close[c].iloc[t + k] / close[c].iloc[t + k - 1] - 1 for c in picks])}[mode]
        me, idx = me * (1 + r), idx * (1 + b)
        if k == HOLD:
            break
        if mode != "cash" and me >= 1 + LOCK / 100:
            mode, me = "cash", me * (1 - W * SELL)
        elif mode == "mom" and (me - idx) * 100 < GAP:
            mode, me = "index", me * (1 - W * COST)
    return me, idx


dates = close.index
start = dates.searchsorted(pd.Timestamp("2024-01-01"))
half = dates[len(dates) // 2 + 120]
rows = []
for t in range(start, len(dates) - HOLD):
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for n in (20, 30, 50):
        for lb in (40, 60, 90):
            me, idx = run(t, n, lb)
            rows.append(dict(cfg=f"상위{n} {lb}일", below=below, recent=dates[t] >= half,
                             first=me >= 1.0023, under=me < idx, final=me - 1))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("cfg", sort=False).agg(
        구간=("first", "size"), 평균=("final", lambda x: f"{x.mean():+.1%}"),
        **{"1위": ("first", lambda x: f"{x.mean():.0%}")}, 지수아래=("under", lambda x: f"{x.mean():.1%}"))


pd.set_option("display.unicode.east_asian_width", True)
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면]\n" + summary(df[df.below]).to_string())
print(f"\n[최근 절반 ({half:%Y-%m} 이후)]\n" + summary(df[df.recent]).to_string())
