# 남은 6거래일 공격 강도 비교: 종목 수(2~4)·주식 비중(95/99%)·안전선(3%p)
#   python research/aggressive_test.py
# 시작 11/20 장중(팀 -11.68%, KODEX 200 -16.53%), 4위 AITrader -5.64%. 안전선은 하루 종가 기준 (실전 14:30).
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, COST, BENCH = 6, 0.0023, "069500"
ME0, IDX0, FOURTH = 0.8832, 0.8347, 0.9436
codes = list(kospi_common().head(30)["Code"])
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in codes + [BENCH]}).ffill()
ret = close.pct_change()


def run(t, k, w, gap):
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in codes if close[c].iloc[t - 60: t + 1].notna().all()}
    picks = sorted(vol, key=vol.get, reverse=True)[:k]
    me, idx, mode = ME0 * (1 - w * COST), IDX0, "mom"
    for d in range(1, HOLD + 1):
        b = close[BENCH].iloc[t + d] / close[BENCH].iloc[t + d - 1] - 1
        r = 0.95 * b if mode == "index" else w * np.mean([close[c].iloc[t + d] / close[c].iloc[t + d - 1] - 1 for c in picks])
        me, idx = me * (1 + r), idx * (1 + b)
        if d < HOLD and mode == "mom" and gap is not None and (me - idx) * 100 < gap:
            mode, me = "index", me * (1 - 0.95 * COST)
    return me, idx


dates = close.index
half = dates[len(dates) // 2 + 120]
rows = []
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for k in (2, 3, 4):
        for w in (0.95, 0.99):
            for gap in (3.0, 4.0):
                me, idx = run(t, k, w, gap)
                rows.append(dict(cfg=f"{k}종목 {w:.0%} 안전선{gap:g}", below=below, recent=dates[t] >= half,
                                 fourth=me >= FOURTH, under=me < idx, final=me - 1))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("cfg", sort=False).agg(
        평균=("final", lambda x: f"{x.mean():+.1%}"),
        **{"4위": ("fourth", lambda x: f"{x.mean():.0%}")}, 지수아래=("under", lambda x: f"{x.mean():.1%}"))


pd.set_option("display.unicode.east_asian_width", True)
out = pd.concat({"전체": summary(df), "하락": summary(df[df.below]), "최근": summary(df[df.recent])}, axis=1)
print(out.to_string())
