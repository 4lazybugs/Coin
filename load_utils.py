from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Callable, List
import utils
import time
import traceback
import math

###### data containers ######################################
@dataclass
class Cooltime:
    scan_every: timedelta = timedelta(hours=25)
    next_scan_at: datetime = field(default_factory=datetime.now)
    news_every: timedelta = timedelta(hours=12)
    next_news_at: datetime = field(default_factory=datetime.now)
    cached_news: List[Dict[str, Any]] = field(default_factory=list)


def _sanitize_json(x: Any) -> Any:
    """NaN/inf/DataFrame 등 json.dumps에서 문제나는 것들 방지"""
    try:
        import pandas as pd
        if isinstance(x, pd.DataFrame):
            return x.where(pd.notnull(x), None).to_dict(orient="records")
    except Exception:
        pass

    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return x

    if isinstance(x, dict):
        return {k: _sanitize_json(v) for k, v in x.items()}

    if isinstance(x, list):
        return [_sanitize_json(v) for v in x]

    return x


@dataclass
class Util_Funcs:
    get_fear_greed_index: Callable[..., Any]
    get_recent_trades: Callable[..., Any]
    generate_reflection: Callable[..., str]
    fetch_rss_news: Callable[..., Any]
    get_vid_script: Callable[..., str]
    get_price: Callable[..., Any]   # Dict[str, Any] 고정하면 오히려 불편해서 Any로

    # ✅ 추가: trades_df_to_records를 주입/기본값으로 사용
    trades_df_to_records: Callable[..., Any] = getattr(utils, "trades_df_to_records", None)

    # RSS 기본 설정(필요시 init_funcs에서 override 가능)
    rss_feed_url: str = "https://news.google.com/rss/search?q=bitcoin"
    rss_limit: int = 5
    rss_summary_len: int = 200
    rss_content_len: int = 400

    video_id: str = ""
    coin_name: str = ""

    _DEFAULTS = {
        "get_fear_greed_index": utils.get_fear_greed_index,
        "get_recent_trades": utils.get_recent_trades,
        "generate_reflection": utils.generate_reflection,
        "fetch_rss_news": utils.fetch_rss_news,
        "get_vid_script": utils.get_vid_script,
        "get_price": utils.get_price,
        "trades_df_to_records": getattr(utils, "trades_df_to_records", None),
    }

    @classmethod
    def set_params(
        cls, *,
        video_id: str,
        coin_name: str,
        rss: Optional[Dict[str, Any]] = None,
        **overrides
    ) -> "Util_Funcs":
        cfg = {**cls._DEFAULTS, **overrides}
        uf = cls(**cfg, video_id=video_id, coin_name=coin_name)

        if rss:
            for k, v in rss.items():
                setattr(uf, f"rss_{k}", v)

        return uf

    def run_all(
        self,
        *,
        pre_fear_greed_index=None,
        pre_recent_trades_df=None,
        pre_reflection=None,
        pre_news=None,
        cooltime=None,
    ) -> dict:
        informs = {}

        t0 = time.perf_counter()
        def lap(name: str):
            nonlocal t0
            t1 = time.perf_counter()
            print(f"[TIMING] {name}: {(t1 - t0):.3f}s")
            t0 = t1

        try:
            # 1) FNG
            try:
                informs["fear_greed_index"] = (
                    pre_fear_greed_index
                    if pre_fear_greed_index is not None
                    else self.get_fear_greed_index(limit=1, date_format="kr")
                )
            except Exception as e:
                print("[WARN] fear_greed_index failed:", repr(e))
                print(traceback.format_exc())
                informs["fear_greed_index"] = None
            lap("fear_greed_index")

            # 2) recent trades
            try:
                df = pre_recent_trades_df if pre_recent_trades_df is not None else self.get_recent_trades(minutes=20)
            except Exception as e:
                print("[WARN] get_recent_trades failed:", repr(e))
                print(traceback.format_exc())
                df = None
            lap("get_recent_trades")
            print("[DEBUG] trades rows:", 0 if df is None else len(df))

            # ✅ DF 넣지 말고 records로
            try:
                if self.trades_df_to_records is not None:
                    informs["recent_trades"] = self.trades_df_to_records(df, tail=30)
                else:
                    informs["recent_trades"] = []
            except Exception as e:
                print("[WARN] trades_df_to_records failed:", repr(e))
                print(traceback.format_exc())
                informs["recent_trades"] = []
            lap("trades_df_to_records")

            # 3) reflection
            if pre_reflection is not None:
                informs["reflection"] = pre_reflection
                lap("reflection (pre_reflection)")
            else:
                market_data = {"fear_greed_index": informs["fear_greed_index"]}

                # ✅ trades가 비어도 reflection 생성 (rows=0이면 0% 성과 기반 코멘트가 나오게 됨)
                try:
                    informs["reflection"] = self.generate_reflection(df, market_data)
                except Exception as e:
                    print("[WARN] generate_reflection failed:", repr(e))
                    print(traceback.format_exc())
                    informs["reflection"] = ""   # 실패해도 계속 진행

                lap("generate_reflection")
                print("[DEBUG] reflection chars:", len(informs["reflection"] or ""))


            # 4) youtube transcript
            try:
                t_vid0 = time.perf_counter()
                informs["youtube_transcript"] = self.get_vid_script(self.video_id)
                print(f"[TIMING] get_vid_script inner: {(time.perf_counter()-t_vid0):.3f}s")
            except Exception as e:
                print("[WARN] get_vid_script failed:", repr(e))
                print(traceback.format_exc())
                informs["youtube_transcript"] = ""
            lap("get_vid_script")
            print("[DEBUG] transcript chars:", len(informs["youtube_transcript"] or ""))

            # 5) coin price
            try:
                t_px0 = time.perf_counter()
                informs["coin_price"] = self.get_price(self.coin_name)
                print(f"[TIMING] get_price inner: {(time.perf_counter()-t_px0):.3f}s")
            except Exception as e:
                print("[WARN] get_price failed:", repr(e))
                print(traceback.format_exc())
                informs["coin_price"] = None
            lap("get_price")

            # 6) news
            if pre_news is not None:
                informs["news"] = pre_news
                lap("news (skipped)")
            else:
                try:
                    t_news0 = time.perf_counter()
                    if cooltime is not None:
                        now = datetime.now()
                        if (now >= cooltime.next_news_at) or (not cooltime.cached_news):
                            cooltime.cached_news = self.fetch_rss_news(
                                self.rss_feed_url,
                                self.rss_limit,
                                self.rss_summary_len,
                                self.rss_content_len,
                            )
                            cooltime.next_news_at = now + cooltime.news_every
                        informs["news"] = cooltime.cached_news
                    else:
                        informs["news"] = self.fetch_rss_news(
                            self.rss_feed_url,
                            self.rss_limit,
                            self.rss_summary_len,
                            self.rss_content_len,
                        )
                    print(f"[TIMING] fetch_rss_news inner: {(time.perf_counter()-t_news0):.3f}s")
                except Exception as e:
                    print("[WARN] fetch_rss_news failed:", repr(e))
                    print(traceback.format_exc())
                    informs["news"] = []
                lap("fetch_rss_news")
                print("[DEBUG] news items:", len(informs["news"] or []))

            return informs

        except Exception as e:
            print("[ERROR] run_all failed (unexpected):", repr(e))
            print(traceback.format_exc())
            raise


