# 금융 특화 오픈소스 기반 모델(Kronos, 2025)로 종목을 고르면 고변동성 상위 5보다 나은가
#   git clone https://github.com/shiyu-coder/Kronos  (모델 코드는 pip 패키지가 아님)
#   python research/kronos_test.py <Kronos 저장소 경로>
# 시총 상위 30 각 종목의 일봉 OHLCV 200일로 9거래일 뒤 종가를 예측하고, 예측 상승률 상위 5를 동일비중으로 산다.
# 지표는 chronos_test.py와 같다.
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import FinanceDataReader as fdr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, sys.argv[1])
from agent.listing import kospi_common
from model import Kronos, KronosTokenizer, KronosPredictor

#   추가 인자: [시작일 간격 보유일 종목수]  예) python research/kronos_test.py <경로> 2025-06-01 6 6 4
START = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
STEP = int(sys.argv[3]) if len(sys.argv) > 3 else 3
HOLD = int(sys.argv[4]) if len(sys.argv) > 4 else 9
K = int(sys.argv[5]) if len(sys.argv) > 5 else 5
COST, W, CTX, SAMPLES = 0.0023, 0.95, 200, 5
TARGET = (1 + 0.0023) / (1 - 0.0807) - 1
BENCH = "069500"
torch.manual_seed(0)

lst = kospi_common().head(30)
names = dict(zip(lst["Code"], lst["Name"]))
ohlcv = {c: fdr.DataReader(c, "2022-01-01")[["Open", "High", "Low", "Close", "Volume"]] for c in names}
close = pd.DataFrame({c: d["Close"] for c, d in ohlcv.items()})
close[BENCH] = fdr.DataReader(BENCH, "2022-01-01")["Close"]
close = close.ffill()
ret = close.pct_change()

tok = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
pred = KronosPredictor(model, tok, device="cpu", max_context=512)

rows, dates = [], close.index
for t in range(dates.searchsorted(pd.Timestamp(START)), len(dates) - HOLD, STEP):
    day = dates[t]
    ok, dfs, xs, ys = [], [], [], []
    for c in names:
        d = ohlcv[c].loc[:day].tail(CTX)
        if len(d) < CTX or d.index[-1] != day or d.isna().any().any():
            continue
        x = d.rename(columns=str.lower)
        x["amount"] = x["close"] * x["volume"]
        ok.append(c)
        dfs.append(x.reset_index(drop=True))
        xs.append(pd.Series(d.index))
        ys.append(pd.Series(pd.bdate_range(day + pd.Timedelta(days=1), periods=HOLD)))
    out = pred.predict_batch(dfs, xs, ys, pred_len=HOLD, T=1.0, top_p=0.9, sample_count=SAMPLES, verbose=False)
    exp = {c: float(o["close"].iloc[-1]) / close[c].loc[day] - 1 for c, o in zip(ok, out)}
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in ok}
    top = lambda dct: sorted(dct, key=dct.get, reverse=True)[:K]
    bench = close[BENCH].iloc[t + HOLD] / close[BENCH].iloc[t] - 1
    below = close[BENCH].iloc[t] <= close[BENCH].iloc[t - 59: t + 1].mean()
    for name, picks in {f"고변동성 상위{K} (현재)": top(vol), f"Kronos 예측 수익 상위{K}": top(exp),
                        f"고변동성 상위{K*2} 중 Kronos 상위{K}": top({c: exp[c] for c in sorted(vol, key=vol.get, reverse=True)[:K * 2]})}.items():
        g = W * (np.mean([close[c].iloc[t + HOLD] / close[c].iloc[t] - 1 for c in picks]) - COST)
        rows.append(dict(date=day, strategy=name, ret=g, excess=g - bench, below=below))
    print(f"{day:%Y-%m-%d}", end=" ", flush=True)

df = pd.DataFrame(rows)
need = (1 - 0.1483) / (1 - 0.0807) - 1


def summary(d):
    return d.groupby("strategy", sort=False).agg(
        구간수=("ret", "size"), 평균수익=("ret", lambda x: f"{x.mean():+.1%}"),
        **{f"1위 확률(+{TARGET:.1%}↑)": ("ret", lambda x: f"{(x >= TARGET).mean():.0%}")},
        **{"4위 확률(+4.4%↑)": ("ret", lambda x: f"{(x >= 0.044).mean():.0%}")},
        지수아래추락=("excess", lambda x: f"{(x < need).mean():.1%}"),
        지수이김=("excess", lambda x: f"{(x > 0).mean():.0%}"))


pd.set_option("display.unicode.east_asian_width", True)
print(f"\n\n9거래일 보유, {df.date.min():%Y-%m-%d} ~ {df.date.max():%Y-%m-%d}, {STEP}거래일 간격\n")
print("[전체]\n" + summary(df).to_string())
print("\n[하락 국면 (지수 < 60일 이평)]\n" + summary(df[df.below]).to_string())
