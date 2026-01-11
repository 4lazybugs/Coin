import requests

FNG_API_BASE = "https://api.alternative.me"
FNG_ENDPOINT = "/fng/"

def get_fear_greed_index(
    FNG_API_BASE=FNG_API_BASE,
    FNG_ENDPOINT=FNG_ENDPOINT,
    limit: int = 1,
    date_format: str = "kr",
):
    """
    Fetch Fear & Greed Index from Alternative.me.
    Attribution requirement: show source near display of data.
    """
    url = f"{FNG_API_BASE}{FNG_ENDPOINT}"
    params = {"limit": limit, "date_format": date_format}

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

        result = {
            "name": payload.get("name", "Fear and Greed Index"),
            "value": latest.get("value"),
            "value_classification": latest.get("value_classification"),
            "timestamp": latest.get("timestamp"),
            "time_until_update": latest.get("time_until_update", None),
            "source": "Alternative.me (https://alternative.me) / API: https://api.alternative.me/fng/",
        }

        # ===== 기존 ai_trading()에 있던 출력 로직 이동 =====
        print(
            f"[FNG] value={result['value']} ({result['value_classification']}), "
            f"ts={result['timestamp']} (Source: {result['source']})"
        )

        return result

    except Exception as e:
        error_result = {
            "name": "Fear and Greed Index",
            "value": None,
            "value_classification": None,
            "timestamp": None,
            "time_until_update": None,
            "source": "Alternative.me (https://alternative.me) / API: https://api.alternative.me/fng/",
            "error": str(e),
        }

        # ===== 에러 출력도 함수 내부에서 처리 =====
        print(f"[FNG] (Source: {error_result['source']}) Fetch failed: {error_result['error']}")

        return error_result
