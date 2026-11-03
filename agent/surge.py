# 가설 B (형민님 Case 3): 장중 +10% 급등 + DART 호재 공시 종목 진입, 손절 -5%, 음봉 마감일 종가 청산
# 장중 내내 켜 두는 루프. python -m agent.surge [--execute]
#   진입: 전일 종가 대비 +10% 도달 & 전일~당일 호재 공시(자사주 취득·공급계약·잠정실적·신규시설투자)
#   손절: 진입가 대비 -5% (단, 같은 종목 30분 재거래 제한 때문에 진입 후 30분 동안은 못 판다)
#   청산: 14:50에 현재가 < 당일 시가(음봉)면 매도. 진입 당일은 진입가 아래일 때만
import argparse
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import FinanceDataReader as fdr
from dotenv import load_dotenv

from agent import dart_filter
from agent.aqua import Aqua, AquaError

STATE = Path(__file__).parent / "state" / "b_state.json"
C_STATE = Path(__file__).parent / "state" / "c_state.json"
UNIVERSE_N = 200          # KOSPI200 구성종목 대신 시총 상위 200 보통주
TRIGGER, STOP = 0.10, -0.05
BUDGET, MAX_POS = 0.20, 3  # 총자산의 20%를 최대 3종목에 나눠 씀
ENTRY_FROM, ENTRY_UNTIL, CLOSE_CHECK = "09:10", "14:40", "14:50"  # 09:05 C 리밸런싱과 겹치지 않게
POLL_SEC = 60
GOOD_KEYWORDS = ["자기주식취득", "자기주식 취득", "신탁계약체결", "단일판매ㆍ공급계약", "단일판매·공급계약",
                 "영업(잠정)실적", "잠정실적", "신규시설투자"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def universe():
    lst = fdr.StockListing("KOSPI")
    lst = lst[lst["Code"].str.endswith("0")].sort_values("Marcap", ascending=False).head(UNIVERSE_N)
    # 장 시작 전에 받으면 Close가 곧 전일 종가, 장중이면 Close - Changes
    before_open = datetime.now().strftime("%H:%M") < "09:00"
    prev = lst["Close"] if before_open else lst["Close"] - lst["Changes"]
    return dict(zip(lst["Code"], prev.astype(int))), dict(zip(lst["Code"], lst["Name"]))


def good_disclosures():
    """전일~당일 호재 공시 {symbol: 제목}. 정정공시와 악재 키워드가 섞인 제목은 제외"""
    out = {}
    for d in dart_filter.fetch(days=3 if date.today().weekday() == 0 else 1):  # 월요일은 금요일 공시부터
        t = d["report_nm"]
        if "정정" in t or any(k in t for k in dart_filter.BAD_KEYWORDS if k != "공급계약"):
            continue
        if any(k in t for k in GOOD_KEYWORDS):
            out.setdefault(d["stock_code"], t)
    return out


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(pos):
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(pos, ensure_ascii=False, indent=2), encoding="utf-8")


def sell(api, s, qty, why, execute, pos, names):
    log(f"SELL {names.get(s, s)}({s}) {qty}주 — {why}")
    if not execute:
        pos.pop(s, None)
        return
    try:
        r = api.order(s, "SELL", qty)
        log(f"  → {r['status']} {r['filledQuantity']}주 @ {r['executedPrice']}")
        if r["filledQuantity"] >= qty:
            pos.pop(s, None)
        else:
            pos[s]["qty"] = qty - r["filledQuantity"]
        save(pos)
    except AquaError as e:
        log(f"  → 실패 {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    load_dotenv()

    api = Aqua()
    prev, names = universe()
    syms = list(prev)
    pos = load(STATE, {})  # {symbol: {entry, date, qty}}
    log(f"{api.team} 시작, 감시 {len(syms)}종목, 보유 B 포지션 {list(pos)}")

    good, good_at = {}, None
    tried = set()          # 오늘 이미 판단한 종목 (하루 1회만 진입 시도)
    closed_check = False

    while datetime.now().strftime("%H:%M") < "15:00":
        now = datetime.now().strftime("%H:%M")
        try:
            px = api.prices(syms + [s for s in pos if s not in prev])
        except AquaError as e:
            log(f"시세 실패 {e}")
            time.sleep(POLL_SEC)
            continue

        # 1) 손절
        for s, p in list(pos.items()):
            if s in px and px[s] <= p["entry"] * (1 + STOP):
                sell(api, s, p["qty"], f"손절 {px[s] / p['entry'] - 1:+.1%}", args.execute, pos, names)

        # 2) 14:50 음봉 청산
        if now >= CLOSE_CHECK and not closed_check:
            closed_check = True
            for s, p in list(pos.items()):
                o = api.candles(s, "1d", 1)[-1]["openPrice"]
                bearish = px[s] < o
                if bearish and (p["date"] != date.today().isoformat() or px[s] < p["entry"]):
                    sell(api, s, p["qty"], f"음봉 (시가 {o:,} > 현재 {px[s]:,})", args.execute, pos, names)

        # 3) 진입
        if ENTRY_FROM <= now <= ENTRY_UNTIL and len(pos) < MAX_POS:
            c_held = set(load(C_STATE, {"targets": []})["targets"])
            hits = [s for s in syms if s in px and px[s] >= prev[s] * (1 + TRIGGER)
                    and s not in pos and s not in tried and s not in c_held]
            if hits:
                if good_at is None or datetime.now() - good_at > timedelta(minutes=10):
                    good, good_at = good_disclosures(), datetime.now()
                for s in sorted(hits, key=lambda s: -px[s] / prev[s]):
                    tried.add(s)
                    chg = px[s] / prev[s] - 1
                    if s not in good:
                        log(f"패스 {names[s]}({s}) {chg:+.1%} — 호재 공시 없음")
                        continue
                    if len(pos) >= MAX_POS:
                        break
                    pf = api.portfolio()
                    budget = min(pf["totalAssetValue"] * BUDGET / MAX_POS, pf["availableCash"] * 0.98)
                    qty = int(budget // px[s])
                    log(f"BUY {names[s]}({s}) {chg:+.1%} {qty}주 — {good[s]}")
                    if qty <= 0:
                        continue
                    if not args.execute:
                        pos[s] = {"entry": px[s], "date": date.today().isoformat(), "qty": qty}
                        continue
                    try:
                        r = api.order(s, "BUY", qty)
                        log(f"  → {r['status']} {r['filledQuantity']}주 @ {r['executedPrice']}")
                        if r["filledQuantity"]:
                            pos[s] = {"entry": r["executedPrice"], "date": date.today().isoformat(),
                                      "qty": r["filledQuantity"]}
                            save(pos)
                    except AquaError as e:
                        log(f"  → 실패 {e}")
        time.sleep(POLL_SEC)
    log("장 마감, 종료")


if __name__ == "__main__":
    main()
