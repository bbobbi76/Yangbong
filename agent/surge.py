# 가설 B (형민님 Case 3, v2.1 검증 반영): 장중 +10% 급등 + DART 호재 공시 종목 진입, 손절 -5%, 음봉 마감일 종가 청산
# 백테스트 근거 (2026-01~09, KOSPI200 대상):
#   - Case 1 (+10% 단독): 1,258건, 승률 30.0%, 평균 순수익 +0.14%p, 초과수익 +0.27%p, 손절률 50.2%
#   - Case 3 (+10% + DART 호재공시 + -5% 손절 + 당일음봉 매도): 139건, 승률 39.6%, 평균 순수익 +2.07%p, 초과수익 +2.07%p, 평균 보유 1.60일, 손절률 40.3%
# 장중 상주 루프: python -m agent.surge [--execute]
import argparse
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

from agent import dart_filter
from agent.listing import kospi_common
from agent.aqua import Aqua, AquaError

STATE = Path(__file__).parent / "state" / "b_state.json"
C_STATE = Path(__file__).parent / "state" / "c_state.json"
UNIVERSE_N = 200          # AQuA 시세 일괄 조회 한도(200종목)에 맞춘 시총 상위 200 보통주
TRIGGER, STOP = 0.10, -0.05
BUDGET, MAX_POS = 0.20, 3  # 총자산의 20%를 최대 3종목에 분할
# 09:05 C 리밸런싱 및 개장 직후(09:00~09:15) 윗꼬리 변동성 회피, 14:50 음봉 청산 전 30분 쿨다운 확보를 위해 14:20 진입 마감
ENTRY_FROM, ENTRY_UNTIL, CLOSE_CHECK = "09:15", "14:20", "14:50"
COOLDOWN_SEC = 30 * 60    # AQuA 규칙: 동일 종목 주문 후 30분간 매수·매도 불가 (429 SYMBOL_COOLDOWN)
MAX_HOLD_DAYS = 15        # v2.1 백테스트 기준 최대 보유일 안전장치
POLL_SEC = 60

GOOD_KEYWORDS = [
    "자기주식취득", "자기주식 취득", "자사주", "신탁계약체결",
    "단일판매", "공급계약", "수주",
    "영업(잠정)실적", "잠정실적", "매출액또는손익구조",
    "신규시설투자", "특허권취득", "기술이전", "현금ㆍ현물배당",
]
NEG_KEYWORDS = ["기재정정", "정정", "철회", "해지", "중단", "취소"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def universe():
    lst = kospi_common()
    if lst.attrs["stale"]:
        raise RuntimeError("오늘 종목 목록이 없어 전일 종가를 알 수 없음 → surge 중단")
    prev_close = lst.attrs["prev_close"]
    lst = lst.head(UNIVERSE_N).dropna(subset=["Changes"])
    # 장 시작 전 데이터면 Close가 곧 전일 종가, 장중에 새로 받은 거면 Close - Changes
    prev = lst["Close"] if prev_close else lst["Close"] - lst["Changes"]
    return dict(zip(lst["Code"], prev.astype(int))), dict(zip(lst["Code"], lst["Name"]))


def good_disclosures():
    """전일~당일 호재 공시 {symbol: 제목}. 악재·정정 공시가 동반된 종목은 제외"""
    days = 3 if date.today().weekday() == 0 else 1  # 월요일은 금요일 공시부터 확인
    raw = dart_filter.fetch(days=days)
    bad_words = [k for k in dart_filter.BAD_KEYWORDS if k != "공급계약"] + NEG_KEYWORDS

    bad_syms = {
        d["stock_code"] for d in raw
        if any(k in d.get("report_nm", "") for k in bad_words)
    }
    out = {}
    for d in raw:
        s, t = d.get("stock_code", ""), d.get("report_nm", "")
        if not s or s in bad_syms or any(k in t for k in bad_words):
            continue
        if any(k in t for k in GOOD_KEYWORDS):
            out.setdefault(s, t)
    return out


def llm_confirm(name, title, cache):
    """GEMINI_KEY가 있으면 +10% 급등 종목의 공시 제목이 실질 호재인지 판독 (실패·미설정 시 True)"""
    key = f"{name}::{title}"
    if key in cache:
        return cache[key]
    api_key = os.getenv("GEMINI_KEY", "").strip()
    if not api_key:
        cache[key] = True
        return True

    prompt = (
        f"코스피200 종목 '{name}'이 장중 +10% 이상 급등했습니다. 동반된 DART 공시 제목: '{title}'\n"
        "이 공시가 자사주 취득, 수주(단일판매·공급계약), 실적 호전, 신규시설투자 등 주가 상승을 뒷받침하는 "
        "실질적 호재라면 YES, 단순 정정·일상 안내·악재·희석 공시라면 NO만 답하세요."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    try:
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=8)
        ans = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
        ok = "YES" in ans
    except Exception as e:
        log(f"  [LLM 예외 → 키워드 통과 유지] {e}")
        ok = True
    cache[key] = ok
    return ok


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(pos):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(pos, ensure_ascii=False, indent=2), encoding="utf-8")


