# 가설 A 검증: "LLM이 호재로 분류한 DART 공시 종목은 공시 후 1~5일간 KOSPI200(KODEX 200)보다 수익률이 높다"
# Colab에서 셀(# %%) 단위로 복붙해서 실행하면 됨

# %% [1] 설치
# !pip install -q finance-datareader google-genai scipy

# %% [2] 설정
# 키는 Colab 왼쪽 🔑(보안 비밀)에 DART_KEY, GEMINI_KEY 이름으로 등록 → 코드/깃허브에 키가 안 남음
from google.colab import userdata
DART_KEY = userdata.get("DART_KEY").strip()
GEMINI_MODEL = "gemini-2.5-flash"   # AI Studio에서 쓸 수 있는 모델명으로 바꿔도 됨

START, END = "20260401", "20260930"  # 검증 기간 (최근 6개월)
PBLNTF_TYPES = ["B", "I"]            # B: 주요사항보고(자사주·유상증자 등), I: 거래소공시(공급계약·실적변동 등)
HOLD_DAYS = [1, 3, 5]                # 보유 기간(거래일)
BENCH = "069500"                     # KODEX 200 = AQuA 리더보드 기준선

import time, json, re
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from scipy import stats

# %% [3] DART 공시 수집
def month_ranges(start, end):
    # corp_code 없이 조회하면 DART가 검색기간을 3개월로 제한해서 월 단위로 쪼갬
    s, e = datetime.strptime(start, "%Y%m%d"), datetime.strptime(end, "%Y%m%d")
    while s <= e:
        nxt = (s.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield s.strftime("%Y%m%d"), min(nxt - timedelta(days=1), e).strftime("%Y%m%d")
        s = nxt

def fetch_disclosures(bgn, end, ty):
    rows, page = [], 1
    while True:
        r = requests.get("https://opendart.fss.or.kr/api/list.json", params=dict(
            crtfc_key=DART_KEY, bgn_de=bgn, end_de=end, pblntf_ty=ty,
            corp_cls="Y", page_no=page, page_count=100), timeout=30).json()
        if r["status"] == "013":  # 조회된 데이터 없음
            break
        if r["status"] != "000":
            raise RuntimeError(r)
        rows += r["list"]
        if page >= r["total_page"]:
            break
        page += 1
        time.sleep(0.1)
    return rows

rows = []
for ty in PBLNTF_TYPES:
    for b, e in month_ranges(START, END):
        rows += fetch_disclosures(b, e, ty)
        print(ty, b, e, len(rows))

disc = pd.DataFrame(rows)
disc = disc[disc["stock_code"].str.strip() != ""]
disc = disc[~disc["report_nm"].str.contains("정정|첨부")]  # 정정공시는 새 정보가 아님
disc["title"] = disc["report_nm"].str.replace(r"\s+", "", regex=True)
disc["rcept_dt"] = pd.to_datetime(disc["rcept_dt"])
disc.to_csv("disclosures.csv", index=False)
print("공시 수:", len(disc), "/ 고유 제목 수:", disc["title"].nunique())

# %% [4] Gemini로 공시 제목 분류 (고유 제목만 분류해서 비용 절약)
from google import genai
client = genai.Client(api_key=userdata.get("GEMINI_KEY"))

PROMPT = """너는 한국 주식 애널리스트다. 아래는 코스피 상장사의 공시 제목 목록이다.
각 공시가 발표 직후 해당 기업 주가에 미칠 단기 영향을 판단해라.
- label: "호재" / "악재" / "중립" 중 하나 (영향이 불분명하거나 일상적인 공시면 중립)
- category: 공시 유형을 2~6글자로 (예: 자사주매입, 공급계약, 유상증자, 실적변동, 소송, 기타)
입력과 같은 순서로 JSON 배열만 출력: [{"id":0,"label":"...","category":"..."}, ...]

"""

def classify(titles, batch=50):
    out = {}
    for i in range(0, len(titles), batch):
        chunk = titles[i:i + batch]
        text = PROMPT + "\n".join(f"{j}: {t}" for j, t in enumerate(chunk))
        resp = client.models.generate_content(
            model=GEMINI_MODEL, contents=text,
            config={"response_mime_type": "application/json", "temperature": 0})
        for item in json.loads(resp.text):
            out[chunk[item["id"]]] = (item["label"], item["category"])
        print(f"{min(i + batch, len(titles))}/{len(titles)}")
        time.sleep(1)
    return out

labels = classify(sorted(disc["title"].unique()))
disc["label"] = disc["title"].map(lambda t: labels.get(t, ("중립", "기타"))[0])
disc["category"] = disc["title"].map(lambda t: labels.get(t, ("중립", "기타"))[1])
disc.to_csv("disclosures_labeled.csv", index=False)
print(disc["label"].value_counts())

# %% [5] 주가 수집 + 이벤트별 초과수익 계산
px_start = pd.to_datetime(START) - pd.Timedelta(days=10)
px_end = pd.to_datetime(END) + pd.Timedelta(days=20)  # D+5까지 필요
bench = fdr.DataReader(BENCH, px_start, px_end)

# 같은 종목·같은 날·같은 라벨은 하나의 이벤트로 취급
events = disc.drop_duplicates(["stock_code", "rcept_dt", "label"])

prices = {}
for code in events["stock_code"].unique():
    try:
        prices[code] = fdr.DataReader(code, px_start, px_end)
    except Exception as ex:
        print("가격 실패", code, ex)

# %% [5-2] 이벤트별 초과수익 계산 (주가 재다운로드 없이 이 셀만 다시 돌려도 됨)
# 거래정지일은 시가가 0으로 들어와서 수익률이 inf가 됨 → 제외
prices = {k: v[v["Open"] > 0] for k, v in prices.items()}
bench = bench[bench["Open"] > 0]

def event_returns(px, rcept_dt):
    # 공시 시각이 장중/장후로 섞여 있어서 보수적으로 '다음 거래일 시가 매수'로 가정
    i = px.index.searchsorted(rcept_dt, side="right")
    res = {}
    for h in HOLD_DAYS:
        j = i + h - 1
        if j >= len(px):
            return None
        entry, exit_ = px.index[i], px.index[j]
        if entry not in bench.index or exit_ not in bench.index:
            return None
        r = px["Close"].iloc[j] / px["Open"].iloc[i] - 1
        b = bench.loc[exit_, "Close"] / bench.loc[entry, "Open"] - 1
        res[f"ex_{h}d"] = (r - b) * 100  # 초과수익(%p)
    return res

records = []
for _, ev in events.iterrows():
    px = prices.get(ev["stock_code"])
    if px is None or px.empty:
        continue
    r = event_returns(px, ev["rcept_dt"])
    if r:
        records.append({**ev[["corp_name", "stock_code", "rcept_dt", "title", "label", "category"]].to_dict(), **r})

res = pd.DataFrame(records)
res.to_csv("event_returns.csv", index=False)
print("분석 이벤트 수:", len(res))

# %% [6] 결과 요약
def summarize(df, by):
    rows = []
    for key, g in df.groupby(by):
        for h in HOLD_DAYS:
            x = g[f"ex_{h}d"].dropna()
            if len(x) < 5:
                continue
            rows.append({by: key, "보유일": h, "건수": len(x),
                         "평균초과수익(%p)": round(x.mean(), 2),
                         "중앙값(%p)": round(x.median(), 2),
                         "승률(%)": round((x > 0).mean() * 100, 1),
                         "p-value": round(stats.ttest_1samp(x, 0).pvalue, 3)})
    return pd.DataFrame(rows)

print("=== 라벨별 ===")
print(summarize(res, "label").to_string(index=False))

print("\n=== 호재 공시 유형별 (10건 이상) ===")
good = res[res["label"] == "호재"]
cat = summarize(good, "category")
print(cat[cat["건수"] >= 10].sort_values(["보유일", "평균초과수익(%p)"], ascending=[True, False]).to_string(index=False))
