"""air.py 캐시 동작 테스트. API 호출 함수를 가짜로 바꿔서 호출 횟수를 센다."""
import itertools

import pytest

from weather_mcp.services import air

# 가짜 응답 데이터 (필드 이름은 실제 에어코리아 응답과 같게 맞춘다)
STATIONS = [{"stationName": "강남구", "tm": "0.1"}]
ROW_OK = {
    "dataTime": "2026-10-16 09:00",
    "pm10Value": "19", "pm10Grade1h": "1",
    "pm25Value": "4", "pm25Grade1h": "1",
}
ROW_EMPTY = {"dataTime": "2026-10-16 09:00", "pm10Value": "-", "pm25Value": "-"}
LAT, LON = 37.5172, 127.0473  # 서울 강남 근처 (한국 범위 안)


@pytest.fixture
def api(monkeypatch):
    """_call_airkorea를 가짜로 교체한다.

    state["realtime"]에 넣은 응답을 호출 순서대로 하나씩 꺼내 쓰고,
    Exception이면 그 예외를 발생시킨다. state["calls"]에는 호출된 URL이 쌓인다.
    """
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    state = {"calls": [], "realtime": []}

    def fake_call(url, params):
        state["calls"].append(url)
        if url == air.NEARBY_URL:
            return STATIONS
        result = state["realtime"].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(air, "_call_airkorea", fake_call)

    # 호출할 때마다 다른 시각이 나오게 해서, 캐시된 시각이 유지되는지 구분한다
    counter = itertools.count(1)
    monkeypatch.setattr(air, "_now_iso", lambda: f"t{next(counter)}")
    return state


def test_same_request_hits_api_only_once(api):
    api["realtime"] = [[ROW_OK]]
    first = air.get_air_quality(LAT, LON)
    second = air.get_air_quality(LAT, LON)

    assert first["pm10"] == 19 and second["pm10"] == 19
    assert api["calls"].count(air.NEARBY_URL) == 1    # 측정소 목록: 1번만
    assert api["calls"].count(air.REALTIME_URL) == 1  # 측정값: 1번만
    # 캐시된 결과는 '처음 API에서 받은 시각'을 그대로 보여준다
    assert second["collected_at"] == first["collected_at"]


def test_api_error_is_not_cached(api):
    api["realtime"] = [air.AirKoreaError("실패"), [ROW_OK]]
    first = air.get_air_quality(LAT, LON)
    second = air.get_air_quality(LAT, LON)

    assert "error" in first          # 첫 호출은 실패
    assert second["pm10"] == 19      # 실패가 저장되지 않아 다시 호출했다
    assert api["calls"].count(air.REALTIME_URL) == 2


def test_empty_values_are_not_cached(api):
    api["realtime"] = [[ROW_EMPTY], [ROW_OK]]
    first = air.get_air_quality(LAT, LON)
    second = air.get_air_quality(LAT, LON)

    assert "error" in first          # 미세먼지 값이 없어서 오류
    assert second["pm10"] == 19      # 빈 값이 저장되지 않아 다시 호출했다
    assert api["calls"].count(air.NEARBY_URL) == 1  # 측정소 목록은 재사용