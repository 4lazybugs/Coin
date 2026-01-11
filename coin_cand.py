import pyupbit

##############################################
## params explanation: liquidity_filter() ####
###############################################
LISTING_DAYS = 30 # 최근 30일치 일봉 데이터가 정상적으로 존재하는 코인만 통과
PUMP_RATIO = 8 # 어떤 하루가 평소보다 8배 이상 거래되는 코인 기각!
MIN_TURNOVER = 5_000_000_000 # 하루 거래대금 50억 미만 기각!: 특정 날만 터지는 코인 제외
MAX_DAILY_RET = 0.3 # 하루 변동폭 30% 초과 코인 비정상 코인 기각!: Too Risky

###### main functions ####################################################
def filter(df, ticker, verbose=True):
    if df is None or df.empty:
        if verbose: print("skip(no data)")
        return False

    df30 = df if len(df) >= LISTING_DAYS else pyupbit.get_ohlcv(
        ticker, count=LISTING_DAYS, interval="day"
    )
    if df30 is None or len(df30) < LISTING_DAYS:
        if verbose: print("skip(new)")
        return False

    v = df30["value"]
    med = v.median()

    if v.max() / (med + 1e-9) > PUMP_RATIO:
        if verbose: print("skip(pump)")
        return False
    if v.min() < MIN_TURNOVER:
        if verbose: print("skip(thin)")
        return False
    if df30["close"].pct_change().abs().max() > MAX_DAILY_RET:
        if verbose: print("skip(volatile)")
        return False

    return True

def top_liquid_coins(score_days=10, verbose=True):
    tickers = pyupbit.get_tickers(fiat="KRW")
    scores, total = [], len(tickers)

    for i, t in enumerate(tickers, 1):
        if verbose:
            print(f"[{i}/{total}] {t} ...", end=" ")

        df = pyupbit.get_ohlcv(t, count=score_days, interval="day")
        if not filter(df, t, verbose):
            continue

        score = df["value"].median()
        scores.append((t, score))

        if verbose:
            print(int(score))

    return sorted(scores, key=lambda x: x[1], reverse=True)

def make_liquidity_row():
    return lambda ts, t, s: (ts, t, float(s), LISTING_DAYS, PUMP_RATIO, MIN_TURNOVER, MAX_DAILY_RET)

