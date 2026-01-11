import os, time, json
from datetime import datetime, timedelta
import pyupbit
from dotenv import load_dotenv
from utils.get_fear import get_fear_greed_index
from utils.get_reflection import get_recent_trades, generate_reflection
from utils.get_vid import get_vid_script
from utils.db_utils import DataBase
from coin_cand import top_liquid_coins, make_liquidity_row
from openai import OpenAI

load_dotenv()
equity_list = {}

###################### prompts ######################
system_prompt = """You are an expert in Bitcoin investing. Analyze the provided data including technical indicators, market data, recent news headlines, the Fear and Greed Index, YouTube video transcript, and the chart image. Tell me whether to buy, sell, or hold at the moment. Consider the following in your analysis:
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

output_schema = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["buy", "sell", "hold"]},
        "percentage": {"type": "integer"},
        "reason": {"type": "string"}
    },
    "required": ["decision", "percentage", "reason"],
    "additionalProperties": False
}

############### main functions #####################################
def ai_trading(coin_name, model_input, reflection=None, youtube_transcript=None):
    ##### call openai api #######################
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base_currency = coin_name.split("-")[1]

    system_content = (
        f"{system_prompt}\n\n"
        f"[Recent trading reflection]\n{reflection}\n\n"
        f"[Wonyyotti trading method transcript]\n{youtube_transcript}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": json.dumps(model_input, ensure_ascii=False)}
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "trading_decision", "strict": True, "schema": output_schema}
        },
        max_tokens=4095
    )

    result = json.loads(response.choices[0].message.content)

    ############### from now on, upbit codes #########################
    access, secret = os.getenv("ACCESS_KEY_UPBIT"), os.getenv("SECRET_KEY_UPBIT")
    upbit = pyupbit.Upbit(access, secret)

    percent = max(0, min(100, int(result["percentage"])))

    print("### AI Decision: ", result["decision"].upper(), "###")
    print(f"### Percentage: {percent}% ###")
    print(f"### Reason: {result['reason']} ###")

    current_price = pyupbit.get_orderbook(ticker=coin_name)["orderbook_units"][0]["ask_price"]
    order_executed = False

    if result["decision"] == "buy":
        my_krw = float(upbit.get_balance("KRW") or 0.0)
        spend = my_krw * (percent / 100) * 0.9995

        if spend > 5000:
            print("### Buy Order Executed ###")
            print(upbit.buy_market_order(coin_name, spend))
            order_executed = True
        else:
            print("### Buy Order Failed: Insufficient KRW (less than 5000 KRW) ###")

    elif result["decision"] == "sell":
        my_coin = float(upbit.get_balance(base_currency) or 0.0)
        sell_qty = my_coin * (percent / 100)

        if sell_qty * current_price > 5000:
            print("### Sell Order Executed ###")
            print(upbit.sell_market_order(coin_name, sell_qty))
            order_executed = True
        else:
            print("### Sell Order Failed: Insufficient coin (less than 5000 KRW worth) ###")

    else:
        print("### Hold Position ###")

    time.sleep(1)
    my_coin_raw, my_krw_raw = upbit.get_balance(base_currency), upbit.get_balance("KRW")
    coin_balance = float(my_coin_raw) if my_coin_raw else 0.0
    krw_balance = float(my_krw_raw) if my_krw_raw else 0.0

    balances = upbit.get_balances()
    coin_avg_buy_price = next((float(b["avg_buy_price"]) for b in balances if b.get("currency") == base_currency), 0.0)

    equity_now = krw_balance + coin_balance * current_price
    now = datetime.now()
    equity_list[(now, coin_name)] = equity_now
    profit = equity_now - list(equity_list.items())[0][1]
    print(f"{now}_{coin_name}_profit: {profit}")

    return {
        "decision": result["decision"],
        "percent": percent,
        "order_executed": order_executed,
        "reason": result["reason"],
        "coin_name": coin_name,
        "coin_balance": coin_balance,
        "krw_balance": krw_balance,
        "coin_avg_buy_price": coin_avg_buy_price,
        "coin_krw_price": current_price,
        "equity_now": equity_now,
        "profit": profit,
    }

def build_model_input(coin, df, fng):
    if isinstance(fng, list): fng = fng[0] if fng else {}
    return {
        "ticker": coin,
        "ohlcv_30d_daily": json.loads(df.to_json()),
        "fear_greed_index": {
            "value": fng.get("value"),
            "classification": fng.get("value_classification"),
            "timestamp": fng.get("timestamp"),
            "note": "Fear & Greed Index is a broad crypto market sentiment proxy; use as a secondary signal."
        },
        "data_attribution": {"fear_greed_source": fng.get("source")}
    }

if __name__ == "__main__":
    video_id = "5CfV4Afi1F4"
    youtube_transcript = get_vid_script(video_id)

    SCAN_EVERY = timedelta(hours=25)
    next_scan_at = datetime.now()

    database = DataBase()
    coin_candidates = ['KRW-BTC']

    while True:
        now = datetime.now()

        if now >= next_scan_at:
            print(f"{now}: Starting liquidity scan...")
            # score_days는 유동성 점수를 매기는 기준 구간
            top_k = top_liquid_coins(score_days=10, verbose=True)
            row_fn = make_liquidity_row()
            database.log_liquidity_scan(top_k, row_fn)
            coin_candidates = [t for t, _ in top_k] or coin_candidates
            next_scan_at = now + SCAN_EVERY

        fear_greed_index = get_fear_greed_index(limit=1, date_format="kr")
        recent_trades = get_recent_trades()
        reflection = generate_reflection(recent_trades, {"fear_greed_index": fear_greed_index})

        for coin in coin_candidates:
            df = pyupbit.get_ohlcv(coin, count=60, interval="minute1")
            if df is None or df.empty:
                continue

            model_input = build_model_input(coin, df, fear_greed_index)
            trade = ai_trading(coin, model_input, reflection, youtube_transcript)

            database.log_trade(
                trade["decision"],
                trade["percent"] if trade["order_executed"] else 0,
                trade["reason"],
                trade["coin_balance"],
                trade["krw_balance"],
                trade["coin_avg_buy_price"],
                trade["coin_krw_price"],
                trade["equity_now"],
                trade["profit"]
            )

        time.sleep(1 * 60 * 20) # 20 minutes pause before next iteration
