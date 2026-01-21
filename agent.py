# agent.py
import json
from dataclasses import dataclass
from openai import OpenAI
from trade_guide import Util_Funcs, Cooltime
from dotenv import load_dotenv
import pandas as pd
import os
import time
import pyupbit
from datetime import datetime, timedelta
from utils.db_utils import DataBase
from coin_cand import top_liquid_coins, make_liquidity_row

@dataclass
class TradingDecision:
    decision: str
    percentage: int
    reason: str

###################### prompts ######################
# ✅ agent_prompt: "분석 지침"만 남김 (출력 규칙은 아래 OUTPUT CONTRACT로 이동)
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

# ✅ JSON schema(설명용).
output_schema = {
    "decision": "buy | sell | hold",
    "percentage": "integer (hold=0, buy/sell=1..100)",
    "reason": "string"
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
##########################################################


class Agent_openai:
    def __init__(self, base_url: str, api_key: str, model: str, agent_prompt=agent_prompt,
                 max_tokens: int = 512, temperature: float = 0.1):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.agent_prompt = agent_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.output_contract = output_contract
        self.output_schema = output_schema

    def decide(self, informs: dict) -> TradingDecision:
        system_content = (
            f"{self.agent_prompt}\n\n"
            f"[Recent trading reflection]\n{informs['reflection']}\n\n"
            f"[trading method transcript]\n{informs['youtube_transcript']}\n\n"
            f"[OUTPUT CONTRACT]\n{self.output_contract}\n\n"
            f"[JSON SCHEMA]\n{json.dumps(self.output_schema, ensure_ascii=False)}\n"
        )

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": json.dumps(informs, ensure_ascii=False)},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        raw = resp.choices[0].message.content.strip()
        data = json.loads(raw)  # 필요 시 여기서 리트라이/검증 추가

        return TradingDecision(
            decision=data["decision"],
            percentage=int(data["percentage"]),
            reason=data["reason"],
        )

##################################################################
if __name__ == "__main__":
    load_dotenv()

    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    if not access or not secret:
        raise RuntimeError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 가 .env에 없습니다.")

    upbit = pyupbit.Upbit(access, secret)
    DRY_RUN = os.getenv("DRY_RUN", "1") == "1"

    database = DataBase()
    equity_first = None

    # === 유동성 스캔: 최초 1회 즉시 수행 + 이후 25시간 주기 ===
    SCAN_EVERY = timedelta(hours=25)
    next_scan_at = datetime.min  # 시작하자마자 스캔

    coin_candidates = ["KRW-BTC"]

    video_id = "-UJHObtnp5A"

    # === 유튜브 스크립트는 1회만 캐싱 ===
    # (IP block 피하려면 이 1회도 자주 실행하지 말고, 가능하면 파일/DB 캐시 추천)
    youtube_transcript = ""
    try:
        tmp = Util_Funcs.set_params(coin_name="KRW-BTC", video_id=video_id)
        youtube_transcript = tmp.get_vid_script(video_id)
    except Exception as e:
        print("youtube transcript fetch failed -> continue without transcript:", e)
        youtube_transcript = ""

    agent = Agent_openai(
        base_url="http://127.0.0.1:9000/v1",
        api_key="local-token",
        model="stelterlab/Mistral-Small-24B-Instruct-2501-AWQ",
        max_tokens=256,
        temperature=0.1,
    )

    KRW_MARKETS = set(pyupbit.get_tickers(fiat="KRW"))

    while True:
        now = datetime.now()

        # ===== 유동성 후보코인 스캔 =====
        if now >= next_scan_at:
            KRW_MARKETS = set(pyupbit.get_tickers(fiat="KRW"))
            top_k = top_liquid_coins(score_days=10, verbose=True)  # [(ticker, score), ...]
            row_fn = make_liquidity_row()
            database.log_liquidity_scan(top_k, row_fn)

            coin_candidates = [t for t, _ in top_k] or coin_candidates
            next_scan_at = now + SCAN_EVERY

        for coin_name in coin_candidates:
            base_currency = coin_name.split("-")[1]

            # ===== 코인별 util_funcs 재생성 =====
            # 핵심: get_vid_script를 "캐시 반환"으로 덮어써서 run_all()이 유튜브 재호출 못하게 막음
            util_funcs = Util_Funcs.set_params(
                coin_name=coin_name,
                video_id=video_id,
                rss={"limit": 10, "summary_len": 300, "content_len": 600},
                get_vid_script=(lambda _vid: youtube_transcript),
            )

            informs = util_funcs.run_all()

            decision = agent.decide(informs)

            result = {
                "decision": decision.decision,
                "percentage": int(decision.percentage),
                "reason": decision.reason,
            }

            percent = max(0, min(100, int(result["percentage"])))
            if result["decision"] == "hold":
                percent = 0

            print("### AI Decision:", result["decision"].upper(), "###")
            print(f"### Percentage: {percent}% ###")
            print(f"### Reason: {result['reason']} ###")
            print("### DRY_RUN:", DRY_RUN, "###")
            print("### coin:", coin_name, "###")

            current_price = float(pyupbit.get_orderbook(ticker=coin_name)["orderbook_units"][0]["ask_price"])
            order_executed = False

            # ===== 주문 =====
            if result["decision"] == "buy":
                my_krw = float(upbit.get_balance("KRW") or 0.0)
                spend = my_krw * (percent / 100) * 0.9995
                if spend > 5000:
                    if DRY_RUN:
                        print("### DRY_RUN: buy_market_order not sent ###")
                    else:
                        print(upbit.buy_market_order(coin_name, spend))
                        order_executed = True

            elif result["decision"] == "sell":
                my_coin = float(upbit.get_balance(base_currency) or 0.0)
                sell_qty = my_coin * (percent / 100)
                if sell_qty * current_price > 5000:
                    if DRY_RUN:
                        print("### DRY_RUN: sell_market_order not sent ###")
                    else:
                        print(upbit.sell_market_order(coin_name, sell_qty))
                        order_executed = True

            time.sleep(1)

            # ===== 잔고/총자산 =====
            balances = upbit.get_balances() or []

            base_row = next((b for b in balances if b.get("currency") == base_currency), None)
            coin_balance = 0.0
            if base_row:
                coin_balance = float(base_row.get("balance") or 0.0) + float(base_row.get("locked") or 0.0)

            krw_row = next((b for b in balances if b.get("currency") == "KRW"), None)
            krw_balance = 0.0
            if krw_row:
                krw_balance = float(krw_row.get("balance") or 0.0) + float(krw_row.get("locked") or 0.0)

            total_equity = krw_balance

            for b in balances:
                cur = b.get("currency")
                if not cur or cur == "KRW":
                    continue

                qty = float(b.get("balance") or 0.0) + float(b.get("locked") or 0.0)
                if qty <= 0:
                    continue

                t = f"KRW-{cur}"

                # KRW 마켓 없는 코인은 평가 스킵 (Code not found 방지)
                if t not in KRW_MARKETS:
                    continue

                p = float(pyupbit.get_orderbook(ticker=t)["orderbook_units"][0]["ask_price"])
                total_equity += qty * p


            coin_avg_buy_price = next(
                (float(b.get("avg_buy_price") or 0.0) for b in balances if b.get("currency") == base_currency),
                0.0
            )

            equity_now = float(total_equity)
            if equity_first is None:
                equity_first = equity_now
            profit = equity_now - equity_first

            print(f"{datetime.now()}_profit: {profit}")

            # ===== DB log_trade() =====
            database.log_trade(
                result["decision"],
                percent if order_executed else 0,
                result["reason"],
                coin_name,
                coin_balance,
                krw_balance,
                coin_avg_buy_price,
                current_price,
                equity_now,
                profit,
            )

        time.sleep(1 * 60 * 30)  # 30 minutes