def can_order(p):
    """동일 종목 마지막 주문 시각(ordered_at)으로부터 30분이 지났는지 확인"""
    ts = p.get("ordered_at")
    if not ts:
        return True
    try:
        return (datetime.now() - datetime.fromisoformat(ts)).total_seconds() >= COOLDOWN_SEC
    except Exception:
        return True


def today_open(api, s, open_cache):
    """당일 시가(openPrice) 조회 및 캐싱"""
    if s not in open_cache:
        try:
            c = api.candles(s, "1d", 1)
            if c:
                open_cache[s] = c[-1]["openPrice"]
        except AquaError as e:
            log(f"  [{s}] 일봉 시가 조회 실패: {e}")
    return open_cache.get(s)


def sell(api, s, qty, why, execute, pos, names):
    log(f"SELL {names.get(s, s)}({s}) {qty}주 — {why}")
    if not execute:
        pos.pop(s, None)
        return True
    try:
        r = api.order(s, "SELL", qty)
        filled = r.get("filledQuantity", 0)
        log(f"  → {r['status']} {filled}주 @ {r['executedPrice']}")
        if filled >= qty:
            pos.pop(s, None)
        elif filled > 0:
            pos[s]["qty"] = qty - filled
            pos[s]["ordered_at"] = datetime.now().isoformat(timespec="seconds")
        save(pos)
        return filled >= qty
    except AquaError as e:
        log(f"  → 실패 {e}")
        if "SYMBOL_COOLDOWN" in str(e):
            pos[s]["ordered_at"] = datetime.now().isoformat(timespec="seconds")
            save(pos)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    load_dotenv()

    api = Aqua()
    prev, names = universe()
    syms = list(prev)
    pos = load(STATE, {})  # {symbol: {entry, date, qty, ordered_at}}
    log(f"{api.team} 시작, 감시 {len(syms)}종목, 보유 B 포지션 {list(pos)}")

    good, good_at = {}, None
    llm_cache = {}
    open_cache = {}
    tried = set()          # 오늘 이미 진입 판단한 종목 (하루 1회만 시도)
    close_checked = set()  # 14:50 이후 음봉 청산 판정을 완료한 종목

    while datetime.now().strftime("%H:%M") < "15:00":
        now = datetime.now().strftime("%H:%M")
        # AQuA 시세 API는 최대 200종목 제한 → 보유 포지션을 우선 포함하고 총 200개로 맞춤
        extra = [s for s in pos if s not in prev]
        watch = extra + syms[: max(0, UNIVERSE_N - len(extra))]
        try:
            px = api.prices(watch)
        except AquaError as e:
            log(f"시세 실패 {e}")
            time.sleep(POLL_SEC)
            continue

        # 1) 상시 손절: 최초 진입가 대비 -5% 이하 (30분 쿨다운 경과 종목만 실행)
        for s, p in list(pos.items()):
            if s in px and px[s] <= p["entry"] * (1 + STOP) and can_order(p):
                sell(api, s, p["qty"], f"손절 {px[s] / p['entry'] - 1:+.1%}", args.execute, pos, names)

        # 2) 14:50 이후 당일 음봉(현재가 < 시가) 종가 청산 및 최대 보유일(15일) 만료 청산
        if now >= CLOSE_CHECK:
            for s, p in list(pos.items()):
                if s in close_checked or s not in px or not can_order(p):
                    continue
                held_days = (date.today() - date.fromisoformat(p["date"])).days
                if held_days >= MAX_HOLD_DAYS:
                    if sell(api, s, p["qty"], f"최대보유({held_days}일) 만료", args.execute, pos, names):
                        close_checked.add(s)
                    continue
                o = today_open(api, s, open_cache)
                if o is None:
                    continue
                bearish = px[s] < o
                if bearish and (p["date"] != date.today().isoformat() or px[s] < p["entry"]):
                    if sell(api, s, p["qty"], f"음봉 (시가 {o:,} > 현재 {px[s]:,})", args.execute, pos, names):
                        close_checked.add(s)
                else:
                    close_checked.add(s)

        # 3) 장중 진입 (09:15 ~ 14:20): +10% 도달 & 당일 양봉 지지 & DART 호재 공시
        if ENTRY_FROM <= now <= ENTRY_UNTIL and len(pos) < MAX_POS:
            c_held = set(load(C_STATE, {"targets": []}).get("targets", []))
            hits = [
                s for s in syms
                if s in px and px[s] >= prev[s] * (1 + TRIGGER)
                and s not in pos and s not in tried and s not in c_held
            ]
            if hits:
                if good_at is None or datetime.now() - good_at > timedelta(minutes=10):
                    good, good_at = good_disclosures(), datetime.now()
                for s in sorted(hits, key=lambda s: -px[s] / prev[s]):
                    tried.add(s)
                    chg = px[s] / prev[s] - 1
                    if s not in good:
                        log(f"패스 {names[s]}({s}) {chg:+.1%} — 호재 공시 없음")
                        continue
                    if not llm_confirm(names[s], good[s], llm_cache):
                        log(f"패스 {names[s]}({s}) {chg:+.1%} — LLM 비호재 판정 ({good[s]})")
                        continue
                    o = today_open(api, s, open_cache)
                    if o is not None and px[s] < o:
                        log(f"패스 {names[s]}({s}) {chg:+.1%} — 시가({o:,}) 하회 장중 음봉")
                        continue
                    if len(pos) >= MAX_POS:
                        break
                    pf = api.portfolio()
                    budget = min(pf["totalAssetValue"] * BUDGET / MAX_POS, pf["availableCash"] * 0.98)
                    qty = int(budget // px[s])
                    log(f"BUY {names[s]}({s}) {chg:+.1%} {qty}주 — {good[s]}")
                    if qty <= 0:
                        continue
                    now_iso = datetime.now().isoformat(timespec="seconds")
                    if not args.execute:
                        pos[s] = {"entry": px[s], "date": date.today().isoformat(), "qty": qty, "ordered_at": now_iso}
                        continue
                    try:
                        r = api.order(s, "BUY", qty)
                        filled = r.get("filledQuantity", 0)
                        log(f"  → {r['status']} {filled}주 @ {r['executedPrice']}")
                        if filled:
                            pos[s] = {
                                "entry": r["executedPrice"],
                                "date": date.today().isoformat(),
                                "qty": filled,
                                "ordered_at": now_iso,
                            }
                            save(pos)
                    except AquaError as e:
                        log(f"  → 실패 {e}")
        time.sleep(POLL_SEC)
    log("장 마감, 종료")


if __name__ == "__main__":
    main()
