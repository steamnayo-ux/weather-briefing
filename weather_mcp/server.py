"""MCP 서버 진입점. 도구 등록만 담당하고 로직은 services에 둔다."""
from mcp.server.fastmcp import FastMCP

from weather_mcp.services import activity, ai_briefing, air, kakao_briefing, location, uv, weather

mcp = FastMCP("weather-briefing")


@mcp.tool()
def search_location(query: str) -> list[dict]:
    """지역 이름으로 위치를 검색한다. 예: '강남'"""
    return location.search_location(query)


@mcp.tool()
def get_weather(location_name: str) -> dict:
    """지역의 현재 날씨를 조회한다. 예: '서울 강남구'"""
    return weather.get_weather(location_name)


@mcp.tool()
def get_hourly_forecast(
    location_name: str, date: str = "오늘", start_hour: int = 0, end_hour: int = 23
) -> dict:
    """지역의 시간대별 예보(기온, 강수확률, 강수 형태, 하늘 상태, 습도, 풍속)를 조회한다.
    date는 '오늘', '내일', '모레' 또는 'YYYY-MM-DD' (오늘~모레까지만 가능).
    start_hour~end_hour는 0~23시이며 양쪽 시각을 포함한다.
    summary에 최대 강수확률과 비·눈이 오는 시각 목록이 들어 있다.
    wind_chill_c는 겨울 바람 체감온도(℃)이며, 기온 10℃ 이하이고 풍속 1.3m/s 이상일 때만 값이 있고 아니면 null이다.
    예: 퇴근길 비 여부는 start_hour=17, end_hour=19, 내일 오전은 date='내일', start_hour=6, end_hour=12"""
    return weather.get_hourly_forecast(location_name, date, start_hour, end_hour)


@mcp.tool()
def get_uv_index(
    location_name: str, date: str = "오늘", start_hour: int = 0, end_hour: int = 23
) -> dict:
    """지역의 자외선지수 예보를 조회한다. 3시간 간격 예보라서 구간 안의 최대값을 돌려준다.
    date는 '오늘', '내일', '모레', '글피' 또는 'YYYY-MM-DD'이고, start_hour~end_hour는 0~23시이다.
    uv_max(지수), uv_level(낮음/보통/높음/매우높음/위험), uv_max_at(최대 시각)이 들어 있다.
    지수 범위: 낮음 0~2, 보통 3~5, 높음 6~7, 매우높음 8~10, 위험 11 이상.
    값을 구하지 못하면 error가 들어 있으니 지수를 추측하지 말고 확인하지 못했다고 알린다.
    예: 오늘 낮 자외선은 start_hour=10, end_hour=15"""
    return uv.lookup_uv_index(location_name, date, start_hour, end_hour)


@mcp.tool()
def recommend_activity(
    location_name: str, activity_name: str, date: str = "오늘",
    start_hour: int | None = None, end_hour: int | None = None
) -> dict:
    """활동을 해도 좋은지 시간대별 예보와 미세먼지·자외선 규칙으로 판단한다.
    activity_name은 '러닝', '산책', '외출'(퇴근길·우산), '빨래' 중 하나다.
    date는 '오늘', '내일', '모레' 또는 'YYYY-MM-DD'이고, start_hour~end_hour(0~23시)를 생략하면 활동별 기본 시간대를 쓴다.
    verdict(좋음/주의/비추천/판단불가)와 reasons는 코드 규칙의 결과이므로 바꾸지 말고 그대로 설명하고,
    items(준비물)와 notes(확인하지 못한 항목)도 함께 알려 준다. 숫자는 details에 있다.
    예: '퇴근길 비 와?' -> activity_name='외출', start_hour=17, end_hour=19"""
    return activity.recommend_activity(location_name, activity_name, date, start_hour, end_hour)


@mcp.tool()
def get_air_quality(location_name: str) -> dict:
    """지역의 현재 미세먼지(PM10, PM2.5) 정보를 조회한다. 예: '서울 강남구'"""
    return air.get_air_quality_by_name(location_name)


@mcp.tool()
def get_briefing(location_name: str) -> dict:
    """지역의 날씨와 대기질을 AI가 정리한 한국어 브리핑을 반환한다. 예: '서울 강남구'"""
    return ai_briefing.generate_briefing(location_name)


@mcp.tool()
def send_briefing_to_kakao(location_name: str) -> dict:
    """지역의 날씨·대기질 브리핑을 만들어 카카오톡 '나와의 채팅'으로 발송한다.
    호출하면 실제로 메시지가 전송된다. 예: '서울 강남구'"""
    return kakao_briefing.send_briefing_to_kakao(location_name)


if __name__ == "__main__":
    mcp.run()  # 기본 stdio 방식