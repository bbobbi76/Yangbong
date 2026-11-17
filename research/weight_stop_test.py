# 굳히기(+2%)·안전선 3%p·4종목 위에서 C 비중(90/95/100%)과 종목별 손절(-7/-10%, 종가 기준) 비교
#   python research/weight_stop_test.py  (lock_test.py의 데이터 준비 부분을 재사용)
from pathlib import Path
import numpy as np, pandas as pd
src = open(str(Path(__file__).with_name("lock_test.py")), encoding="utf-8").read()
src = src[:src.index("def run(")]
g = {"__file__": str(Path(__file__).with_name("lock_test.py"))}
exec(compile(src, g["__file__"], "exec"), g)
close, ret, names = g["close"], g["ret"], g["names"]
COST, SELL, GAP, B = 0.0023, 0.00215, 3.0, "069500"
def run(t, W, stop, lock=2.0):
    vol = {c: ret[c].iloc[t - 59: t + 1].std() for c in names if close[c].iloc[t - 60: t + 1].notna().all()}
    picks = sorted(vol, key=vol.get, reverse=True)[:4]
    alive = {c: True for c in picks}
    me, idx, mode = 0.9193 * (1 - W * COST / 2), 0.8517, "mom"
    for k in range(1, 10):
        b = close[B].iloc[t + k] / close[B].iloc[t + k - 1] - 1
        if mode == "mom":
            r = W * np.mean([close[c].iloc[t + k] / close[c].iloc[t + k - 1] - 1 if alive[c] else 0 for c in picks])
        else:
            r = {"cash": 0.0, "index": W * b}[mode]
        me, idx = me * (1 + r), idx * (1 + b)
        if k == 9: break
        if mode != "cash" and me >= 1 + lock / 100: mode, me = "cash", me * (1 - W * SELL)
        elif mode == "mom" and (me - idx) * 100 < GAP: mode, me = "index", me * (1 - W * COST)
        elif mode == "mom" and stop:
            for c in picks:
                if alive[c] and close[c].iloc[t + k] / close[c].iloc[t] - 1 <= -stop:
                    alive[c] = False; me *= 1 - W / 4 * SELL
    return me, idx
dates = close.index; start = dates.searchsorted(pd.Timestamp("2024-01-01")); half = dates[len(dates) // 2 + 120]
rows = []
for t in range(start, len(dates) - 9):
    below = close[B].iloc[t] <= close[B].iloc[t - 59: t + 1].mean()
    for cfg, W, stop in [("W95", .95, None), ("W100", .995, None), ("W90", .90, None), ("W95 stop7", .95, .07), ("W95 stop10", .95, .10)]:
        me, idx = run(t, W, stop)
        rows.append(dict(cfg=cfg, below=below, recent=dates[t] >= half, first=me >= 1.0023, under=me < idx))
df = pd.DataFrame(rows)
f = lambda d: d.groupby("cfg", sort=False)[["first", "under"]].mean().round(3)
print("[전체]\n", f(df)); print("[하락]\n", f(df[df.below])); print("[최근]\n", f(df[df.recent]))
