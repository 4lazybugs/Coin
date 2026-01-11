import os
from openai import OpenAI
from datetime import datetime, timedelta
import pandas as pd
from utils.db_utils import DataBase


def get_recent_trades(minutes=20, db_path="bitcoin_trades.db"):
    db = DataBase(db_path=db_path)
    conn = db.get_db_connection(db_path)

    since = (datetime.now() - timedelta(minutes=minutes)).isoformat()

    c = conn.cursor()
    c.execute(
        "SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC",
        (since,),
    )

    columns = [col[0] for col in c.description]
    rows = c.fetchall()
    conn.close()

    return pd.DataFrame.from_records(rows, columns=columns)

def calculate_performance(trades_df):
    if trades_df is None or trades_df.empty:
        return 0.0

    initial_equity = (
        float(trades_df.iloc[-1]["krw_balance"]) +
        float(trades_df.iloc[-1]["asset_balance"]) *
        float(trades_df.iloc[-1]["asset_krw_price"])
    )

    final_equity = (
        float(trades_df.iloc[0]["krw_balance"]) +
        float(trades_df.iloc[0]["asset_balance"]) *
        float(trades_df.iloc[0]["asset_krw_price"])
    )

    if initial_equity == 0:
        return 0.0

    return (final_equity - initial_equity) / initial_equity * 100.0


def generate_reflection(trades_df: pd.DataFrame, current_market_data) -> str:
    """
    최근 거래 로그 + 현재 시장 데이터 기반으로 LLM 리플렉션 생성.
    """
    performance = calculate_performance(trades_df)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    safe_df = trades_df.copy() if trades_df is not None else pd.DataFrame()
    if not safe_df.empty:
        safe_df = safe_df.where(pd.notnull(safe_df), None)

    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL_REFLECTION", "gpt-4o-2024-08-06"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI trading assistant tasked with analyzing recent trading performance "
                    "and current market conditions to generate insights and improvements for future trading decisions."
                ),
            },
            {
                "role": "user",
                "content": f"""
Recent trading data:
{safe_df.to_json(orient='records', force_ascii=False)}

Current market data:
{current_market_data}

Overall performance in the last 20 minutes: {performance:.2f}%

Please analyze this data and provide:
1. A brief reflection on the recent trading decisions
2. Insights on what worked well and what didn't
3. Suggestions for improvement in future trading decisions
4. Any patterns or trends you notice in the market data

Limit your response to 250 words or less.
""",
            },
        ],
    )

    return response.choices[0].message.content
