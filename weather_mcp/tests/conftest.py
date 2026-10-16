"""테스트 공통 설정. 모든 테스트 전후로 air 캐시를 비워 테스트끼리 영향을 막는다."""
import pytest

from weather_mcp.services import air


@pytest.fixture(autouse=True)
def clear_air_caches():
    """autouse=True라서 모든 테스트에 자동 적용된다."""
    air.STATION_CACHE.clear()
    air.REALTIME_CACHE.clear()
    yield  # 여기서 테스트가 실행된다
    air.STATION_CACHE.clear()
    air.REALTIME_CACHE.clear()