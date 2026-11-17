# 공시 필터(dart_filter.BAD_KEYWORDS)가 대형주에서도 맞는가
#   python research/filter_largecap_test.py   (surge_exit_test.py가 research/.cache에 받아 둔 공시 사용)
# 가설 A 검증은 코스피 전체(대부분 중소형주)였다. 실전 기본 포트폴리오는 시총 상위 30만 다루므로,
# 그 안에서 키워드별로 공시 다음 날 시가 매수 → 3·9거래일 뒤 종가의 KODEX 200 대비 초과수익을 다시 본다.
import json
import sys
from pathlib import Path

import pandas as pd
import FinanceDataReader as fdr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.listing import kospi_common
from agent.dart_filter import BAD_KEYWORDS

BENCH = "069500"
CACHE = Path(__file__).parent / ".cache"

codes = list(kospi_common().head(30)["Code"])
disc = pd.DataFrame([d for f in sorted(CACHE.glob("dart_*.json")) for d in json.loads(f.read_text(encoding="utf-8"))])
disc = disc[disc["stock_code"].isin(codes)].drop_duplicates()
disc["date"] = pd.to_datetime(disc["rcept_dt"])
px = {c: fdr.DataReader(c, "2025-12-01")[["Open", "Close"]] for c in codes + [BENCH]}
print(f"시총 상위 30 공시 {len(disc):,}건 ({disc.date.min():%Y-%m-%d} ~ {disc.date.max():%Y-%m-%d})\n")


def excess(code, day, hold):
    d, b = px[code], px[BENCH]
    i = d.index.searchsorted(day, side="right")      # 공시 다음 거래일
    if i + hold > len(d) - 1:
        return None
    t0, t1 = d.index[i], d.index[i + hold - 1]
    r = d.Close.loc[t1] / d.Open.loc[t0] - 1
    rb = b.Close.loc[t1] / b.Open.loc[t0] - 1
    return r - rb


rows = []
for _, d in disc.iterrows():
    kw = next((k for k in BAD_KEYWORDS if k in d.report_nm), None)
    for hold in (3, 9):
        e = excess(d.stock_code, d.date, hold)
        if e is not None:
            rows.append(dict(kw=kw or "(키워드 없음)", hold=hold, ex=e, title=d.report_nm, code=d.stock_code))
df = pd.DataFrame(rows)
t = df.pivot_table(index="kw", columns="hold", values="ex", aggfunc=["count", "mean", "median"])
t.columns = [f"{a}_{h}일" for a, h in t.columns]
for c in [c for c in t.columns if not c.startswith("count")]:
    t[c] = t[c].map(lambda v: f"{v:+.2%}")
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)
print("키워드별 공시 다음 날 시가 매수 → KODEX 200 대비 초과수익 (시총 상위 30)\n")
print(t.sort_values("count_3일", ascending=False).to_string())
print("\n공급계약 공시 예시:")
print(df[(df.kw == "공급계약") & (df.hold == 9)].sort_values("ex").to_string(columns=["code", "title", "ex"], max_rows=12))
