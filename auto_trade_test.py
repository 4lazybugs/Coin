# agent_auto.py
from __future__ import annotations

# =========================================================
# ✅ (0) 스크립트 실행(python agent_auto.py)에서도 로컬 import가 깨지지 않게
#     - 반드시 "로컬 모듈 import 이전"에 sys.path 세팅
# =========================================================
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import os
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict

import httpx
import pyupbit
from dotenv import load_dotenv
from openai import OpenAI

# ✅ 사용자 프로젝트 모듈(참고 코드 구조 유지)
import utils
from utils.llm_lock import LLM_CALL_LOCK
from utils.db_utils import DataBase

# (선택) 참고 코드에서 쓰던 유동성 스캔 모듈이 있다면 그대로 사용
# 없으면 아래 try/except로 KRW-BTC 단일 운용도 가능하게 처리했습니다.
try:
    from coin_cand import top_liquid_coins, make_liquidity_row
    HAS_LIQ_SCAN = True
except Exception:
    HAS_LIQ_SCAN = False

# (선택) 유튜브 스크립트 모듈이 있다면 사용
try:
    from utils.get_vid import get_vid_script
    HAS_YOUTUBE = True
except Exception:
    HAS_YOUTUBE = False


@dataclass
class TradingDecision:
    decision: str
    percentage: int
    reason: str


###################### prompts ######################
agent_prompt = """You are an expert in Coin investing.

Analyze the provided data and decide the best action based on:
- Technical indicators and market data
- Recent news headlines and their potential impact on Coin price
- The Fear and Greed Index and its implications
- Overall market sentiment
- Patterns and trends visible in the chart data
- Insights from the YouTube transcript

Be risk-aware and prioritize capital preservation when signals are mixed or uncertain.
"""

output_schema = {
    "decision": "buy | sell | hold",
    "percentage": "integer (hold=0, buy/sell=1..100)",
    "reason": "string",
}

output_contract = """[OUTPUT CONTRACT]
- Output MUST be a single JSON object and NOTHING ELSE.
- Do NOT use markdown. Do NOT use code fences.
- Output must start with '{' and end with '}'.
- Keys must be exactly: decision, percentage, reason.
- decision must be one of: buy, sell, hold.
- If decision == 'hold', percentage MUST be 0.
- If decision in ['buy','sell'], percentage MUST be an integer 1..100.
- No additional keys.
"""
######################################################


