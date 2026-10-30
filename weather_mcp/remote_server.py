"""원격 MCP 서버 진입점. 읽기 전용 날씨 도구 6개만 공개한다.

server.py(로컬용, 8개 전체)는 건드리지 않는다.
카카오 발송(send_briefing_to_kakao)과 Gemini 호출(get_briefing)은
일부러 가져오지 않는다. 원격에서는 호출할 수 없어야 한다.
"""
import os

from mcp.server.fastmcp import FastMCP

# 함수 정의와 docstring은 server.py 한 곳에만 둔다 (복사 금지)
from weather_mcp.server import (
    get_air_quality,
    get_hourly_forecast,
    get_uv_index,
    get_weather,
    recommend_activity,
    search_location,
)

# 허용 목록: 여기에 적은 도구만 원격에 열린다
READ_ONLY_TOOLS = [
    search_location,
    get_weather,
    get_hourly_forecast,
    get_uv_index,
    recommend_activity,
    get_air_quality,
]

# host/port는 호스팅 환경(R3)에서 환경변수로 받는다. 기본값은 로컬 테스트용
remote_mcp = FastMCP(
    "weather-briefing-remote",
    host=os.environ.get("HOST", "127.0.0.1"),
    port=int(os.environ.get("PORT", "8000")),
    stateless_http=True,  # 서버가 꺼졌다 켜져도 문제없게 요청마다 독립 처리
)

for _fn in READ_ONLY_TOOLS:
    remote_mcp.tool()(_fn)  # server.py의 함수를 그대로 등록


# 원격 서버가 시작할 때 반드시 있어야 하는 환경변수
REQUIRED_ENV = ["REMOTE_API_KEY", "DATA_GO_KR_API_KEY"]


def create_app():
    """키 인증이 붙은 ASGI 앱. 필수 환경변수가 빠지면 여기서 예외가 나 서버가 뜨지 않는다."""
    from weather_mcp.env_check import require_env
    from weather_mcp.remote_auth import ApiKeyMiddleware, load_remote_key

    require_env(REQUIRED_ENV)  # 가장 먼저 점검: 빠진 이름을 한 번에 알려 준다
    return ApiKeyMiddleware(remote_mcp.streamable_http_app(), load_remote_key())


if __name__ == "__main__":
    from pathlib import Path

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))  # weather_mcp/.env
    import logging
    # httpx가 요청 URL(쿼리의 serviceKey 포함)을 INFO로 찍지 않게 한다
    logging.getLogger("httpx").setLevel(logging.WARNING)
    uvicorn.run(
        create_app(),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        access_log=False,  # 접속 로그에 ?key=...가 찍히지 않게
    )