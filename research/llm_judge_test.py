# Gemini 모델별로 "악재" 판정이 실제 주가와 맞는가 (대형주, 키워드 필터에 안 걸린 공시만)
#   python research/llm_judge_test.py gemini-2.5-flash gemini-3.8-flash ...
# 시총 상위 30 공시(research/.cache) 중 BAD_KEYWORDS에 안 걸린 제목을 dart_filter와 같은 프롬프트로 판독하고,
# 악재로 본 공시와 아닌 공시의 다음 날 시가 매수 → 3·9거래일 KODEX 200 대비 초과수익을 비교한다.
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import FinanceDataReader as fdr
from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.listing import kospi_common
from agent.dart_filter import BAD_KEYWORDS

load_dotenv(ROOT / ".env")
CACHE = Path(__file__).parent / ".cache"
BENCH = "069500"
client = genai.Client(api_key=os.environ["GEMINI_KEY"].strip(), http_options={"timeout": 120_000})
PROMPT = ("다음은 코스피 상장사 DART 공시 제목 목록이다. 향후 며칠간 주가에 악재(희석, 재무 악화, 법적 리스크, "
          "지배구조 불확실성 등)인 공시만 골라라. 판단이 애매하면 악재가 아니다.\n"
          'JSON으로만 답하라: {"bad": [악재 공시의 번호, ...]}\n\n')

codes = list(kospi_common().head(30)["Code"])
disc = pd.DataFrame([d for f in sorted(CACHE.glob("dart_*.json")) for d in json.loads(f.read_text(encoding="utf-8"))])
disc = disc[disc.stock_code.isin(codes)].drop_duplicates()
disc = disc[~disc.report_nm.apply(lambda t: any(k in t for k in BAD_KEYWORDS))]
disc["title"] = disc.report_nm.str.replace(r"\s+", " ", regex=True).str.strip()
titles = sorted(disc.title.unique())
px = {c: fdr.DataReader(c, "2025-12-01")[["Open", "Close"]] for c in codes + [BENCH]}


def excess(code, day, hold):
    d, b = px[code], px[BENCH]
    i = d.index.searchsorted(pd.Timestamp(day), side="right")
    if i + hold > len(d) - 1:
        return None
    t0, t1 = d.index[i], d.index[i + hold - 1]
    return d.Close.loc[t1] / d.Open.loc[t0] - 1 - (b.Close.loc[t1] / b.Open.loc[t0] - 1)


def judge(model):
    """악재로 본 제목 집합. 덩어리별로 저장해 두고 이어서 판독. 다 못 받으면 None"""
    path = CACHE / f"judge_{model}.json"
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")))
    part_path = CACHE / f"judge_{model}.part.json"
    part = json.loads(part_path.read_text(encoding="utf-8")) if part_path.exists() else {}
    for i in range(0, len(titles), 60):  # 60개씩 나눠 판독
        chunk = titles[i:i + 60]
        if str(i) in part:
            continue
        for attempt in range(4):
            try:
                r = client.models.generate_content(model=model, contents=PROMPT + "\n".join(f"{j}. {t}" for j, t in enumerate(chunk)),
                                                   config={"response_mime_type": "application/json"})
                part[str(i)] = [chunk[j] for j in json.loads(r.text)["bad"] if 0 <= j < len(chunk)]
                part_path.write_text(json.dumps(part, ensure_ascii=False), encoding="utf-8")
                print(f"  {model} {i + len(chunk)}/{len(titles)}", flush=True)
                break
            except Exception as e:
                print(f"  {model} 재시도 {attempt + 1}: {str(e)[:80]}", flush=True)
                time.sleep(20 * (attempt + 1))
    if len(part) < (len(titles) + 59) // 60:
        print(f"  {model}: {len(part)}/{(len(titles) + 59) // 60} 덩어리만 받음 → 제외", flush=True)
        return None
    bad = {t for v in part.values() for t in v}
    path.write_text(json.dumps(sorted(bad), ensure_ascii=False), encoding="utf-8")
    return bad


disc["ex3"] = [excess(c, d, 3) for c, d in zip(disc.stock_code, disc.rcept_dt)]
disc["ex9"] = [excess(c, d, 9) for c, d in zip(disc.stock_code, disc.rcept_dt)]
print(f"키워드 미해당 공시 {len(disc):,}건, 고유 제목 {len(titles)}개\n")
rows = []
for m in sys.argv[1:]:
    t0 = time.time()
    bad = judge(m)
    if bad is None:
        continue
    d = disc.assign(flag=disc.title.isin(bad))
    for flag, g in d.groupby("flag"):
        rows.append({"모델": m, "판정": "악재" if flag else "악재 아님", "건수": len(g),
                     "3일 초과": f"{g.ex3.mean():+.2%}", "9일 초과": f"{g.ex9.mean():+.2%}",
                     "9일 중앙값": f"{g.ex9.median():+.2%}", "9일 -5%↓ 비율": f"{(g.ex9 < -0.05).mean():.0%}"})
    print(f"{m}: 악재 판정 제목 {len(bad)}개 ({time.time() - t0:.0f}s) 예: {sorted(bad)[:6]}")
pd.set_option("display.unicode.east_asian_width", True)
print("\n" + pd.DataFrame(rows).to_string(index=False))
