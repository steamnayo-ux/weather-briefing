"""MCP 서버 진입점. 도구 등록만 담당하고 로직은 services에 둔다."""
from mcp.server.fastmcp import FastMCP

from weather_mcp.services import location, weather

mcp = FastMCP("weather-briefing")


@mcp.tool()
def search_location(query: str) -> list[dict]:
    """지역 이름으로 위치를 검색한다. 예: '강남'"""
    return location.search_location(query)


@mcp.tool()
def get_weather(location_name: str) -> dict:
    """지역의 현재 날씨를 조회한다. 예: '서울 강남구'"""
    return weather.get_weather(location_name)


if __name__ == "__main__":
    mcp.run()  # 기본 stdio 방식