#############################################################
if __name__ == "__main__":
    API_KEY = "local-token"
    BASE_URL = "http://127.0.0.1:9000/v1"

    # util_funcs = Util_Funcs.set_params(
    #     video_id="-UJHObtnp5A",
    #     rss={
    #         "feed_url": "https://www.cryptobreaking.com/feed/",
    #         "limit": 10,
    #         "summary_len": 300,
    #         "content_len": 600,
    #     },
    #     get_vid_script=lambda video_id: utils.get_vid_script(BASE_URL, API_KEY, video_id),
    # )

    #util_funcs = Util_Funcs()

    cooltime = Cooltime(
        news_every=timedelta(hours=12),
        next_news_at=datetime.now(),
    )

    informs = {}

    # cool time 계산하는 함수:fng 아니면 continue
    fng = utils.get_fear_greed_index()
    informs["fear_greed_index"] = fng

    price = utils.get_price(coin_name="KRW-BTC")
    informs["coin_price"] = price

    news =utils.fetch_rss_news(feed_url="https://www.cryptobreaking.com/feed/")
    informs["news"] = news

    print(json.dumps(_sanitize_json(informs), ensure_ascii=False, indent=2))


    

    #informs = util_funcs.run_all(cooltime=cooltime)

    # ✅ 출력 전에 sanitize (NaN/inf/DF 방지)
    #print(json.dumps(_sanitize_json(informs), ensure_ascii=False, indent=2))
