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
    df = pyupbit.get_ohlcv(f"{COIN_NAME}", count=30, interval="day")

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
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are an expert in crypto investing.\n"
                            "Decide whether to buy, sell, or hold based on the provided OHLCV data and sentiment data.\n"
                            "Use Fear & Greed Index only as a supplementary signal (it may reflect broad market sentiment, not ETC-specific).\n"
                            "Respond in JSON format only.\n\n"
                            "Response Example:\n"
                            "{\"decision\": \"buy\", \"reason\": \"some technical reason\"}\n"
                            "{\"decision\": \"sell\", \"reason\": \"some technical reason\"}\n"
                            "{\"decision\": \"hold\", \"reason\": \"some technical reason\"}\n"
                        )
                    }
                ]
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
        response_format={"type": "json_object"}
    )

    result = response.choices[0].message.content

    # 3. AI의 판단에 따라 실제로 자동매매 진행하기
    result = json.loads(result)
    access = os.getenv("ACCESS_KEY_UPBIT")
    secret = os.getenv("SECRET_KEY_UPBIT")
    upbit = pyupbit.Upbit(access, secret)

    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Reason: {result['reason']} ###")

    current_price = pyupbit.get_orderbook(ticker=f"{COIN_NAME}")['orderbook_units'][0]["ask_price"]

    if result["decision"] == "buy":
        my_krw = upbit.get_balance("KRW")
        if (my_krw / 2) * 0.9995 > 5000:
            print("### Buy Order Executed ###")
            print(upbit.buy_market_order(f"{COIN_NAME}", (my_krw / 2) * 0.9995))
        else:
            print("### Buy Order Failed: Insufficient KRW (less than 5000 KRW) ###")

    elif result["decision"] == "sell":
        my_etc = upbit.get_balance(f"{COIN_NAME}")
        if (my_etc / 2) * current_price > 5000:
            print("### Sell Order Executed ###")
            print(upbit.sell_market_order(f"{COIN_NAME}", my_etc / 2))
        else:
            print("### Sell Order Failed: Insufficient ETC (less than 5000 KRW worth) ###")

    elif result["decision"] == "hold":
        print("### Hold Position ###")

    my_etc = upbit.get_balance(f"{COIN_NAME}")
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
