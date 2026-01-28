import os
import time
import traceback
from datetime import datetime, timedelta

import pandas as pd
from openai import OpenAI

from .db_utils import DataBase
from .llm_lock import LLM_CALL_LOCK  # ✅ 추가


def trades_df_to_records(trades_df: pd.DataFrame, tail: int = 30) -> list[dict]:
    if trades_df is None or trades_df.empty:
        return []
    safe_df = trades_df.tail(tail).copy()
    safe_df = safe_df.where(pd.notnull(safe_df), None)
    return safe_df.to_dict(orient="records")


def get_recent_trades(minutes=20, db_path="bitcoin_trades.db") -> pd.DataFrame:
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


def calculate_performance(trades_df: pd.DataFrame) -> float:
    if trades_df is None or trades_df.empty:
        return 0.0

    initial_equity = (
        float(trades_df.iloc[-1]["krw_balance"])
        + float(trades_df.iloc[-1]["asset_balance"]) * float(trades_df.iloc[-1]["asset_krw_price"])
    )
    final_equity = (
        float(trades_df.iloc[0]["krw_balance"])
        + float(trades_df.iloc[0]["asset_balance"]) * float(trades_df.iloc[0]["asset_krw_price"])
    )

    if initial_equity == 0:
        return 0.0

    return (final_equity - initial_equity) / initial_equity * 100.0


def generate_reflection(trades_df: pd.DataFrame, current_market_data) -> str:
    base_url = os.getenv("LOCAL_OPENAI_BASE_URL", "http://127.0.0.1:9000/v1")
    api_key = os.getenv("LOCAL_OPENAI_API_KEY", "local-token")
    model = os.getenv("LOCAL_OPENAI_MODEL_REFLECTION", "stelterlab/Mistral-Small-24B-Instruct-2501-AWQ")
    timeout_s = float(os.getenv("LOCAL_OPENAI_TIMEOUT", "60"))

    # (선택) trades가 없으면 LLM 호출 스킵하고 짧게 반환
    # if trades_df is None or trades_df.empty:
    #     return "No trades in the last window; reflection skipped."

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        max_retries=0,
        timeout=timeout_s,
    )

    safe_df = trades_df.tail(30).copy() if trades_df is not None else pd.DataFrame()

    # ✅ 입력 축소: 핵심 컬럼만 유지 (테이블 컬럼 많을수록 효과 큼)
    KEEP_COLS = [
        "timestamp", "decision", "percentage",
        "krw_balance", "asset_balance", "asset_krw_price",
        "reason",
    ]
    if not safe_df.empty:
        safe_df = safe_df[[c for c in KEEP_COLS if c in safe_df.columns]].copy()
        safe_df = safe_df.where(pd.notnull(safe_df), None)
        if "reason" in safe_df.columns:
            safe_df["reason"] = safe_df["reason"].astype(str).str.slice(0, 200)

    performance = calculate_performance(safe_df)

    messages = [
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

Limit your response to 200 words or less.
""".strip(),
        },
    ]

    t0 = time.perf_counter()
    try:
        # ✅ 핵심: 단일 GPU 큐 밀림 방지(직렬화)
        with LLM_CALL_LOCK:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=180,
                temperature=0.2,
            )

        text = (resp.choices[0].message.content or "").strip()
        return text

    except Exception as e:
        print("[ERROR] reflection LLM call failed:", repr(e))
        print(traceback.format_exc())
        raise

    finally:
        print(f"[TIMING] reflection LLM call: {(time.perf_counter() - t0):.3f}s")

if __name__ == "__main__":
    print("[1] get_recent_trades...")
    df = get_recent_trades(minutes=20)
    print("[2] rows:", len(df), "cols:", (0 if df is None else len(df.columns)))

    market_data = {"fear_greed_index": {"value": 0}}

    print("[3] generate_reflection (LLM call)...")
    out = generate_reflection(df, market_data)
    print("[4] done")
    print(out)
