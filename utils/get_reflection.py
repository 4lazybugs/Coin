import os
from openai import OpenAI
from datetime import datetime, timedelta
import pandas as pd
from utils.db_utils import DataBase


def get_recent_trades(days=7, db_path='bitcoin_trades.db'):
    # ✅ get_db_connection() 미정의 문제 해결: DataBase 인스턴스 통해 연결
    db = DataBase(db_path=db_path)
    conn = db.get_db_connection(db_path)

    seven_days_ago = (datetime.now() - timedelta(days=days)).isoformat()

    c = conn.cursor()
    c.execute(
        "SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC",
        (seven_days_ago,)
    )

    columns = [column[0] for column in c.description]
    rows = c.fetchall()

    conn.close()  # 여기서 닫아도 됨 (별도 커넥션이므로)

    return pd.DataFrame.from_records(data=rows, columns=columns)


def calculate_performance(trades_df):
    if trades_df is None or trades_df.empty:
        return 0.0

    # ✅ 컬럼명은 btc_*로 되어 있어도 "코인"으로 해석하면 됨 (ETC도 동일 컬럼에 저장 중)
    initial_balance = (
        float(trades_df.iloc[-1]['krw_balance']) +
        float(trades_df.iloc[-1]['btc_balance']) * float(trades_df.iloc[-1]['btc_krw_price'])
    )
    final_balance = (
        float(trades_df.iloc[0]['krw_balance']) +
        float(trades_df.iloc[0]['btc_balance']) * float(trades_df.iloc[0]['btc_krw_price'])
    )

    if initial_balance == 0:
        return 0.0

    return (final_balance - initial_balance) / initial_balance * 100.0


def generate_reflection(trades_df, current_market_data):
    performance = calculate_performance(trades_df)

    # ✅ 위 코드와 동일하게 API 키 사용 (dotenv 로드되어 있으면 환경변수로 들어옴)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ✅ JSON 직렬화 안정화(최소): NaN -> None
    safe_df = trades_df.copy() if trades_df is not None else pd.DataFrame()
    if not safe_df.empty:
        safe_df = safe_df.where(pd.notnull(safe_df), None)

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL_REFLECTION", "gpt-4o-2024-08-06"),
        messages=[
            {
                "role": "system",
                "content": "You are an AI trading assistant tasked with analyzing recent trading performance and current market conditions to generate insights and improvements for future trading decisions."
            },
            {
                "role": "user",
                "content": f"""
Recent trading data:
{safe_df.to_json(orient='records', force_ascii=False)}

Current market data:
{current_market_data}

Overall performance in the last 7 days: {performance:.2f}%

Please analyze this data and provide:
1. A brief reflection on the recent trading decisions
2. Insights on what worked well and what didn't
3. Suggestions for improvement in future trading decisions
4. Any patterns or trends you notice in the market data

Limit your response to 250 words or less.
"""
            }
        ]
    )

    return response.choices[0].message.content
