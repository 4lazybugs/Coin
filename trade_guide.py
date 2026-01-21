from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Callable, List, ClassVar
import utils

###### data containers ######################################
@dataclass
class Cooltime:
    scan_every: timedelta = timedelta(hours=25)
    next_scan_at: datetime = field(default_factory=datetime.now)
    news_every: timedelta = timedelta(hours=12)
    next_news_at: datetime = field(default_factory=datetime.now)
    cached_news: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Util_Funcs:
    get_fear_greed_index: Callable[..., Any]
    get_recent_trades: Callable[..., Any]
    generate_reflection: Callable[..., str]
    fetch_rss_news: Callable[..., Any]
    get_vid_script: Callable[..., str]
    get_price: Callable[..., Dict[str, Any]] 

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
    }

    @classmethod
    def set_params(cls, *, video_id: str, coin_name: str, rss: Optional[Dict[str, Any]] = None, **overrides) -> "Util_Funcs":
        cfg = {**cls._DEFAULTS, **overrides}
        uf = cls(**cfg, video_id=video_id, coin_name=coin_name)

        if rss:
            for k, v in rss.items():
                setattr(uf, f"rss_{k}", v)

        return uf
    
    def run_all(self):
        informs: Dict[str, Any] = {}
        informs["fear_greed_index"] = self.get_fear_greed_index(limit=1, date_format="kr")
        
        rt_df = self.get_recent_trades()
        informs["recent_trades"] = utils.trades_df_to_records(rt_df, tail=30)
        
        informs["reflection"] = self.generate_reflection(
            rt_df,
            {"fear_greed_index": informs["fear_greed_index"]}
        )
        informs["youtube_transcript"] = self.get_vid_script(self.video_id)
        informs["coin_price"] = self.get_price(self.coin_name)

        informs["news"] = self.fetch_rss_news(
            self.rss_feed_url,
            self.rss_limit,
            self.rss_summary_len,
            self.rss_content_len,
        )

        return informs


#############################################################
if __name__ == "__main__":

    util_funcs = Util_Funcs.set_params(
        coin_name="KRW-BTC",
        video_id="-UJHObtnp5A",
        rss={"limit": 10, "summary_len": 300, "content_len": 600},
    )

    informs = util_funcs.run_all()
    print(informs)
