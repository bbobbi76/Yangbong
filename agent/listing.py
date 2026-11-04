# 코스피 보통주 목록 (FinanceDataReader). 장 시작 직후엔 빈 값이 섞여 숫자 컬럼이 문자열로 오는 일이 있어
# 숫자로 바꾸고, 값이 빠진 종목이 많으면 매매하지 않도록 예외를 낸다 (2026-11-04 문자열 정렬로 엉뚱한 종목 매수)
import pandas as pd
import FinanceDataReader as fdr

NUM_COLS = ["Close", "Changes", "Marcap", "Amount"]


def kospi_common(max_missing=0.05):
    lst = fdr.StockListing("KOSPI")
    lst = lst[lst["Code"].str.endswith("0")].copy()  # 우선주 제외 (AQuA는 보통주만 거래)
    for c in NUM_COLS:
        lst[c] = pd.to_numeric(lst[c], errors="coerce")
    missing = lst[["Close", "Marcap"]].isna().any(axis=1).mean()
    if missing > max_missing:
        raise RuntimeError(f"종목 목록 데이터 이상: 시세 빠진 종목 {missing:.0%} → 매매 중단")
    return lst.dropna(subset=["Close", "Marcap"]).sort_values("Marcap", ascending=False)
