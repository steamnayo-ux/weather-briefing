"""MCP 서버 진입점. 도구 등록만 담당하고 로직은 services에 둔다."""
from mcp.server.fastmcp import FastMCP

from weather_mcp.services import ai_briefing, air, kakao_briefing, location, weather

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