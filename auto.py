import os
from dotenv import load_dotenv
load_dotenv()

def ai_trading():
    # 1. 업비트 차트 데이터 가져오기 (30일 일봉)
    import pyupbit
    df = pyupbit.get_ohlcv("KRW-ETC", count=30, interval="day")

    # 2. AI에게 데이터 제공하고 판단 받기
    from openai import OpenAI
    API_KEY_OPENAI = os.getenv("SECRET_KEY_OPENAI")
    client = OpenAI(api_key = API_KEY_OPENAI)

    response = client.chat.completions.create(
    model="gpt-4.1",
    messages=[
        {
        "role": "system",
        "content": [
            {
            "type": "text",
            "text": "You are an expert in Bitcoin investing. Tell me whether to buy, sell, or hold at the moment based on the chart data provided. response in json format.\n\nResponse Example:\n{\"decision\": \"buy\", \"reason\": \"some technical reason\"}\n{\"decision\": \"sell\", \"reason\": \"some technical reason\"}\n{\"decision\": \"hold\", \"reason\": \"some technical reason\"}"
            }
        ]
        },
        {
        "role": "user",
        "content": [
            {
            "type": "text",
            "text": df.to_json()
            }
        ]
        }
    ],
    response_format={
        "type": "json_object"
    }
    )
    result = response.choices[0].message.content

    # 3. AI의 판단에 따라 실제로 자동매매 진행하기
    import json
    result = json.loads(result)
    import pyupbit
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")
    upbit = pyupbit.Upbit(access, secret)

    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Reason: {result['reason']} ###")

    if result["decision"] == "buy":
        my_krw = upbit.get_balance("KRW")
        if my_krw*0.9995 > 5000: # 수수료 0.05% -> (100-0.05)/100=0.9995
            print("### Buy Order Executed ###")
            print(upbit.buy_market_order("KRW-ETC", my_krw * 0.9995))
        else:
            print("### Buy Order Failed: Insufficient KRW (less than 5000 KRW) ###")
    elif result["decision"] == "sell":
        my_etc = upbit.get_balance("KRW-ETC")
        current_price = pyupbit.get_orderbook(ticker="KRW-ETC")['orderbook_units'][0]["ask_price"] # 시장가 추출
        if my_etc*current_price > 5000:
            print("### Sell Order Executed ###")
            print(upbit.sell_market_order("KRW-ETC", my_etc))
        else:
            print("### Sell Order Failed: Insufficient ETC (less than 5000 KRW worth) ###")
    elif result["decision"] == "hold":
        print("### Hold Position ###")
        
while True:
    import time
    time.sleep(4 * 60 * 60)  # 주기: (4시간 = 14400초)
    ai_trading()