import os, time, json
from datetime import datetime
import requests
import pyupbit
from dotenv import load_dotenv
from get_fear import get_fear_greed_index

load_dotenv()
COIN_NAME = 'KRW-ETC'
equity_list = {}

def ai_trading():
    # 1. 업비트 차트 데이터 가져오기 (30일 일봉)
    df = pyupbit.get_ohlcv(COIN_NAME, count=30, interval="day")

    # 1-1. 공포 탐욕 지수 가져오기 (Alternative.me)
    fng = get_fear_greed_index(limit=1, date_format="kr")

    # (중요) Alternative.me 이용 규칙: 데이터 표시 바로 옆에 출처 표기
    # -> 콘솔 출력에 출처를 함께 보여주어 “prominently reference” 조건을 충족하도록 구성
    if fng.get("error"):
        print(f"[FNG] (Source: {fng['source']}) Fetch failed: {fng['error']}")
    else:
        print(
            f"[FNG] value={fng['value']} ({fng['value_classification']}), ts={fng['timestamp']} "
            f"(Source: {fng['source']})"
        )

    # 2. AI에게 데이터 제공하고 판단 받기
    from openai import OpenAI
    API_KEY_OPENAI = os.getenv("SECRET_KEY_OPENAI")
    client = OpenAI(api_key=API_KEY_OPENAI)

    # 모델에 전달할 입력을 하나의 JSON으로 구성 (차트 + FNG)
    model_input = {
        "ticker": COIN_NAME,
        "ohlcv_30d_daily": json.loads(df.to_json()),
        "fear_greed_index": {
            "value": fng.get("value"),
            "classification": fng.get("value_classification"),
            "timestamp": fng.get("timestamp"),
            "note": "Fear & Greed Index is a broad crypto market sentiment proxy (often BTC-weighted); use as a secondary signal for ETC."
        },
        "data_attribution": {
            "fear_greed_source": fng.get("source")
        }
    }

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "system",
                "content": """You are an expert in Bitcoin investing. Analyze the provided data including technical indicators, market data, recent news headlines, the Fear and Greed Index, YouTube video transcript, and the chart image. Tell me whether to buy, sell, or hold at the moment. Consider the following in your analysis:
                - Technical indicators and market data
                - Recent news headlines and their potential impact on Bitcoin price
                - The Fear and Greed Index and its implications
                - Overall market sentiment
                - The patterns and trends visible in the chart image
                - Insights from the YouTube video transcript
                
                Respond with:
                1. A decision (buy, sell, or hold)
                2. If the decision is 'buy', provide a percentage (1-100) of available KRW to use for buying.
                If the decision is 'sell', provide a percentage (1-100) of held BTC to sell.
                If the decision is 'hold', set the percentage to 0.
                3. A reason for your decision
                
                Ensure that the percentage is an integer between 1 and 100 for buy/sell decisions, and exactly 0 for hold decisions.
                Your percentage should reflect the strength of your conviction in the decision based on the analyzed data."""
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(model_input)
                    }
                ]
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "trading_decision",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "decision": {"type": "string", "enum": ["buy", "sell", "hold"]},
                        "percentage": {"type": "integer"},
                        "reason": {"type": "string"}
                    },
                    "required": ["decision", "percentage", "reason"],
                    "additionalProperties": False
                }
            }
        },
        max_tokens=4095
    )

    result = response.choices[0].message.content

    # 3. AI의 판단에 따라 실제로 자동매매 진행하기
    result = json.loads(result)
    access = os.getenv("ACCESS_KEY_UPBIT")
    secret = os.getenv("SECRET_KEY_UPBIT")
    upbit = pyupbit.Upbit(access, secret)

    pct = int(result["percentage"])
    pct = max(0, min(100, pct))  # 안전 클램프

    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Percentage: {pct}% ###")
    print(f"### Reason: {result['reason']} ###")

    current_price = pyupbit.get_orderbook(ticker=COIN_NAME)['orderbook_units'][0]["ask_price"]

    if result["decision"] == "buy":
        my_krw = upbit.get_balance("KRW")
        spend = my_krw * (pct / 100) * 0.9995  # 수수료 여유
        if spend > 5000:
            print("### Buy Order Executed ###")
            print(upbit.buy_market_order(COIN_NAME, spend))
        else:
            print("### Buy Order Failed: Insufficient KRW (less than 5000 KRW) ###")

    elif result["decision"] == "sell":
        my_etc = upbit.get_balance(COIN_NAME)
        sell_qty = my_etc * (pct / 100)
        if sell_qty * current_price > 5000:
            print("### Sell Order Executed ###")
            print(upbit.sell_market_order(COIN_NAME, sell_qty))
        else:
            print("### Sell Order Failed: Insufficient ETC (less than 5000 KRW worth) ###")

    elif result["decision"] == "hold":
        print("### Hold Position ###")

    my_etc = upbit.get_balance(COIN_NAME)
    my_krw = upbit.get_balance("KRW")
    if my_etc is None:
        equity_now = my_krw
    else:
        equity_now = my_krw + my_etc * current_price

    now = datetime.now()
    equity_list[now] = equity_now
    profit = equity_list[now] - list(equity_list.items())[0][1]
    print(f"{now}_profit: {profit}")

if __name__ == "__main__":
    while True:
        ai_trading()
        time.sleep(1 * 60 * 60)  # 주기: 1시간
