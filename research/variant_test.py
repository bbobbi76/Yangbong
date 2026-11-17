# 고변동성 상위 5에 간단한 조건을 붙이면 남은 9거래일 1위·4위 확률이 오르나
#   python research/variant_test.py
# 시작 상태 11/17 마감(팀 -8.07%, 지수 -14.83%), 주식 95%, 왕복 비용 0.23%.
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, W, COST, BENCH = 9, 0.95, 0.0023, "069500"
NEED_FIRST = 1.0023 / 0.9193 - 1        # 1위(+0.23%)까지 필요한 수익
NEED_FOURTH = 0.96 / 0.9193 - 1         # 4위(-4%)까지
UNDER = 0.8517 / 0.9193 - 1             # 지수 아래로 떨어지는 초과수익 기준

lst = kospi_common().head(30)
names = dict(zip(lst["Code"], lst["Name"]))
close = pd.DataFrame({c: fdr.DataReader(c, "2023-01-01")["Close"] for c in list(names) + [BENCH]}).ffill()
ret = close.pct_change()


def pick(t):
    px = close.iloc[: t + 1]
    ok = [c for c in names if px[c].iloc[-121:].notna().all()]
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in ok}
    vol20 = {c: ret[c].iloc[t - 19: t + 1].std() for c in ok}
    beta = {c: ret[c].iloc[t - 59: t + 1].cov(ret[BENCH].iloc[t - 59: t + 1]) / ret[BENCH].iloc[t - 59: t + 1].var() for c in ok}
    ma20 = {c: px[c].iloc[-1] > px[c].iloc[-20:].mean() for c in ok}
    m1 = {c: px[c].iloc[-1] / px[c].iloc[-21] - 1 for c in ok}
    dd = {c: px[c].iloc[-1] / px[c].iloc[-60:].max() - 1 for c in ok}   # 60일 고점 대비 낙폭
    top = lambda d, k=5, pool=ok: sorted([c for c in pool if c in d], key=d.get, reverse=True)[:k]
    return {
        "고변동성 상위5 (현재)": top(vol),
        "고변동성 상위5, 20일선 위만": top(vol, pool=[c for c in ok if ma20[c]]) or top(vol),
        "고변동성 상위5, 1개월 상승만": top(vol, pool=[c for c in ok if m1[c] > 0]) or top(vol),
        "고변동성 상위5 (20일 기준)": top(vol20),
        "고변동성×베타 상위5": top({c: vol[c] * beta[c] for c in ok}),
        "고변동성 중 낙폭 큰 5 (반등 노림)": sorted(top(vol, 10), key=dd.get)[:5],
        "고변동성 상위3": top(vol, 3),
        "고변동성 상위4": top(vol, 4),
        "고변동성 상위6": top(vol, 6),
    }


rows, dates = [], close.index
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD):
    b = close[BENCH].iloc[t + HOLD] / close[BENCH].iloc[t] - 1
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for name, ps in pick(t).items():
        g = W * (np.mean([close[c].iloc[t + HOLD] / close[c].iloc[t] - 1 for c in ps]) - COST)
        rows.append(dict(strategy=name, ret=g, ex=g - b, below=below))
df = pd.DataFrame(rows)


def summary(d):
    return d.groupby("strategy", sort=False).agg(
        구간수=("ret", "size"), 평균=("ret", lambda x: f"{x.mean():+.1%}"),
        **{"1위": ("ret", lambda x: f"{(x >= NEED_FIRST).mean():.0%}")}, **{"4위": ("ret", lambda x: f"{(x >= NEED_FOURTH).mean():.0%}")},
        지수아래=("ex", lambda x: f"{(x < UNDER).mean():.1%}"))


pd.set_option("display.unicode.east_asian_width", True)
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면]\n" + summary(df[df.below]).to_string())
print("\n오늘 기준 종목:")
for n, ps in pick(len(dates) - 1).items():
    print(f"  {n}: " + ", ".join(names[c] for c in ps))
