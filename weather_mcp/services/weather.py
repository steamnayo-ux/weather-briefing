"""날씨 조회 서비스 (1단계: mock 데이터)."""
from datetime import datetime, timezone, timedelta

from weather_mcp.services.location import get_location

KST = timezone(timedelta(hours=9))


def get_weather(location_name: str) -> dict:
    """지역 이름으로 날씨를 반환한다.

    출처(source)와 수집 시각(collected_at)을 항상 함께 담는다.
    """
    loc = get_location(location_name)
    if loc is None:
        # 없는 지역은 잘못된 값을 만들지 않고 명확히 오류를 알린다
        return {"error": f"알 수 없는 지역: {location_name}"}

    return {
        "location": loc["name"],
        "source": "mock",  # 실제 API로 바꾸면 'kma'
        "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
        "temperature_c": 18.5,
        "sky": "맑음",
        "precipitation_probability": 10,
    }