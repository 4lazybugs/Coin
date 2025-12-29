import requests
FNG_API_BASE = "https://api.alternative.me"
FNG_ENDPOINT = "/fng/"

def get_fear_greed_index(FNG_API_BASE=FNG_API_BASE, FNG_ENDPOINT=FNG_ENDPOINT, limit: int = 1, date_format: str = "kr"):
    """
    Fetch Fear & Greed Index from Alternative.me.
    Attribution requirement: show source near display of data.
    """
    url = f"{FNG_API_BASE}{FNG_ENDPOINT}"
    params = {"limit": limit, "date_format": date_format}  # date_format: 'kr' -> YYYY/MM/DD
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        payload = r.json()

        if payload.get("metadata", {}).get("error") is not None:
            raise RuntimeError(f"Alternative.me API error: {payload['metadata']['error']}")

        data = payload.get("data", [])
        if not data:
            raise RuntimeError("Alternative.me API returned empty data")

        latest = data[0]
        # 최신값(limit=1)일 때만 time_until_update가 있을 수 있음
        return {
            "name": payload.get("name", "Fear and Greed Index"),
            "value": latest.get("value"),
            "value_classification": latest.get("value_classification"),
            "timestamp": latest.get("timestamp"),
            "time_until_update": latest.get("time_until_update", None),
            "source": "Alternative.me (https://alternative.me) / API: https://api.alternative.me/fng/"
        }
    except Exception as e:
        # 실전 운영에서는 여기서 None 반환 후 프롬프트에서 'unknown' 처리하는 편이 안전합니다.
        return {
            "name": "Fear and Greed Index",
            "value": None,
            "value_classification": None,
            "timestamp": None,
            "time_until_update": None,
            "source": "Alternative.me (https://alternative.me) / API: https://api.alternative.me/fng/",
            "error": str(e),
        }