# 매일 장 시작 직후(09:05 무렵) 1회 실행: C 기본 포트폴리오 + A 공시 필터
#   python -m agent.rebalance            → 주문 계획만 출력 (dry-run)
#   python -m agent.rebalance --execute  → 실제 주문
# 20거래일마다 모멘텀 상위 K로 전체 교체, 그 사이엔 악재 공시 종목만 빼고 다음 순위로 채운다.
import argparse
import json
import os
from datetime import date
from pathlib import Path

import FinanceDataReader as fdr
from dotenv import load_dotenv

from agent import momentum, dart_filter
from agent.aqua import Aqua, AquaError

STATE = Path(__file__).parent / "state" / "c_state.json"  # C가 관리하는 종목 (B 포지션은 건드리지 않기 위해)
REBAL_DAYS = 20


def load_state():
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"targets": [], "rebalanced": None}
    state.setdefault("pending_sell", [])  # 목표에서 빠졌지만 아직 다 못 판 종목
    state.setdefault("short", {})         # 지난 매수에서 덜 체결된 수량 {symbol: 수량}
    return state


def trading_days_since(d):
    if d is None:
        return 10 ** 9
    return len(fdr.DataReader("069500", d)) - 1  # KODEX 200 일봉 수로 거래일 계산


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--weight", type=float, default=0.8, help="총자산 중 C에 쓸 비중 (나머지는 B용 현금)")
    ap.add_argument("--force", action="store_true", help="20거래일이 안 돼도 전체 교체")
    args = ap.parse_args()
    load_dotenv()

    api = Aqua() if os.getenv("TEAM_CODE") else None
    state = load_state()
    rank = momentum.ranked()
    if api is not None:
        rank = rank[rank["code"].isin(api.symbols())]  # 리츠·인프라펀드 등 AQuA 거래 불가 종목 제외
    names = dict(zip(rank["code"], rank["name"]))
    candidates = list(rank["code"][: args.k * 3])

    check = sorted(set(candidates) | set(state["targets"]))
    bad = dart_filter.blocked(check) if os.getenv("DART_KEY") else {}
    if not os.getenv("DART_KEY"):
        print("! DART_KEY 없음 → 공시 필터 생략")
    for s, why in bad.items():
        print(f"  제외 {names.get(s, s)}({s}): {why}")

    # 종목 선정 기준(momentum.SIGNAL)이 바뀌었으면 기다리지 않고 바로 전체 교체
    full = (args.force or state.get("signal", "mom") != momentum.SIGNAL
            or trading_days_since(state["rebalanced"]) >= REBAL_DAYS)
    keep = [] if full else [s for s in state["targets"] if s not in bad]
    targets = keep + [s for s in candidates if s not in bad and s not in keep][: args.k - len(keep)]
    print(f"{'전체 교체' if full else '유지 + 보충'} → 목표: " + ", ".join(f"{names.get(s, s)}({s})" for s in targets))

    if api is None:
        print("! TEAM_CODE 없음 → 1억 빈 계좌로 가정한 계획만 출력")
        pf = {"totalAssetValue": 100_000_000, "holdings": []}
        px = {s: int(momentum.fdr.DataReader(s).iloc[-1]["Close"]) for s in targets}
    else:
        pf = api.portfolio()
        px = api.prices(sorted(set(targets) | set(state["targets"]) | set(state["pending_sell"])))
    held = {h["symbol"]: h["availableQuantity"] for h in pf["holdings"]}

    per = pf["totalAssetValue"] * args.weight / args.k
    gone = [s for s in dict.fromkeys(state["targets"] + state["pending_sell"]) if s not in targets]
    plan = [(s, "SELL", held[s]) for s in gone if held.get(s)]
    for s in targets:
        diff = int(per // px[s]) - held.get(s, 0)
        # 월중에는 기존 보유분 비중 조정을 하지 않음 (매매비용·쿨다운 절약). 새로 들어온 종목만 매수
        if diff > 0 and (full or held.get(s, 0) == 0):
            plan.append((s, "BUY", diff))
        elif diff > 0 and s in state["short"]:  # 지난번 덜 체결된 수량만 채움
            plan.append((s, "BUY", min(diff, state["short"][s])))
        elif diff < 0 and full:
            plan.append((s, "SELL", -diff))
    plan.sort(key=lambda x: x[1] != "SELL")  # 매도 먼저 해서 현금 확보

    sold, short = {}, {}
    for s, side, q in plan:
        line = f"  {side:4} {names.get(s, s)}({s}) {q}주 ≈ {q * px[s]:,.0f}원"
        if not args.execute or api is None:
            print(line + " [dry-run]")
            continue
        filled = 0
        try:
            r = api.order(s, side, q)  # 시장가: 지금 호가 잔량만큼 체결, 남는 수량은 버림
            filled = r["filledQuantity"]
            print(line + f" → {r['status']} {filled}주 @ {r['executedPrice']}")
        except AquaError as e:
            print(line + f" → 실패 {e}")
        if side == "SELL":
            sold[s] = sold.get(s, 0) + filled
        elif filled < q:
            short[s] = q - filled

    if args.execute and api is not None:
        STATE.parent.mkdir(exist_ok=True)
        # 주문이 실패했거나 일부만 체결된 종목은 다음 실행에서 이어서 처리
        pending = [s for s in gone if s in held and (held[s] == 0 or sold.get(s, 0) < held[s])]
        STATE.write_text(json.dumps({"targets": targets, "pending_sell": pending, "short": short,
                                     "signal": momentum.SIGNAL,
                                     "rebalanced": date.today().isoformat() if full else state["rebalanced"]},
                                    ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
