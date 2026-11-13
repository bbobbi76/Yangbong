# 급등주 전략(형민 Case 3) 일봉 재현 + 수익 보호(익절·트레일링) 규칙 비교
#   python research/surge_exit_test.py      (.env의 DART_KEY 필요, 공시는 research/.cache에 저장)
# 원 백테스트 코드가 저장소에 없어서 research/dart_sangtta_strategy_report.md의 규칙대로 다시 짰다.
#   유니버스: 현재 시총 상위 200 코스피 보통주 (KOSPI200 구성종목 대용)
#   신호: 고가가 전일 종가 +10% 이상 & 전일·당일 DART 호재 공시 (악재·정정 공시가 같이 있으면 제외)
#   진입가: max(시가, 전일 종가 × 1.10)
#   당일: 저가가 진입가 -5% 이하면 손절, 아니면 음봉이면서 진입가 아래 마감 시 종가 청산
#   다음 날부터: 음봉(종가 < 시가)인 첫날 종가 청산, 최대 15거래일
#   비용: 왕복 0.23%. 초과수익 = 같은 기간 KODEX 200(전일 종가 → 청산일 종가) 대비
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import FinanceDataReader as fdr
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.listing import kospi_common

load_dotenv(ROOT / ".env")
CACHE = Path(__file__).parent / ".cache"
CACHE.mkdir(exist_ok=True)

PRICE_FROM, END = "2025-12-01", "2026-11-12"
PERIODS = {"재현 (26.01~09, 원 보고서 기간)": ("2026-01-01", "2026-09-30"),
           "최근 (26.10~11.12, 조정장)": ("2026-10-01", END)}
TRIGGER, STOP, COST, MAX_HOLD = 0.10, -0.05, 0.0023, 15
BENCH = "069500"
GOOD = ["자기주식취득", "자기주식 취득", "신탁계약체결", "단일판매", "공급계약", "영업(잠정)실적", "잠정실적", "신규시설투자"]
BAD = ["유상증자", "전환사채", "신주인수권부사채", "교환사채", "합병", "분할", "주식소각", "감자", "정정", "철회", "해지"]


def dart(bgn, end):
    """코스피 B·I·F 공시, 월 단위로 받아 캐시"""
    path = CACHE / f"dart_{bgn}_{end}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for ty in ["B", "I", "F"]:
        page = 1
        while True:
            r = requests.get("https://opendart.fss.or.kr/api/list.json", params=dict(
                crtfc_key=os.environ["DART_KEY"].strip(), bgn_de=bgn, end_de=end, pblntf_ty=ty,
                corp_cls="Y", page_no=page, page_count=100), timeout=30).json()
            if r["status"] == "013":
                break
            if r["status"] != "000":
                raise RuntimeError(r)
            rows += [{k: d[k] for k in ("stock_code", "report_nm", "rcept_dt")} for d in r["list"]]
            if page >= r["total_page"]:
                break
            page += 1
            time.sleep(0.1)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return rows


