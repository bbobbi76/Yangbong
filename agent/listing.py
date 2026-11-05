# 코스피 보통주 목록 (FinanceDataReader).
# 장 시작 직후(09:00~)엔 목록이 비거나(11/5: 시세 빠진 종목 100%) 숫자 컬럼이 문자열로 와서(11/4) 믿을 수 없다.
# 그래서 장 시작 전(08:50 검사 때) 받은 정상 목록을 날짜별로 저장해 두고, 장중 실행은 그 저장본을 쓴다.
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import FinanceDataReader as fdr

CACHE = Path(__file__).parent / "state" / "listing"
NUM_COLS = ["Close", "Changes", "Marcap", "Amount"]
MAX_STALE_DAYS = 4  # 오늘 저장본도 없고 새로 받은 것도 이상하면, 이 기간 안의 저장본으로 대신 (rebalance용)


def _fetch(max_missing):
    lst = fdr.StockListing("KOSPI")
    lst = lst[lst["Code"].str.endswith("0")].copy()  # 우선주 제외 (AQuA는 보통주만 거래)
    for c in NUM_COLS:
        lst[c] = pd.to_numeric(lst[c], errors="coerce")
    missing = lst[["Close", "Marcap"]].isna().any(axis=1).mean()
    if missing > max_missing:
        raise RuntimeError(f"종목 목록 데이터 이상: 시세 빠진 종목 {missing:.0%}")
    return lst.dropna(subset=["Close", "Marcap"]).sort_values("Marcap", ascending=False)


def _load(path):
    lst = pd.read_csv(path, dtype={"Code": str})
    return lst.sort_values("Marcap", ascending=False)


def kospi_common(max_missing=0.05):
    """시총 내림차순 목록. attrs["prev_close"]가 True면 Close 컬럼이 곧 전일 종가(장 시작 전 데이터),
    attrs["stale"]가 True면 오늘 것이 아닌 옛 저장본이다."""
    today = CACHE / f"{date.today():%Y%m%d}.csv"
    if today.exists():
        lst = _load(today)
        lst.attrs.update(prev_close=True, stale=False)
        return lst

    try:
        lst = _fetch(max_missing)
    except RuntimeError as e:
        old = sorted(CACHE.glob("*.csv"))
        if not old or (date.today() - datetime.strptime(old[-1].stem, "%Y%m%d").date()).days > MAX_STALE_DAYS:
            raise RuntimeError(f"{e} → 쓸 수 있는 저장본도 없어 매매 중단")
        print(f"! {e} → {old[-1].stem} 저장본 사용")
        lst = _load(old[-1])
        lst.attrs.update(prev_close=False, stale=True)
        return lst

    preopen = datetime.now().strftime("%H:%M") < "09:00"
    if preopen:
        CACHE.mkdir(parents=True, exist_ok=True)
        lst.to_csv(today, index=False)
    lst.attrs.update(prev_close=preopen, stale=False)
    return lst
