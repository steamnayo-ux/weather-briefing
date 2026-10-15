"""air.py 테스트. 실제 API 호출 없이 동작한다."""
import httpx
import pytest

from weather_mcp.services import air


def test_to_float_and_int():
    assert air._to_float("18") == 18.0
    assert air._to_float("-") is None   # 점검/결측은 "-"로 온다
    assert air._to_float(None) is None
    assert air._to_int("18") == 18
    assert air._to_int("-") is None


def test_grade_text():
    assert air._grade_text("1") == "좋음"
    assert air._grade_text("4") == "매우나쁨"
    assert air._grade_text(None) is None
    assert air._grade_text("9") is None  # 알 수 없는 코드


def test_has_pm_data():
    assert air._has_pm_data({"pm10Value": "18", "pm25Value": "-"}) is True
    assert air._has_pm_data({"pm10Value": "-", "pm25Value": None}) is False


def test_build_result():
    station = {"stationName": "강남구", "tm": 0.1}
    row = {
        "dataTime": "2026-10-15 15:00",
        "pm10Value": "18", "pm10Grade1h": "1",
        "pm25Value": "7", "pm25Grade1h": "1",
    }
    assert air._build_result(station, row) == {
        "station_name": "강남구", "station_distance_km": 0.1,
        "data_time": "2026-10-15 15:00",
        "pm10": 18, "pm10_grade": "좋음", "pm25": 7, "pm25_grade": "좋음",
    }


def test_out_of_korea_returns_error():
    # 도쿄 좌표는 한국 범위 밖 -> API 호출 전에 오류
    assert "error" in air.get_air_quality(35.68, 139.69)


def _fake_call(nearby, rows_by_station):
    """_call_airkorea 대신 쓰는 가짜 함수 (URL에 따라 준비된 응답을 돌려준다)."""
    def fake(url, params):
        if url == air.NEARBY_URL:
            return nearby
        return rows_by_station[params["stationName"]]
    return fake


def test_falls_back_to_next_station_when_no_data(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "dummy")
    nearby = [{"stationName": "A", "tm": 0.1}, {"stationName": "B", "tm": 2.6}]
    rows = {
        "A": [{"dataTime": "t", "pm10Value": "-", "pm25Value": "-"}],  # 점검 중
        "B": [{"dataTime": "t", "pm10Value": "30", "pm10Grade1h": "2",
               "pm25Value": "10", "pm25Grade1h": "1"}],
    }
    monkeypatch.setattr(air, "_call_airkorea", _fake_call(nearby, rows))
    result = air.get_air_quality(37.5172, 127.0473)
    assert result["station_name"] == "B"
    assert result["pm10"] == 30
    assert len(result["warnings"]) == 1  # A에 값이 없었다는 안내


def test_error_when_all_stations_have_no_data(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "dummy")
    nearby = [{"stationName": "A", "tm": 0.1}]
    rows = {"A": [{"dataTime": "t", "pm10Value": "-", "pm25Value": "-"}]}
    monkeypatch.setattr(air, "_call_airkorea", _fake_call(nearby, rows))
    assert "error" in air.get_air_quality(37.5172, 127.0473)


# --- 일시적 오류 재시도 ---
class _FakeResp:
    """httpx 응답 흉내. status가 400 이상이면 raise_for_status()가 오류를 낸다."""
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "http://x"),
                response=httpx.Response(self.status),
            )

    def json(self):
        return {"response": {"header": {"resultCode": "00", "resultMsg": "OK"},
                             "body": {"items": [{"a": 1}]}}}


def _patch_get(monkeypatch, outcomes):
    """httpx.get을 가짜로 바꾼다. outcomes를 차례로 하나씩 사용하고 호출 횟수를 센다.

    outcomes의 각 항목: 예외 객체(발생시킴) 또는 _FakeResp(돌려줌)
    """
    calls = {"n": 0}

    def fake_get(url, params, timeout):
        outcome = outcomes[calls["n"]]
        calls["n"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(air.httpx, "get", fake_get)
    monkeypatch.setattr(air.time, "sleep", lambda seconds: None)  # 테스트가 느려지지 않게
    return calls


def test_call_retries_once_on_timeout(monkeypatch):
    calls = _patch_get(monkeypatch, [httpx.ReadTimeout("느림"), _FakeResp()])
    assert air._call_airkorea("http://x", {}) == [{"a": 1}]
    assert calls["n"] == 2  # 한 번 재시도해서 성공


def test_call_gives_up_after_two_timeouts(monkeypatch):
    calls = _patch_get(monkeypatch, [httpx.ReadTimeout("느림"), httpx.ReadTimeout("느림")])
    with pytest.raises(air.AirKoreaError):
        air._call_airkorea("http://x", {})
    assert calls["n"] == 2


def test_call_retries_on_504(monkeypatch):
    calls = _patch_get(monkeypatch, [_FakeResp(504), _FakeResp()])
    assert air._call_airkorea("http://x", {}) == [{"a": 1}]
    assert calls["n"] == 2


def test_call_does_not_retry_on_401(monkeypatch):
    # 인증 오류는 다시 시도해도 소용없으니 바로 중단한다
    calls = _patch_get(monkeypatch, [_FakeResp(401), _FakeResp()])
    with pytest.raises(air.AirKoreaError) as info:
        air._call_airkorea("http://x", {})
    assert calls["n"] == 1
    assert "401" in str(info.value)

# --- 지역 이름으로 조회 ---
def test_by_name_unknown_location():
    assert air.get_air_quality_by_name("없는지역") == {"error": "알 수 없는 지역: 없는지역"}


def test_by_name_adds_location(monkeypatch):
    monkeypatch.setattr(air, "get_air_quality", lambda lat, lon: {"station_name": "A"})
    result = air.get_air_quality_by_name("서울 강남구")
    assert result["location"] == "서울 강남구"
    assert result["station_name"] == "A"