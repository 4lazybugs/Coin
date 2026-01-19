from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Callable, List
import utils

###### data containers ######################################
@dataclass
class Informs:
    coin_name: str
    reflection: Optional[str]
    youtube_transcript: Optional[str]
    model_input: Dict[str, Any]


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

    # RSS 기본 설정(필요시 make_informs에서 override 가능)
    rss_feed_url: str = "https://news.google.com/rss/search?q=bitcoin"
    rss_limit: int = 5
    rss_summary_len: int = 200
    rss_content_len: int = 400

    _DEFAULTS = {
        "get_fear_greed_index": utils.get_fear_greed_index,
        "get_recent_trades": utils.get_recent_trades,
        "generate_reflection": utils.generate_reflection,
        "fetch_rss_news": utils.fetch_rss_news,
        "get_vid_script": utils.get_vid_script,
    }

    @staticmethod
    def make(**overrides) -> "Util_Funcs":
        cfg = {**Util_Funcs._DEFAULTS, **overrides}
        return Util_Funcs(**cfg)

    @classmethod
    def make_informs(
        cls,
        *,
        key: str,
        coin_name: str,
        video_id: str,
        snapshot: Dict[str, Any],
        cooltime: "Cooltime",
        rss: Optional[Dict[str, Any]] = None,   # ✅ RSS 설정은 여기로
        **overrides,
    ) -> "Informs":
        uf = cls.make(**overrides)

        if rss:
            # rss dict에 들어온 키만 uf에 반영
            for k, v in rss.items():
                setattr(uf, f"rss_{k}", v)

        return build_context(
            key,
            Util_Funcs=uf,
            cooltime=cooltime,
            coin_name=coin_name,
            video_id=video_id,
            snapshot=snapshot,
        )
################################################################


def _return_informs(uf: Util_Funcs, cooltime: Cooltime, video_id: str):
    fear_greed_index = uf.get_fear_greed_index(limit=1, date_format="kr")
    recent_trades = uf.get_recent_trades()

    reflection = uf.generate_reflection(
        recent_trades,
        {"fear_greed_index": fear_greed_index}
    )

    youtube_transcript = uf.get_vid_script(video_id)

    # raw 시그니처로 호출 (설정은 uf에 저장된 값 사용)
    cached_news = uf.fetch_rss_news(
        uf.rss_feed_url,
        uf.rss_limit,
        uf.rss_summary_len,
        uf.rss_content_len,
    )

    return fear_greed_index, reflection, youtube_transcript, cached_news


################## Strategy implementations ###########################
def btc_v1_build(
    *, coin_name: str, Util_Funcs: Util_Funcs, cooltime: Cooltime,
    video_id: str, snapshot: Dict[str, Any],
) -> Informs:
    fear_greed_index, reflection, youtube_transcript, cached_news = _return_informs(Util_Funcs, cooltime, video_id)

    model_input = {
        "price": snapshot["price"],
        "rsi": snapshot["rsi"],
        "macd": snapshot["macd"],
        "fear_greed_index": fear_greed_index,
        "news": cached_news,
    }

    return Informs(
        coin_name=coin_name,
        reflection=reflection,
        youtube_transcript=youtube_transcript,
        model_input=model_input,
    )


# ====== Registry: key -> function ======
CONTEXT_REGISTRY: Dict[str, Callable[..., Informs]] = {
    "btc_v1": btc_v1_build,
}


# ====== Dispatcher ======
def build_context(
    key: str, *, Util_Funcs: Util_Funcs, cooltime: Cooltime,
    coin_name: str, video_id: str, snapshot: Dict[str, Any],
) -> Informs:
    try:
        build_fn = CONTEXT_REGISTRY[key]
    except KeyError as e:
        raise ValueError(f"Unknown context key: {key}") from e

    return build_fn(
        coin_name=coin_name,
        Util_Funcs=Util_Funcs,
        cooltime=cooltime,
        video_id=video_id,
        snapshot=snapshot,
    )


#############################################################
if __name__ == "__main__":
    snapshot = {
        "price": 68400,
        "rsi": 61.2,
        "macd": "bullish",
        # v1에서는 아래 2개는 현재 미사용(향후 v2에서 쓰면 됨)
        "ohlcv_tail": [],
        "indicators": {"rsi": 61.2, "macd": "bullish"},
    }

    informs = Util_Funcs.make_informs(
        key="btc_v1",
        coin_name="BTC",
        video_id="-UJHObtnp5A",
        snapshot=snapshot,
        cooltime=Cooltime(),
        rss={"limit": 10, "summary_len": 300, "content_len": 600},
    )

    print("=== Informs ===")
    print("coin_name:", informs.coin_name)
    print("reflection:", informs.reflection)
    print("youtube_transcript:", (informs.youtube_transcript[:400] + "...") if informs.youtube_transcript else None)
    print("model_input:", json.dumps(informs.model_input, ensure_ascii=False, indent=2))
