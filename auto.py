import os, time
from datetime import datetime
import pyupbit
from dotenv import load_dotenv
load_dotenv()

COIN_NAME = 'KRW-ETC'
equity_list = {} 

def ai_trading():
    # 1. 업비트 차트 데이터 가져오기 (30일 일봉)
    df = pyupbit.get_ohlcv(f"{COIN_NAME}", count=30, interval="day")

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
    import sys
    result = json.loads(result)
    access = os.getenv("ACCESS_KEY_UPBIT")
    secret = os.getenv("SECRET_KEY_UPBIT")
    upbit = pyupbit.Upbit(access, secret)
    
    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Reason: {result['reason']} ###")

    current_price = pyupbit.get_orderbook(ticker=f"{COIN_NAME}")['orderbook_units'][0]["ask_price"] # 코인 시장가 추출
    
    if result["decision"] == "buy":
        my_krw = upbit.get_balance("KRW")
        # 우선 매수/매도 시 50%씩 팔기
        if (my_krw/2)*0.9995 > 5000: # 수수료 0.05% -> (100-0.05)/100=0.9995
            print("### Buy Order Executed ###")
            # my_krw/2만큼 코인 구매
            print(upbit.buy_market_order(f"{COIN_NAME}", (my_krw/2) * 0.9995)) # 수수료 0.05% -> (100-0.05)/100=0.9995 
        else:
            print("### Buy Order Failed: Insufficient KRW (less than 5000 KRW) ###")

    elif result["decision"] == "sell":
        my_etc = upbit.get_balance(f"{COIN_NAME}")
        if (my_etc/2)*current_price > 5000:
            print("### Sell Order Executed ###")
            # my_etc/2만큼 코인 판매
            print(upbit.sell_market_order(f"{COIN_NAME}", my_etc/2))
        else:
            print("### Sell Order Failed: Insufficient ETC (less than 5000 KRW worth) ###")

    elif result["decision"] == "hold":
        print("### Hold Position ###")

    my_etc = upbit.get_balance(f"{COIN_NAME}")
    my_krw = upbit.get_balance("KRW")
    if my_etc is None:
        equity_now = my_krw 
    else:
        equity_now = my_krw + my_etc*current_price 

    now = datetime.now()
    equity_list[now] = equity_now
    #breakpoint()
    profit = equity_list[now]- list(equity_list.items())[0][1]
    print(f"{now}_profit: {profit}")

if __name__ == "__main__":
    while True:
        ai_trading()
        time.sleep(4 * 60 * 60)  # 주기: (4시간 = 14400초)