"""테스트 공통 설정.

1) 모든 테스트 전후로 air·location 캐시를 비워 테스트끼리 영향을 막는다.
2) 테스트 중 실제 HTTP GET 호출을 막는다. 가짜를 주입하지 않은 테스트가
   몰래 카카오·공공 API를 부르면 느려지거나 키 때문에 이상하게 깨지는 대신,
   이유가 보이는 오류로 바로 실패한다.
   (HTTP를 쓰는 테스트는 monkeypatch로 httpx.get을 직접 가짜로 바꾸면 된다.)
"""
import httpx
import pytest

from weather_mcp.services import air, location


@pytest.fixture(autouse=True)
def clear_caches():
    """autouse=True라서 모든 테스트에 자동 적용된다."""
    air.STATION_CACHE.clear()
    air.REALTIME_CACHE.clear()
    location.DOCS_CACHE.clear()
    yield  # 여기서 테스트가 실행된다
    air.STATION_CACHE.clear()
    air.REALTIME_CACHE.clear()
    location.DOCS_CACHE.clear()


@pytest.fixture(autouse=True)
def block_real_http(monkeypatch):
    """테스트에서 실제 네트워크(GET) 호출을 막는다."""

    def blocked(*args, **kwargs):
        raise AssertionError(
            "테스트에서 실제 HTTP 호출이 일어났습니다. "
            "location._call_kakao 또는 httpx.get을 가짜로 바꾸세요."
        )

    monkeypatch.setattr(httpx, "get", blocked)
