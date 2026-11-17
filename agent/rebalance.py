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
from agent.listing import kospi_common

STATE = Path(__file__).parent / "state" / "c_state.json"  # C가 관리하는 종목 (B 포지션은 건드리지 않기 위해)
REBAL_DAYS = 20
# 지수 대비 안전선: KODEX 200보다 앞선 폭이 이만큼(%p) 아래로 줄면 남은 기간은 지수 추종으로 전환한다 (되돌리지 않음).
# 고변동성 종목이 지수보다 크게 빠져 코스피 200 아래로 내려가는 걸 막기 위한 장치.
GUARD_GAP = 3.0
INDEX_N, INDEX_CAP = 10, 0.20  # 지수 추종: 시총 상위 10종목을 시총 비중으로, 한 종목 최대 20%


def index_gap(api):
    """리더보드 기준 우리 팀 수익률 - KODEX 200 수익률 (%p)"""
    lb = api.leaderboard()
    me = next(r for r in lb["rankings"] if r["teamName"] == api.team)
    return me["totalReturnRate"] - lb["baseline"]["totalReturnRate"]


def index_weights(codes, marcap):
    """시총 비중, 한 종목 INDEX_CAP 상한 (넘친 몫은 나머지에 비례 배분)"""
    w = {c: marcap[c] for c in codes}
    w = {c: v / sum(w.values()) for c, v in w.items()}
    for _ in range(5):
        over = {c for c, v in w.items() if v > INDEX_CAP}
        if not over:
            break
        extra = sum(w[c] - INDEX_CAP for c in over)
        rest = sum(v for c, v in w.items() if c not in over)
        w = {c: INDEX_CAP if c in over else v + extra * v / rest for c, v in w.items()}
    return w


def too_many_sells(plan, held_targets, full):
    """전체 교체일이 아닌데 보유 종목의 절반 넘게 팔려고 하면 True (악재 공시 판정 오류 등으로 한꺼번에 파는 것 방지)"""
    sells = {s for s, side, _ in plan if side == "SELL"}
    return not full and len(sells) > max(1, len(held_targets) // 2)


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
    # 11/18부터 4종목: 남은 9거래일 재생에서 하락 국면 1위 확률 14% → 21%, 앞·뒤 기간 모두 같은 경향
    # (3종목은 지수 아래 추락 10%로 너무 위험). research/model_tests_result.md
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--weight", type=float, default=0.95,
                    help="총자산 중 C에 쓸 비중. 11/19부터 0.95 (급등주 자리는 대부분 비어 있어 노는 현금을 줄임)")
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

    # 지수 대비 안전선 확인 (한 번 걸리면 대회 끝까지 지수 추종)
    defense = state.get("defense", False)
    if api is not None and not defense:
        gap = index_gap(api)
        print(f"  KODEX 200 대비 {gap:+.2f}%p (안전선 {GUARD_GAP}%p)")
        defense = gap < GUARD_GAP
    signal = "index" if defense else momentum.SIGNAL
    if defense:
        lst = kospi_common()
        if api is not None:
            lst = lst[lst["Code"].isin(api.symbols())]
        marcap = dict(zip(lst["Code"], lst["Marcap"]))
        names.update(zip(lst["Code"], lst["Name"]))
        candidates = list(lst["Code"][: INDEX_N * 2])
        print("!!! 지수 대비 안전선 아래 → 남은 기간 지수 추종(시총 상위 10, 시총 비중)")

    check = sorted(set(candidates) | set(state["targets"]))
    bad = dart_filter.blocked(check, allow=dart_filter.LARGECAP_OK) if os.getenv("DART_KEY") else {}
    if not os.getenv("DART_KEY"):
        print("! DART_KEY 없음 → 공시 필터 생략")
    for s, why in bad.items():
        print(f"  제외 {names.get(s, s)}({s}): {why}")

    # 종목 선정 기준이 바뀌었으면(안전선 전환 포함) 기다리지 않고 바로 전체 교체
    full = (args.force or state.get("signal", "mom") != signal
            or trading_days_since(state["rebalanced"]) >= REBAL_DAYS)
    n = INDEX_N if defense else args.k
    keep = [] if full else [s for s in state["targets"] if s not in bad]
    targets = keep + [s for s in candidates if s not in bad and s not in keep][: n - len(keep)]
    weights = index_weights(targets, marcap) if defense else {s: 1 / len(targets) for s in targets}
    print(f"{'전체 교체' if full else '유지 + 보충'} → 목표: " + ", ".join(f"{names.get(s, s)}({s})" for s in targets))

    if api is None:
        print("! TEAM_CODE 없음 → 1억 빈 계좌로 가정한 계획만 출력")
        pf = {"totalAssetValue": 100_000_000, "holdings": []}
        px = {s: int(momentum.fdr.DataReader(s).iloc[-1]["Close"]) for s in targets}
    else:
        pf = api.portfolio()
        px = api.prices(sorted(set(targets) | set(state["targets"]) | set(state["pending_sell"])))
    held = {h["symbol"]: h["availableQuantity"] for h in pf["holdings"]}

    budget = pf["totalAssetValue"] * args.weight
    gone = [s for s in dict.fromkeys(state["targets"] + state["pending_sell"]) if s not in targets]
    plan = [(s, "SELL", held[s]) for s in gone if held.get(s)]
    for s in targets:
        diff = int(budget * weights[s] // px[s]) - held.get(s, 0)
        # 월중에는 기존 보유분 비중 조정을 하지 않음 (매매비용·쿨다운 절약). 새로 들어온 종목만 매수
        if diff > 0 and (full or held.get(s, 0) == 0):
            plan.append((s, "BUY", diff))
        elif diff > 0 and s in state["short"]:  # 지난번 덜 체결된 수량만 채움
            plan.append((s, "BUY", min(diff, state["short"][s])))
        elif diff < 0 and full:
            plan.append((s, "SELL", -diff))
    plan.sort(key=lambda x: x[1] != "SELL")  # 매도 먼저 해서 현금 확보
    if too_many_sells(plan, [s for s in state["targets"] if held.get(s)], full):
        print(f"!!! 전체 교체일이 아닌데 {sum(x[1] == 'SELL' for x in plan)}종목을 팔려고 함 → 오늘 주문 전부 중단, 로그 확인 필요")
        plan = []

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
                                     "signal": signal, "defense": defense,
                                     "rebalanced": date.today().isoformat() if full else state["rebalanced"]},
                                    ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