class Agent_openai:
    """
    ✅ 사용자가 주신 첫 번째 코드 스타일(HTTPX timeout 커스텀 + OpenAI(base_url))
    ✅ 최대한 보존
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        agent_prompt: str = agent_prompt,
        max_tokens: int = 256,
        temperature: float = 0.1,
        timeout_connect: float = 5.0,
        timeout_read: float = 180.0,
    ):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            # ✅ httpx timeout 커스텀(첫 번째 코드 그대로)
            http_client=httpx.Client(
                timeout=httpx.Timeout(
                    connect=timeout_connect,
                    read=timeout_read,
                    write=30.0,
                    pool=5.0,
                )
            ),
        )
        self.model = model
        self.agent_prompt = agent_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature

    def decide(self, informs: dict) -> TradingDecision:
        system_content = (
            f"{self.agent_prompt}\n\n"
            f"{output_contract}\n\n"
            f"[JSON SCHEMA]\n{json.dumps(output_schema, ensure_ascii=False)}\n"
        )

        # ✅ 원본 코드의 user_content 구성 방식 보존
        user_content = (
            f"[Recent coin_price]\n{informs.get('coin_price', '')}\n\n"
            f"[Recent fear_greed_index]\n{informs.get('fear_greed_index', '')}\n\n"
            f"[Recent news]\n{informs.get('news', '')}\n\n"
            f"[Recent trading reflection]\n{informs.get('reflection', '')}\n\n"
            f"[trading method transcript]\n{informs.get('youtube_transcript', '')}\n\n"
        )

        print("System content length:", len(system_content))
        print("User content length:", len(user_content))
        print("All information has been prepared. Making decision...")

        with LLM_CALL_LOCK:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

        raw = (resp.choices[0].message.content or "").strip()

        # ✅ 참고 코드처럼 JSON 파싱 방어 로직만 추가(계약 위반 대비)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            l = raw.find("{")
            r = raw.rfind("}")
            if l != -1 and r != -1 and r > l:
                data = json.loads(raw[l : r + 1])
            else:
                raise

        return TradingDecision(
            decision=str(data["decision"]).strip().lower(),
            percentage=int(data["percentage"]),
            reason=str(data["reason"]),
        )


def clamp_percent(decision: str, pct: int) -> int:
    pct = int(pct)
    if decision == "hold":
        return 0
    return max(1, min(100, pct))


def safe_get_current_price(coin_name: str) -> float:
    ob = pyupbit.get_orderbook(ticker=coin_name)
    return float(ob["orderbook_units"][0]["ask_price"])


def calc_total_equity_krw(upbit: pyupbit.Upbit, KRW_MARKETS: set[str]) -> tuple[float, float, list]:
    """
    total_equity(KRW) = KRW 잔고 + (보유 코인들 * 현재가)
    반환: (krw_balance, total_equity, balances_raw)
    """
    balances = upbit.get_balances() or []

    # KRW
    krw_row = next((b for b in balances if b.get("currency") == "KRW"), None)
    krw_balance = 0.0
    if krw_row:
        krw_balance = float(krw_row.get("balance") or 0.0) + float(krw_row.get("locked") or 0.0)

    total_equity = float(krw_balance)

    # coins
    for b in balances:
        cur = b.get("currency")
        if not cur or cur == "KRW":
            continue

        qty = float(b.get("balance") or 0.0) + float(b.get("locked") or 0.0)
        if qty <= 0:
            continue

        t = f"KRW-{cur}"
        if t not in KRW_MARKETS:
            continue

        try:
            p = safe_get_current_price(t)
        except Exception:
            continue

        total_equity += qty * p

    return krw_balance, total_equity, balances


def get_coin_balance(balances: list, base_currency: str) -> tuple[float, float]:
    """
    base_currency: 예) BTC
    반환: (coin_balance_total, avg_buy_price)
    """
    base_row = next((b for b in balances if b.get("currency") == base_currency), None)
    coin_balance = 0.0
    avg_buy = 0.0
    if base_row:
        coin_balance = float(base_row.get("balance") or 0.0) + float(base_row.get("locked") or 0.0)
        avg_buy = float(base_row.get("avg_buy_price") or 0.0)
    return coin_balance, avg_buy


def main():
    # =========================================================
    # ✅ (1) 환경 로드 / 기본 설정
    # =========================================================
    load_dotenv()

    access = os.getenv("UPBIT_ACCESS_KEY", "")
    secret = os.getenv("UPBIT_SECRET_KEY", "")
    
    BASE_URL = os.getenv("LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:9000/v1")
    API_KEY = os.getenv("LOCAL_OPENAI_API_KEY", "not-used")
    MODEL_NAME = "unsloth/Mistral-Small-24B-Instruct-2501-bnb-4bit"

    # 뉴스 RSS 설정(첫 코드 스타일 util.fetch_rss_news에 맞춰 전달)
    RSS_URL = os.getenv("RSS_FEED_URL", "https://www.cryptobreaking.com/feed/")

    # 실행 파라미터
    SCAN_EVERY = timedelta(hours=float(os.getenv("SCAN_EVERY_HOURS", "25")))
    SLEEP_EVERY = int(os.getenv("SLEEP_EVERY_SECONDS", str(30 * 60)))  # 기본 30분

    # 운용 설정
    MIN_KRW_ORDER = float(os.getenv("MIN_KRW_ORDER", "5000"))  # 업비트 최소 주문
    SLIPPAGE_FEE_FACTOR = float(os.getenv("FEE_FACTOR", "0.9995"))  # 대략 수수료/슬리피지 보정

    # 초기 후보
    coin_candidates = [os.getenv("DEFAULT_TICKER", "KRW-BTC")]

    # 유튜브 (선택)
    video_id = os.getenv("YOUTUBE_VIDEO_ID", "e-QmGJU1XYc")

    # =========================================================
    # ✅ (2) 클라이언트/DB 초기화
    # =========================================================
    upbit = pyupbit.Upbit(access, secret)
    database = DataBase()

    # KRW 마켓 캐시
    KRW_MARKETS = set(pyupbit.get_tickers(fiat="KRW"))

    # 수익 기준점
    equity_first = None

    # 유동성 스캔 스케줄
    next_scan_at = datetime.min

    # =========================================================
    # ✅ (3) 유튜브 트랜스크립트 1회 캐시 (가능할 때만)
    # =========================================================
    youtube_transcript = ""
    if HAS_YOUTUBE:
        try:
            youtube_transcript = get_vid_script(BASE_URL, API_KEY, video_id) or ""
            youtube_transcript = youtube_transcript[:4000]
        except Exception as e:
            print("[YOUTUBE FAIL] -> continue without transcript:", repr(e))
            youtube_transcript = ""

    # =========================================================
    # ✅ (4) Agent 생성
    # =========================================================
    agent = Agent_openai(
        base_url=BASE_URL,
        api_key=API_KEY,
        model=MODEL_NAME,
        max_tokens=256,
        temperature=0.1,
        timeout_connect=float(os.getenv("LOCAL_OPENAI_TIMEOUT_CONNECT", "5")),
        timeout_read=float(os.getenv("LOCAL_OPENAI_TIMEOUT_READ", "180")),
    )
    print("Agent initialized.")

    # =========================================================
    # ✅ (5) 메인 루프
    # =========================================================
    while True:
        now = datetime.now()

        # ---------------------------------------------------------
        # (A) 유동성 후보코인 스캔(모듈 있을 때만)
        # ---------------------------------------------------------
        if now >= next_scan_at:
            try:
                KRW_MARKETS = set(pyupbit.get_tickers(fiat="KRW"))

                if HAS_LIQ_SCAN:
                    top_k = top_liquid_coins(score_days=10, verbose=True)
                    row_fn = make_liquidity_row()
                    database.log_liquidity_scan(top_k, row_fn)
                    coin_candidates = [t for t, _ in top_k] or coin_candidates
                else:
                    # 모듈이 없으면 기존 후보 유지(기본 KRW-BTC)
                    pass

                next_scan_at = now + SCAN_EVERY
            except Exception as e:
                print("[LIQUIDITY SCAN FAIL] keep previous candidates:", repr(e))
                next_scan_at = now + timedelta(minutes=30)

        # ---------------------------------------------------------
        # (B) 코인별 실행
        # ---------------------------------------------------------
        for coin_name in coin_candidates:
            try:
                base_currency = coin_name.split("-")[1]  # KRW-BTC -> BTC
            except Exception:
                print("[SKIP] invalid ticker:", coin_name)
                continue

            # -----------------------------------------------------
            # (B-1) informs 구성
            #  - 사용자가 올린 첫 코드의 informs 구조(coin_price/fng/news/reflection/youtube_transcript) 유지
            # -----------------------------------------------------
            informs: Dict = {}

            # fear & greed
            try:
                fng = utils.get_fear_greed_index()
                # 첫 코드에선 fng["value"]만 넣었으니 동일하게
                informs["fear_greed_index"] = fng.get("value", "")
            except Exception as e:
                print("[FNG FAIL] -> empty:", repr(e))
                informs["fear_greed_index"] = ""

            # price (원본 코드에선 utils.get_price(coin_name="KRW-BTC"))
            try:
                informs["coin_price"] = utils.get_price(coin_name=coin_name)
            except Exception as e:
                print("[PRICE INFO FAIL] -> fallback to orderbook:", repr(e))
                try:
                    informs["coin_price"] = safe_get_current_price(coin_name)
                except Exception:
                    informs["coin_price"] = ""

            # news
            try:
                informs["news"] = utils.fetch_rss_news(feed_url=RSS_URL)
            except Exception as e:
                print("[NEWS FAIL] -> empty:", repr(e))
                informs["news"] = ""

            # reflection(없으면 빈 문자열)
            informs["reflection"] = informs.get("reflection", "")

            # youtube transcript(캐시)
            informs["youtube_transcript"] = youtube_transcript

            # -----------------------------------------------------
            # (B-2) Agent 결정
            # -----------------------------------------------------
            try:
                decision = agent.decide(informs)
            except json.JSONDecodeError as e:
                print("[AGENT JSON FAIL] -> hold:", repr(e))
                decision = TradingDecision(decision="hold", percentage=0, reason="LLM JSON parse failed")
            except Exception as e:
                print("[AGENT FAIL] -> hold:", repr(e))
                decision = TradingDecision(decision="hold", percentage=0, reason=str(e))

            percent = clamp_percent(decision.decision, decision.percentage)

            print("### AI Decision:", decision.decision.upper(), "###")
            print(f"### Percentage: {percent}% ###")
            print(f"### Reason: {decision.reason} ###")
            print("### coin:", coin_name, "###")

            # -----------------------------------------------------
            # (B-3) 현재가
            # -----------------------------------------------------
            try:
                current_price = safe_get_current_price(coin_name)
            except Exception as e:
                print("[PRICE FAIL] skip coin:", repr(e))
                continue

            # -----------------------------------------------------
            # (B-4) 주문/체결
            # -----------------------------------------------------
            order_executed = False
            order_resp = None

            try:
                if decision.decision == "buy":
                    my_krw = float(upbit.get_balance("KRW") or 0.0)
                    spend = my_krw * (percent / 100.0) * SLIPPAGE_FEE_FACTOR

                    if spend >= MIN_KRW_ORDER:
                        order_resp = upbit.buy_market_order(coin_name, spend)
                        print(order_resp)
                        if isinstance(order_resp, dict) and order_resp.get("uuid"):
                            order_executed = True
                    else:
                        print(f"[SKIP BUY] spend too small: {spend:.2f} KRW (min {MIN_KRW_ORDER})")

                elif decision.decision == "sell":
                    my_coin = float(upbit.get_balance(base_currency) or 0.0)
                    sell_qty = my_coin * (percent / 100.0)

                    if sell_qty * current_price >= MIN_KRW_ORDER:
                        order_resp = upbit.sell_market_order(coin_name, sell_qty)
                        print(order_resp)
                        if isinstance(order_resp, dict) and order_resp.get("uuid"):
                            order_executed = True
                    else:
                        print(f"[SKIP SELL] value too small: {sell_qty * current_price:.2f} KRW (min {MIN_KRW_ORDER})")
                else:
                    # hold
                    pass

            except Exception as e:
                print("[ORDER ERROR]", repr(e))
                order_executed = False

            # 체결/잔고 반영 시간(너무 짧으면 get_balances가 이전 값일 수 있음)
            time.sleep(1)

            # -----------------------------------------------------
            # (B-5) 잔고/총자산/수익 계산
            # -----------------------------------------------------
            try:
                krw_balance, total_equity, balances = calc_total_equity_krw(upbit, KRW_MARKETS)
                coin_balance, avg_buy_price = get_coin_balance(balances, base_currency)

                equity_now = float(total_equity)
                if equity_first is None:
                    equity_first = equity_now

                profit = equity_now - equity_first
                print(f"{datetime.now()}_profit: {profit}")

                # -------------------------------------------------
                # (B-6) DB 로그 저장
                # -------------------------------------------------
                database.log_trade(
                    decision.decision,
                    percent if order_executed else 0,
                    decision.reason,
                    coin_name,
                    coin_balance,
                    krw_balance,
                    avg_buy_price,
                    float(current_price),
                    equity_now,
                    float(profit),
                )

            except Exception as e:
                print("[EQUITY/LOG FAIL]", repr(e))

        time.sleep(SLEEP_EVERY)


if __name__ == "__main__":
    main()
