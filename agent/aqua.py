# AQuA 모의투자 REST API 클라이언트 (문서: http://136.119.248.78/docs)
import os
import time
import requests

BASE = os.getenv("AQUA_BASE", "http://136.119.248.78")
# 매수 한 건이 총자산의 이 비율을 넘으면 보내지 않는다 (버그로 엉뚱하게 큰 주문 방지).
# 정상 주문은 기본 포트폴리오 한 종목 약 18%(90% ÷ 5), 급등주 한 종목 5%라 걸리지 않는다.
MAX_ORDER_RATIO = 0.25


class AquaError(Exception):
    def __init__(self, status, code, message):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class Aqua:
    def __init__(self, team_code=None):
        self.s = requests.Session()
        r = self.s.post(f"{BASE}/api/auth/login", json={"teamCode": team_code or os.environ["TEAM_CODE"]}, timeout=10)
        self._check(r)
        self.team = r.json()["teamName"]
        self.s.headers["Authorization"] = f"Bearer {r.json()['accessToken']}"

    @staticmethod
    def _check(r):
        if r.ok:
            return
        try:
            err = r.json()["error"]
        except Exception:
            err = {"code": "HTTP", "message": r.text[:200]}
        raise AquaError(r.status_code, err["code"], err["message"])

    def _req(self, method, path, **kw):
        # 분당 100회 초과(RATE_LIMIT_EXCEEDED)만 Retry-After 만큼 쉬고 재시도, 나머지 에러는 그대로 올림
        for _ in range(3):
            try:
                r = self.s.request(method, f"{BASE}{path}", timeout=15, **kw)
            except requests.RequestException as e:
                # 서버 접속 장애도 AquaError로 올려서 surge 루프가 죽지 않고 다음 주기에 재시도하게 (11/9 접속 타임아웃으로 종료)
                raise AquaError(0, "NETWORK", type(e).__name__) from None
            if r.status_code == 429 and "RATE_LIMIT" in r.text:
                time.sleep(int(r.headers.get("Retry-After", 10)))
                continue
            self._check(r)
            return r.json()
        self._check(r)

    def symbols(self):
        """AQuA에서 거래 가능한 종목 코드 집합 (코스피 보통주. 맥쿼리인프라·리츠 등은 없음)"""
        return {x["symbol"] for x in self._req("GET", "/api/stocks")["stocks"]}

    def prices(self, symbols):
        out = {}
        for i in range(0, len(symbols), 200):  # 한 번에 최대 200개
            chunk = list(symbols[i:i + 200])
            for _ in range(5):
                try:
                    res = self._req("GET", "/api/stocks/price", params={"symbols": ",".join(chunk)})
                    break
                except AquaError as e:
                    # 거래 불가 종목 하나 때문에 전체 조회가 실패하지 않게 (11/6 맥쿼리인프라로 surge 하루 공백)
                    bad = next((s for s in chunk if s in e.message), None)
                    if e.code != "UNKNOWN_SYMBOL" or bad is None:
                        raise
                    chunk.remove(bad)
            else:
                raise AquaError(404, "UNKNOWN_SYMBOL", "거래 불가 종목이 너무 많음")
            out.update({x["symbol"]: x["price"] for x in res["result"]})
        return out

    def candles(self, symbol, interval="1d", count=200):
        return self._req("GET", f"/api/stocks/{symbol}/candles", params={"interval": interval, "count": count})["candles"]

    def orderbook(self, symbol):
        return self._req("GET", f"/api/stocks/{symbol}/orderbook")

    def order(self, symbol, side, quantity, price=None):
        if side == "BUY":  # 매도는 막지 않는다 (많이 오른 종목을 못 파는 일이 없게)
            self._check_size(symbol, side, quantity, price)
        body = {"symbol": symbol, "order_code": side, "quantity": int(quantity)}
        if price is not None:
            body["price"] = int(price)
        return self._req("POST", "/api/orders", json=body)

    def _check_size(self, symbol, side, quantity, price):
        est = int(quantity) * (price or self.prices([symbol])[symbol])
        total = self.portfolio()["totalAssetValue"]
        if est > total * MAX_ORDER_RATIO:
            raise AquaError(0, "ORDER_TOO_LARGE",
                            f"{symbol} {side} {int(quantity)}주 ≈ {est:,.0f}원이 총자산의 {MAX_ORDER_RATIO:.0%}({total * MAX_ORDER_RATIO:,.0f}원) 초과 → 주문 안 함")

    def cancel(self, order_id):
        return self._req("DELETE", f"/api/orders/{order_id}")

    def orders(self, status=None, page=0, size=100):
        return self._req("GET", "/api/orders", params={"status": status, "page": page, "size": size})

    def limit(self):
        return self._req("GET", "/api/orders/limit")

    def portfolio(self):
        return self._req("GET", "/api/portfolio")
