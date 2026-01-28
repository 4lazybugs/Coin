import os, time, json
from datetime import datetime, timedelta
import pyupbit
from dotenv import load_dotenv
from utils.get_fear import get_fear_greed_index
from utils.get_reflection import get_recent_trades, generate_reflection
from utils.get_vid import get_vid_script
from utils.db_utils import DataBase
from utils.rss import fetch_rss_news
from coin_cand import top_liquid_coins, make_liquidity_row
from openai import OpenAI

load_dotenv()

# ✅ profit 계산 안정화: dict 대신 "첫 총자산"만 저장
equity_first = None

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
    global equity_first

    ##### call openai api #######################
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # for gpt
    # client = OpenAI(base_url="http://127.0.0.1:9000/v1")
    base_currency = coin_name.split("-")[1]

    system_content = (
        f"{system_prompt}\n\n"
        f"[Recent trading reflection]\n{reflection}\n\n"
        f"[Wonyyotti trading method transcript]\n{youtube_transcript}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4.1",
        # model="stelterlab/Mistral-Small-24B-Instruct-2501-AWQ",
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

    # ✅ 현재 티커 가격(해당 코인 트레이딩/로그용)
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

    # ✅ 체결 반영 대기
    time.sleep(1)

    # ✅ balances 1회로 통일 (가용+locked, 평균매입가, 총자산 계산에 모두 사용)
    balances = upbit.get_balances() or []

    # ✅ 트레이딩 대상 코인 보유수량(가용+locked) - 로그용
    base_row = next((b for b in balances if b.get("currency") == base_currency), None)
    coin_balance = 0.0
    if base_row:
        coin_balance = float(base_row.get("balance") or 0.0) + float(base_row.get("locked") or 0.0)

    # ✅ KRW 잔고(가용+locked) - 로그/총자산용
    krw_row = next((b for b in balances if b.get("currency") == "KRW"), None)
    if krw_row:
        krw_balance = float(krw_row.get("balance") or 0.0) + float(krw_row.get("locked") or 0.0)
    else:
        krw_balance = float(upbit.get_balance("KRW") or 0.0)

    # ✅ 가격 조회 최적화: 한 번에 current_price들 가져오기 (실패 시 개별 orderbook fallback)
    tickers = []
    qty_by_ticker = {}
    for b in balances:
        cur = b.get("currency")
        if not cur or cur == "KRW":
            continue

        qty = float(b.get("balance") or 0.0) + float(b.get("locked") or 0.0)
        if qty <= 0:
            continue

        ticker = f"KRW-{cur}"
        tickers.append(ticker)
        qty_by_ticker[ticker] = qty

    prices = {}
    if tickers:
        try:
            prices = pyupbit.get_current_price(tickers) or {}
        except Exception:
            prices = {}

    # ✅ 전체 포트폴리오 총자산(KRW 환산)
    total_equity = krw_balance
    for ticker, qty in qty_by_ticker.items():
        price = prices.get(ticker)

        # fallback: get_current_price가 누락/실패한 경우 개별 orderbook로 재시도
        if price is None:
            try:
                price = pyupbit.get_orderbook(ticker=ticker)["orderbook_units"][0]["ask_price"]
            except Exception:
                continue  # 가격 못 가져오면 스킵

        total_equity += qty * float(price)

    # ✅ 해당 트레이딩 코인의 평균 매입가(그대로 유지)
    coin_avg_buy_price = next(
        (float(b["avg_buy_price"]) for b in balances if b.get("currency") == base_currency),
        0.0
    )

    equity_now = total_equity

    # ✅ 첫 총자산 저장(세션 기준 profit)
    if equity_first is None:
        equity_first = equity_now
    profit = equity_now - equity_first

    now = datetime.now()
    print(f"{now}_profit: {profit}")

    return {
        "decision": result["decision"],
        "percent": percent,
        "order_executed": order_executed,
        "reason": result["reason"],
        "coin_name": coin_name,
        "coin_balance": coin_balance,
        "krw_balance": krw_balance,
        "coin_avg_buy_price": coin_avg_buy_price,
        "coin_krw_price": current_price,   # 트레이딩 코인 현재가
        "equity_now": equity_now,          # ✅ 포트폴리오 총자산
        "profit": profit,                  # ✅ 세션 시작 대비 총자산 변화
    }

def build_model_input(coin, df, fng, news_items):
    if isinstance(fng, list):
        fng = fng[0] if fng else {}
    return {
        "ticker": coin,
        "ohlcv_4days": json.loads(df.to_json()),
        "fear_greed_index": {
            "value": fng.get("value"),
            "classification": fng.get("value_classification"),
            "timestamp": fng.get("timestamp"),
            "note": "Fear & Greed Index is a broad crypto market sentiment proxy; use as a secondary signal."
        },
        "news": news_items or [],
        "data_attribution": {"fear_greed_source": fng.get("source")}
    }

if __name__ == "__main__":
    video_id = "-UJHObtnp5A"
    youtube_transcript = get_vid_script(video_id)

    SCAN_EVERY = timedelta(hours=25)
    next_scan_at = datetime.now()

    # ✅ 뉴스 갱신 주기 추가
    NEWS_EVERY = timedelta(hours=12)
    next_news_at = datetime.now()
    cached_news = []

    database = DataBase()
    coin_candidates = ['KRW-BTC']

    # ✅ 시작 시: DB에서 최신 cand 먼저 로드 + 예외처리
    try:
        latest = database.get_liq_cand(limit=20)
        coin_candidates = latest or coin_candidates
    except Exception as e:
        print(f"{datetime.now()}: Failed to load candidates from DB: {e}. Use default candidates.")

    # ✅ 시작하자마자 스캔 방지
    next_scan_at = datetime.now() + SCAN_EVERY

    while True:
        now = datetime.now()

        # ✅ 유동성 스캔(주기 도래 시에만)
        if now >= next_scan_at:
            print(f"{now}: Starting liquidity scan...")
            top_k = top_liquid_coins(score_days=10, verbose=True)
            row_fn = make_liquidity_row()
            database.log_liquidity_scan(top_k, row_fn)
            coin_candidates = [t for t, _ in top_k] or coin_candidates
            next_scan_at = now + SCAN_EVERY

        # ✅ 뉴스 갱신 (캐시)
        if now >= next_news_at:
            try:
                cached_news = fetch_rss_news(
                    feed_url="https://cryptopotato.com/feed/",
                    limit=10,
                    summary_len=200,
                    content_len=300
                )
                print(f"{now}: RSS news updated. items={len(cached_news)}")
            except Exception as e:
                print(f"{now}: RSS news fetch failed: {e}")
            next_news_at = now + NEWS_EVERY

        fear_greed_index = get_fear_greed_index(limit=1, date_format="kr")
        recent_trades = get_recent_trades()
        reflection = generate_reflection(recent_trades, {"fear_greed_index": fear_greed_index})

        for coin in coin_candidates:
            df = pyupbit.get_ohlcv(coin, count=200, interval="minute30")
            if df is None or df.empty:
                continue

            model_input = build_model_input(coin, df, fear_greed_index, cached_news)
            trade = ai_trading(coin, model_input, reflection, youtube_transcript)

            database.log_trade(
                trade["decision"],
                trade["percent"] if trade["order_executed"] else 0,
                trade["reason"],
                trade["coin_name"],
                trade["coin_balance"],
                trade["krw_balance"],
                trade["coin_avg_buy_price"],
                trade["coin_krw_price"],
                trade["equity_now"],
                trade["profit"]
            )

        time.sleep(1 * 60 * 180)  # 3hours pause before next iteration (원 코드 유지)