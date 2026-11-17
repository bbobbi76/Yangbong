# 굳히기(+2%) 있는 상태에서 종목 수(3~5)와 안전선(2~4%p) 조합 비교
#   python research/lock_combo_test.py  (lock_test.py의 run()을 재사용)
from pathlib import Path
import sys, runpy
import importlib.util, pandas as pd
spec = importlib.util.spec_from_file_location("lt", str(Path(__file__).with_name("lock_test.py")))
src = open(spec.origin, encoding="utf-8").read()
src = src[:src.index("rows, dates = [], close.index")]
g = {"__file__": spec.origin}
exec(compile(src, spec.origin, "exec"), g)
close, dates = g["close"], g["close"].index
rows = []
start = dates.searchsorted(pd.Timestamp("2024-01-01"))
half = dates[len(dates) // 2 + 120]
for K in (3, 4, 5):
    for GAP in (2.0, 3.0, 4.0):
        g["K"], g["GAP"] = K, GAP
        for t in range(start, len(dates) - 9):
            below = close["069500"].iloc[t] <= close["069500"].iloc[t - 59: t + 1].mean()
            me, idx, mode = g["run"](t, 2.0)
            rows.append(dict(cfg=f"K{K} gap{GAP:g}", below=below, recent=dates[t] >= half,
                             first=me >= 1.0023, f2=me >= 1.02, under=me < idx))
df = pd.DataFrame(rows)
f = lambda d: d.groupby("cfg", sort=False).agg(n=("first", "size"), first=("first", "mean"), f2=("f2", "mean"), under=("under", "mean")).round(3)
print("[전체]\n", f(df)); print("[하락]\n", f(df[df.below])); print("[최근 절반]\n", f(df[df.recent]))
