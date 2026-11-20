# 급락 직후 남은 6거래일: 고변동성 상위 4 vs 단기 반등·베타 기반 선정 (안전선 3%p 포함)
#   python research/rebound_pick_test.py
# 시작 11/20 장중(팀 -11.68%, KODEX 200 -16.53%), 4위 AITrader -5.64%. "급락 직후" = 시작일 KODEX 하루 -2% 이하.
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST, GAP, K, BENCH = 6, 0.95, 0.0023, 3.0, 4, "069500"
ME0, IDX0, FOURTH = 0.8832, 0.8347, 0.9436
codes = list(kospi_common().head(30)["Code"])
raw = {c: fdr.DataReader(c, "2023-01-01") for c in codes + [BENCH]}
close = pd.DataFrame({c: d["Close"] for c, d in raw.items()}).ffill()
amt = pd.DataFrame({c: d["Close"] * d["Volume"] for c, d in raw.items() if c != BENCH}).reindex(close.index)
ret = close.pct_change()


def picks(t):
    ok = [c for c in codes if close[c].iloc[t - 60: t + 1].notna().all()]
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in ok}
    rb = ret[BENCH].iloc[t - 59: t + 1]
    beta = {c: ret[c].iloc[t - 59: t + 1].cov(rb) / rb.var() for c in ok}
    r5 = {c: close[c].iloc[t] / close[c].iloc[t - 5] - 1 for c in ok}
    r1 = {c: ret[c].iloc[t] for c in ok}
    surge = {c: amt[c].iloc[t - 4: t + 1].mean() / amt[c].iloc[t - 59: t + 1].mean() for c in ok}
    top = lambda d, pool=ok: sorted(pool, key=d.get, reverse=True)[:K]
    v10 = top(vol, ok)[:0] or sorted(ok, key=vol.get, reverse=True)[:10]
    return {
        "고변동성 상위4 (현재)": top(vol),
        "베타 상위4": top(beta),
        "고변동성10 중 5일 낙폭 큰 4": sorted(v10, key=r5.get)[:K],
        "고변동성10 중 당일 낙폭 큰 4": sorted(v10, key=r1.get)[:K],
        "고변동성10 중 5일 강한 4": sorted(v10, key=r5.get, reverse=True)[:K],
        "고변동성10 중 거래대금 급증 4": sorted(v10, key=surge.get, reverse=True)[:K],
    }


def run(t, ps):
    me, idx, mode = ME0 * (1 - W * COST), IDX0, "mom"
    for d in range(1, HOLD + 1):
        b = close[BENCH].iloc[t + d] / close[BENCH].iloc[t + d - 1] - 1
        r = W * b if mode == "index" else W * np.mean([close[c].iloc[t + d] / close[c].iloc[t + d - 1] - 1 for c in ps])
        me, idx = me * (1 + r), idx * (1 + b)
        if d < HOLD and mode == "mom" and (me - idx) * 100 < GAP:
            mode, me = "index", me * (1 - W * COST)
    return me, idx


dates = close.index
rows = []
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    crash = ret[BENCH].iloc[t] <= -0.02
    for name, ps in picks(t).items():
        me, idx = run(t, ps)
        rows.append(dict(cfg=name, below=below, crash=crash, fourth=me >= FOURTH, under=me < idx, final=me - 1))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("cfg", sort=False).agg(
        n=("final", "size"), 평균=("final", lambda x: f"{x.mean():+.1%}"),
        **{"4위": ("fourth", lambda x: f"{x.mean():.0%}")}, 지수아래=("under", lambda x: f"{x.mean():.1%}"))


pd.set_option("display.unicode.east_asian_width", True)
print(pd.concat({"전체": summary(df), "하락 국면": summary(df[df.below]), "급락 직후": summary(df[df.crash])}, axis=1).to_string())
print("\n오늘 기준:")
names = dict(zip(kospi_common()["Code"], kospi_common()["Name"]))
for n, ps in picks(len(dates) - 1).items():
    print(f"  {n}: " + ", ".join(names.get(c, c) for c in ps))
