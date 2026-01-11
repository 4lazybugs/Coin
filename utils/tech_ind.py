import os
import pyupbit
import pandas as pd
from utils import get_config
from ta.volatility import BollingerBands

CFG = get_config()
COIN_NAME = CFG["COIN_NAME"]

df = pyupbit.get_ohlcv(COIN_NAME, count=30, interval="day")

os.makedirs("data", exist_ok=True)

out = df.reset_index().rename(columns={"index": "date"})
out["date"] = out["date"].dt.strftime("%Y-%m-%d %H:%M")  # 문자열로 변환
out.index.name = "Timestamp"
out.to_excel("data/ohlcv.xlsx", index=False)


df_ta = out.copy()

# 4) Bollinger Bands 계산
indicator_bb = BollingerBands(close=out["close"], window=5, window_dev=2, fillna=True)

df_ta["bb_bbm"] = indicator_bb.bollinger_mavg()
df_ta["bb_bbh"] = indicator_bb.bollinger_hband()
df_ta["bb_bbl"] = indicator_bb.bollinger_lband()

df_ta["bb_bbhi"] = indicator_bb.bollinger_hband_indicator()
df_ta["bb_bbli"] = indicator_bb.bollinger_lband_indicator()

df_ta["bb_bbw"] = indicator_bb.bollinger_wband()
df_ta["bb_bbp"] = indicator_bb.bollinger_pband()

# 5) 저장(엑셀)
os.makedirs("data", exist_ok=True)

out = df_ta.reset_index().rename(columns={"index": "date"})
out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d %H:%M")  # 문자열로 변환
out.index.name = "Timestamp"

out.to_excel("data/ohlcv.xlsx", index=False)