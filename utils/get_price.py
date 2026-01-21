import pyupbit
from ta.utils import dropna
import ta
import os
from dotenv import load_dotenv
import pandas as pd

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    indicator_bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_bbm'] = indicator_bb.bollinger_mavg()
    df['bb_bbh'] = indicator_bb.bollinger_hband()
    df['bb_bbl'] = indicator_bb.bollinger_lband()

    df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=14).rsi()

    macd = ta.trend.MACD(close=df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_diff'] = macd.macd_diff()

    df['sma_20'] = ta.trend.SMAIndicator(close=df['close'], window=20).sma_indicator()
    df['ema_12'] = ta.trend.EMAIndicator(close=df['close'], window=12).ema_indicator()

    return df

def get_price(coin_name: str, *, tail: int = 10) -> list[dict]:
    df_hourly = pyupbit.get_ohlcv(coin_name, interval="minute60", count=24)
    if df_hourly is None or df_hourly.empty:
        return []

    df_hourly = dropna(df_hourly)
    df_hourly = add_indicators(df_hourly)

    safe = df_hourly.tail(tail).copy()
    safe = safe.where(pd.notnull(safe), None)

    safe = safe.reset_index().rename(columns={"index": "timestamp"})

    # ✅ 여기 추가: Timestamp -> ISO string
    safe["timestamp"] = safe["timestamp"].astype(str)
    # 또는 safe["timestamp"] = safe["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return safe.to_dict(orient="records")


if __name__ == "__main__":
    load_dotenv()
    access = os.getenv("UPBIT_ACCESS_KEY")
    secret = os.getenv("UPBIT_SECRET_KEY")

    coin_name = "KRW-BTC"
    hourly_records = get_price(coin_name, tail=10)
    print(hourly_records)  # JSON 직렬화 가능
