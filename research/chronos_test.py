# 오픈소스 시계열 기반 모델(Amazon Chronos-Bolt)로 종목을 고르면 고변동성 상위 5보다 나은가
#   python research/chronos_test.py      (pip install chronos-forecasting torch)
# 시총 상위 30 각 종목의 과거 종가 256일로 9거래일 뒤 가격을 예측하고, 예측 상승률 상위 5를 동일비중으로 산다.
# 비교 지표는 short_horizon_test.py와 같다 (9거래일, 왕복 비용 0.23%, 주식 95%).
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import FinanceDataReader as fdr
from chronos import BaseChronosPipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent.listing import kospi_common

HOLD, COST, W, CTX, STEP = 9, 0.0023, 0.95, 256, 3   # STEP: 계산량 때문에 3거래일마다 시작
TARGET = (1 + 0.0023) / (1 - 0.0807) - 1             # 1위(+0.23%)를 넘는 데 필요한 수익 (-8.07%에서)
BENCH = "069500"

lst = kospi_common().head(30)
names = dict(zip(lst["Code"], lst["Name"]))
close = pd.DataFrame({c: fdr.DataReader(c, "2022-01-01")["Close"] for c in list(names) + [BENCH]}).ffill()
ret = close.pct_change()
pipe = BaseChronosPipeline.from_pretrained("amazon/chronos-bolt-small", device_map="cpu", torch_dtype=torch.float32)

rows, dates = [], close.index
for t in range(dates.searchsorted(pd.Timestamp("2024-01-01")), len(dates) - HOLD, STEP):
    ok = [c for c in names if close[c].iloc[t - CTX: t + 1].notna().all()]
    ctx = [torch.tensor(close[c].iloc[t - CTX + 1: t + 1].values, dtype=torch.float32) for c in ok]
    q, _ = pipe.predict_quantiles(ctx, prediction_length=HOLD, quantile_levels=[0.5, 0.9])
    pred = {c: float(q[i, -1, 0]) / close[c].iloc[t] - 1 for i, c in enumerate(ok)}       # 9일 뒤 중앙값 예측 수익
    upside = {c: float(q[i, -1, 1]) / close[c].iloc[t] - 1 for i, c in enumerate(ok)}     # 90% 분위 (크게 오를 여지)
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in ok}
    top = lambda d: sorted(d, key=d.get, reverse=True)[:5]
    bench = close[BENCH].iloc[t + HOLD] / close[BENCH].iloc[t] - 1
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for name, picks in {"고변동성 상위5 (현재)": top(vol), "Chronos 예측 수익 상위5": top(pred),
                        "Chronos 상단(90%) 상위5": top(upside)}.items():
        g = W * (np.mean([close[c].iloc[t + HOLD] / close[c].iloc[t] - 1 for c in picks]) - COST)
        rows.append(dict(date=dates[t], strategy=name, ret=g, excess=g - bench, below=below))

df = pd.DataFrame(rows)
need = (1 - 0.1483) / (1 - 0.0807) - 1  # 지수 아래로 떨어지려면 지수 대비 이만큼 더 나빠야 함


def summary(d):
    return d.groupby("strategy", sort=False).agg(
        구간수=("ret", "size"), 평균수익=("ret", lambda x: f"{x.mean():+.1%}"),
        **{f"1위 확률(+{TARGET:.1%}↑)": ("ret", lambda x: f"{(x >= TARGET).mean():.0%}")},
        **{"4위 확률(+4.4%↑)": ("ret", lambda x: f"{(x >= 0.044).mean():.0%}")},
        지수아래추락=("excess", lambda x: f"{(x < need).mean():.1%}"),
        지수이김=("excess", lambda x: f"{(x > 0).mean():.0%}"))


pd.set_option("display.unicode.east_asian_width", True)
print(f"9거래일 보유, {df.date.min():%Y-%m-%d} ~ {df.date.max():%Y-%m-%d}, {STEP}거래일 간격\n")
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면 (지수 < 60일 이평)]\n" + summary(df[df.below]).to_string())
