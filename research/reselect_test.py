# 고변동성 상위 4를 9거래일 내내 들고 가는 것 vs 중간에 다시 골라 갈아타는 것
#   python research/reselect_test.py
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST, K, BENCH = 9, 0.95, 0.0023, 4, "069500"
ME0, IDX0 = 0.9193, 0.8517
lst = kospi_common().head(30)
names = list(lst["Code"])
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in names + [BENCH]}).ffill()
ret = close.pct_change()


def top(t):
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in names if close[c].iloc[t - 60: t + 1].notna().all()}
    return set(sorted(vol, key=vol.get, reverse=True)[:K])


def run(t, every):
    me, idx, hold = ME0 * (1 - W * COST / 2), IDX0, top(t)
    for k in range(1, HOLD + 1):
        r = W * np.mean([close[c].iloc[t + k] / close[c].iloc[t + k - 1] - 1 for c in hold])
        me, idx = me * (1 + r), idx * close[BENCH].iloc[t + k] / close[BENCH].iloc[t + k - 1]
        if every and k % every == 0 and k < HOLD:
            new = top(t + k)
            me *= 1 - W * COST * len(new - hold) / K   # 바뀐 종목만 왕복 비용
            hold = new
    return me, idx


rows, dates = [], close.index
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for every in (None, 1, 3, 5):
        me, idx = run(t, every)
        rows.append(dict(s="보유" if every is None else f"{every}일마다 재선정", below=below,
                         first=me >= 1.0023, fourth=me >= 0.96, under=me < idx, final=me - 1))
df = pd.DataFrame(rows)
f = lambda d: d.groupby("s", sort=False).agg(평균=("final", lambda x: f"{x.mean():+.1%}"), **{"1위": ("first", lambda x: f"{x.mean():.0%}")},
                                             **{"4위": ("fourth", lambda x: f"{x.mean():.0%}")}, 지수아래=("under", lambda x: f"{x.mean():.1%}"))
pd.set_option("display.unicode.east_asian_width", True)
print("[전체]\n" + f(df).to_string() + "\n\n[하락 국면]\n" + f(df[df.below]).to_string())