def months(start, end):
    s, e = datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")
    while s <= e:
        nxt = (s.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield s.strftime("%Y%m%d"), min(nxt - timedelta(days=1), e).strftime("%Y%m%d")
        s = nxt


def load_prices(codes):
    path = CACHE / f"prices_{END}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    data = {c: fdr.DataReader(c, PRICE_FROM, END)[["Open", "High", "Low", "Close"]] for c in codes + [BENCH]}
    pd.to_pickle(data, path)
    return data


# ---- 데이터
codes = list(kospi_common().head(200)["Code"])
px = load_prices(codes)
disc = pd.DataFrame([d for b, e in months("2025-12-25", END) for d in dart(b, e)])
disc["date"] = pd.to_datetime(disc["rcept_dt"])
disc["good"] = disc["report_nm"].apply(lambda t: any(k in t for k in GOOD))
disc["bad"] = disc["report_nm"].apply(lambda t: any(k in t for k in BAD))
by_day = disc.groupby(["stock_code", "date"]).agg(good=("good", "any"), bad=("bad", "any"))
print(f"공시 {len(disc):,}건, 종목 {len(codes)}개\n")

bench = px[BENCH]["Close"]


# ---- 청산 규칙: 보유 중인 날마다 (진입 후 k일째 봉, 상태) → 청산가 또는 None
def make_rule(tp=None, trail=None, lock=None):
    """tp: 고가가 진입가 +tp 닿으면 그 가격에 익절
    trail: 전일까지 최고 고가 대비 trail 만큼 빠지면 청산 (시가가 이미 아래면 시가)
    lock: (도달, 보장) 전일까지 고가가 +도달 이상 갔으면, 진입가 +보장 아래로 내려올 때 청산"""
    def rule(k, bar, entry, peak):
        o, h, l, c = bar.Open, bar.High, bar.Low, bar.Close
        if k == 0:  # 진입 당일 (원 규칙 그대로: 장중 순서를 알 수 없어 추가 규칙은 다음 날부터)
            # 일봉으론 저가가 진입 전인지 후인지 모른다. 시가로 진입(갭 상승)했으면 저가는 전부 진입 후,
            # 장중에 +10%를 뚫고 진입했으면 저가는 진입 전일 수 있어 종가가 손절선 아래일 때만 손절로 본다.
            gap = o >= entry
            if (gap and l <= entry * (1 + STOP)) or c <= entry * (1 + STOP):
                return entry * (1 + STOP), "손절"
            if c < o and c < entry:
                return c, "당일 음봉"
            return None
        levels = []
        if trail is not None:
            levels.append((peak * (1 - trail), "트레일링"))
        if lock is not None and peak >= entry * (1 + lock[0]):
            levels.append((entry * (1 + lock[1]), "수익 보호"))
        for lv, why in sorted(levels, reverse=True):  # 가장 높은 보호선부터
            if l <= lv:
                return min(o, lv), why
        if tp is not None and h >= entry * (1 + tp):
            return max(o, entry * (1 + tp)), "익절"
        if c < o:
            return c, "음봉"
        if k >= MAX_HOLD:
            return c, "최대보유"
        return None
    return rule


def run(rule, start, end, max_entry=None):
    trades = []
    for code in codes:
        d = px[code]
        d = d[d.index >= pd.Timestamp(PRICE_FROM)]
        idx = d.index
        i = 1
        while i < len(idx):
            t = idx[i]
            if not (pd.Timestamp(start) <= t <= pd.Timestamp(end)):
                i += 1
                continue
            prev = d.Close.iloc[i - 1]
            trig = prev * (1 + TRIGGER)
            if d.High.iloc[i] < trig:
                i += 1
                continue
            g = [by_day.loc[(code, dd)] for dd in (idx[i - 1], t) if (code, dd) in by_day.index]
            if not g or any(x.bad for x in g) or not any(x.good for x in g):
                i += 1
                continue
            entry = max(d.Open.iloc[i], trig)
            if max_entry is not None and entry > prev * (1 + max_entry):
                i += 1
                continue
            peak, j, out = entry, i, None
            while j < len(idx):
                out = rule(j - i, d.iloc[j], entry, peak)
                if out:
                    break
                peak = max(peak, d.High.iloc[j])
                j += 1
            if not out:  # 데이터 끝까지 보유 중
                j, out = len(idx) - 1, (d.Close.iloc[-1], "보유중")
            ret = out[0] / entry - 1 - COST
            b = bench.reindex(idx).iloc[j] / bench.reindex(idx).iloc[i - 1] - 1
            trades.append(dict(code=code, date=t, ret=ret, excess=ret - b, days=j - i, why=out[1],
                               peak=peak / entry - 1))
            i = j + 1  # 청산 전엔 같은 종목 재진입 없음
    return pd.DataFrame(trades)


def stats(df):
    if df.empty:
        return dict(건수=0)
    return {"건수": len(df), "승률": f"{(df.ret > 0).mean():.1%}", "평균 순수익": f"{df.ret.mean():+.2%}",
            "중앙값": f"{df.ret.median():+.2%}", "초과수익": f"{df.excess.mean():+.2%}",
            "평균 보유일": f"{df.days.mean():.2f}", "손절 비율": f"{(df.why == '손절').mean():.1%}",
            "+10% 갔다 손실": f"{((df.peak >= 0.10) & (df.ret < 0)).mean():.1%}"}


RULES = {
    "원 규칙 (익절 없음)": make_rule(),
    "익절 +10%": make_rule(tp=0.10),
    "익절 +15%": make_rule(tp=0.15),
    "익절 +20%": make_rule(tp=0.20),
    "트레일링 7%": make_rule(trail=0.07),
    "트레일링 10%": make_rule(trail=0.10),
    "트레일링 15%": make_rule(trail=0.15),
    "+10% 가면 +3% 보장": make_rule(lock=(0.10, 0.03)),
    "+10% 가면 본전 보장": make_rule(lock=(0.10, 0.0)),
    "+15% 가면 +7% 보장": make_rule(lock=(0.15, 0.07)),
}

pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)
for pname, (s, e) in PERIODS.items():
    for cap in (None, 0.15):
        title = f"[{pname}]" + (" 진입 상한 +15%" if cap else "")
        print(title)
        print(pd.DataFrame({n: stats(run(r, s, e, cap)) for n, r in RULES.items()}).T.to_string(), "\n")
