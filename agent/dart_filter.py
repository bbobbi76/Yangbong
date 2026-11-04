# 가설 A: 최근 DART 공시로 매수 금지 종목을 거르는 리스크 필터
# research 결과 두 해 모두 일관된 것: 악재·공급계약·합병·주식소각 공시 종목은 이후 3일간 지수보다 약함
import os
import json
import time
from datetime import date, timedelta
import requests

# 제목에 이 단어가 있으면 LLM 없이 바로 제외
BAD_KEYWORDS = ["유상증자", "전환사채", "신주인수권부사채", "교환사채", "합병", "분할", "주식소각", "감자",
                "공급계약", "횡령", "배임", "소송", "거래정지", "관리종목", "불성실공시", "회생", "부도"]
GEMINI_MODEL = "gemini-2.5-flash"


def fetch(days=3, types=("B", "I")):
    """최근 days일 코스피 공시 (B: 주요사항보고, I: 거래소공시)"""
    key = os.environ["DART_KEY"].strip()
    bgn, end = (date.today() - timedelta(days=days)).strftime("%Y%m%d"), date.today().strftime("%Y%m%d")
    rows = []
    for ty in types:
        page = 1
        while True:
            r = requests.get("https://opendart.fss.or.kr/api/list.json", params=dict(
                crtfc_key=key, bgn_de=bgn, end_de=end, pblntf_ty=ty,
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


def llm_bad(titles):
    """키워드에 안 걸린 공시 제목을 Gemini가 판독. 악재로 본 제목 집합을 반환 (키 없으면 빈 집합)"""
    if not titles or not os.getenv("GEMINI_KEY"):
        return set()
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_KEY"].strip())
    prompt = ("다음은 코스피 상장사 DART 공시 제목 목록이다. 향후 며칠간 주가에 악재(희석, 재무 악화, 법적 리스크, "
              "지배구조 불확실성 등)인 공시만 골라라. 판단이 애매하면 악재가 아니다.\n"
              'JSON으로만 답하라: {"bad": [악재 공시의 번호, ...]}\n\n'
              + "\n".join(f"{i}. {t}" for i, t in enumerate(titles)))
    try:
        r = client.models.generate_content(model=GEMINI_MODEL, contents=prompt,
                                           config={"response_mime_type": "application/json"})
        return {titles[i] for i in json.loads(r.text)["bad"] if 0 <= i < len(titles)}
    except Exception as e:  # 503 과부하 등 → 키워드 필터만으로 진행
        print(f"! Gemini 판독 실패, 키워드 필터만 적용: {str(e)[:120]}")
        return set()


def blocked(symbols, days=3):
    """symbols 중 최근 공시 때문에 보유·매수하면 안 되는 종목 → {symbol: 사유}"""
    symbols = set(symbols)
    disc = [d for d in fetch(days) if d["stock_code"] in symbols]
    out, rest = {}, []
    for d in disc:
        kw = next((k for k in BAD_KEYWORDS if k in d["report_nm"]), None)
        if kw:
            out[d["stock_code"]] = f"{d['report_nm']} [키워드: {kw}]"
        else:
            rest.append(d)
    bad_titles = llm_bad(sorted({d["report_nm"] for d in rest}))
    for d in rest:
        if d["report_nm"] in bad_titles and d["stock_code"] not in out:
            out[d["stock_code"]] = f"{d['report_nm']} [LLM 악재]"
    return out


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    print(blocked(sys.argv[1:]))
