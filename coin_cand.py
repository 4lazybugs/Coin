import pyupbit
import time

LISTING_DAYS   = 30
PUMP_RATIO     = 8
MIN_TURNOVER   = 5_000_000_000
MAX_DAILY_RET  = 0.3

def get_ohlcv_retry(ticker, count, interval="day", sleep_sec=0.2, backoff=1.6, max_sleep=5.0, max_tries=None, verbose=False):
    """
    - None/empty 반환: 재시도
    - 예외(429/네트워크 등): 재시도
    - max_tries=None이면 무한 재시도
    """
    tries = 0
    wait = sleep_sec

    while True:
        tries += 1
        try:
            df = pyupbit.get_ohlcv(ticker, count=count, interval=interval)
            if df is not None and not df.empty:
                return df
            if verbose:
                print("no data -> retry", end=" ")
        except Exception as e:
            if verbose:
                print(f"err({type(e).__name__}) -> retry", end=" ")

        if max_tries is not None and tries >= max_tries:
            return None

        time.sleep(wait)
        wait = min(max_sleep, wait * backoff)

def filter_coin(ticker, verbose=True):
    # 30일치 데이터가 '정상적으로' 존재하는지부터 재시도로 확보
    df30 = get_ohlcv_retry(ticker, count=LISTING_DAYS, interval="day", verbose=verbose)
    if df30 is None or len(df30) < LISTING_DAYS:
        if verbose:
            print("skip(new)")
        return False, None

    v = df30["value"]
    med = v.median()

    if v.max() / (med + 1e-9) > PUMP_RATIO:
        if verbose:
            print("skip(pump)")
        return False, None

    if v.min() < MIN_TURNOVER:
        if verbose:
            print("skip(thin)")
        return False, None

    if df30["close"].pct_change().abs().max() > MAX_DAILY_RET:
        if verbose:
            print("skip(volatile)")
        return False, None

    return True, df30

def top_liquid_coins(score_days=10, verbose=True):
    tickers = pyupbit.get_tickers(fiat="KRW")

    EXCLUDE = {"KRW-USDT", "KRW-USDC", "KRW-DAI", "KRW-TUSD", "KRW-USDP"}
    tickers = [t for t in tickers if t not in EXCLUDE]

    scores, total = [], len(tickers)

    for i, t in enumerate(tickers, 1):
        if verbose:
            print(f"[{i}/{total}] {t} ...", end=" ")

        # 스코어용 df(최근 score_days)도 retry로 확보 (여기가 기존 크래시 포인트)
        df_score = get_ohlcv_retry(t, count=score_days, interval="day", verbose=verbose)
        if df_score is None:
            if verbose:
                print("skip(no_score)")
            continue

        ok, df30 = filter_coin(t, verbose=verbose)
        if not ok:
            continue

        score = df_score["value"].median()
        scores.append((t, score))

        if verbose:
            print(int(score))

    return sorted(scores, key=lambda x: x[1], reverse=True)

def make_liquidity_row():
    return lambda ts, t, s: (ts, t, float(s), LISTING_DAYS, PUMP_RATIO, MIN_TURNOVER, MAX_DAILY_RET)
