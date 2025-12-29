import os
import pyupbit
import pandas as pd
from utils import get_config

CFG = get_config()
COIN_NAME = CFG["COIN_NAME"]

df = pyupbit.get_ohlcv(COIN_NAME, count=30, interval="day")

os.makedirs("data", exist_ok=True)

out = df.reset_index().rename(columns={"index": "date"})
out["date"] = out["date"].dt.strftime("%Y-%m-%d %H:%M")  # 문자열로 변환
out.index.name = "Timestamp"
out.to_excel("data/ohlcv.xlsx", index=False)
