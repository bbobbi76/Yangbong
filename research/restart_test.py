# 11/20 안전선 전환 후 고변동성 상위 4로 복귀할 때 안전선 기준별 4위·지수 아래 확률
#   python research/restart_test.py
# 시작: 11/20 장중(팀 -11.59%, KODEX 200 -15.78%, 4위 AITrader -5.64%, 1위 약 +1.5%), 남은 6거래일.
# 안전선은 하루 종가 기준으로 판단해 그날 종가에 지수 추종으로 전환 (실전: 14:30 확인 후 바로 전환).
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST, K, BENCH = 6, 0.95, 0.0023, 4, "069500"
ME0, IDX0, FOURTH, FIRST = 0.8841, 0.8422, 0.9436, 1.015
codes = list(kospi_common().head(30)["Code"])
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in codes + [BENCH]}).ffill()
ret = close.pct_change()


def run(t, gap, mode0="mom"):
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in codes if close[c].iloc[t - 60: t + 1].notna().all()}
    picks = sorted(vol, key=vol.get, reverse=True)[:K]
    me, idx, mode = ME0 * (1 - W * COST) if mode0 == "mom" else ME0, IDX0, mode0
    for k in range(1, HOLD + 1):
        b = close[BENCH].iloc[t + k] / close[BENCH].iloc[t + k - 1] - 1
        r = W * b if mode == "index" else W * np.mean([close[c].iloc[t + k] / close[c].iloc[t + k - 1] - 1 for c in picks])
        me, idx = me * (1 + r), idx * (1 + b)
        if k < HOLD and mode == "mom" and gap is not None and (me - idx) * 100 < gap:
            mode, me = "index", me * (1 - W * COST)
    return me, idx


dates = close.index
half = dates[len(dates) // 2 + 120]
rows = []
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    cfgs = [("지수 추종 유지", None, "index"), ("4종목, 안전선 없음", None, "mom")] + \
           [(f"4종목, 안전선 {g:g}%p", g, "mom") for g in (1.0, 2.0, 3.0)]
    for name, g, m in cfgs:
        me, idx = run(t, g, m)
        rows.append(dict(cfg=name, below=below, recent=dates[t] >= half, final=me - 1,
                         fourth=me >= FOURTH, first=me >= FIRST, under=me < idx))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("cfg", sort=False).agg(
        구간=("final", "size"), 평균최종=("final", lambda x: f"{x.mean():+.1%}"),
        **{"4위(-5.64%↑)": ("fourth", lambda x: f"{x.mean():.0%}")}, **{"1위": ("first", lambda x: f"{x.mean():.1%}")},
        지수아래=("under", lambda x: f"{x.mean():.1%}"))


pd.set_option("display.unicode.east_asian_width", True)
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면]\n" + summary(df[df.below]).to_string())
print(f"\n[최근 절반]\n" + summary(df[df.recent]).to_string())
