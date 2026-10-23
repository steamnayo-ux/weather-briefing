"""briefing.py 테스트. 날씨/대기질/지역 함수를 가짜로 바꿔서 성공·실패 조합을 확인한다."""
import pytest

from weather_mcp.services import briefing
from weather_mcp.services.location_resolve import LocationError

# 가짜 응답 (실제 응답의 일부 필드만 흉내 낸다)
WEATHER_OK = {"location": "서울 강남구", "source": "kma", "collected_at": "t1", "warnings": []}
AIR_OK = {"location": "서울 강남구", "source": "airkorea", "collected_at": "t2", "pm10": 19, "warnings": []}


@pytest.fixture(autouse=True)
def location_ok(monkeypatch):
    """기본값: 지역은 항상 확정된 것으로 본다 (실제 카카오 호출 차단)."""
    monkeypatch.setattr(briefing.location, "get_location", lambda name: {"name": name})


def patch(monkeypatch, weather_result, air_result):
    """날씨/대기질 함수를 가짜로 교체한다. 결과가 Exception이면 그 예외를 발생시킨다."""
    def fake_weather(name):
        if isinstance(weather_result, Exception):
            raise weather_result
        return weather_result

    def fake_air(name):
        if isinstance(air_result, Exception):
            raise air_result
        return air_result

    monkeypatch.setattr(briefing.weather, "get_weather", fake_weather)
    monkeypatch.setattr(briefing.air, "get_air_quality_by_name", fake_air)


def test_both_ok(monkeypatch):
    patch(monkeypatch, WEATHER_OK, AIR_OK)
    result = briefing.build_briefing_data("서울 강남구")

    assert result["weather"] == WEATHER_OK
    assert result["air"] == AIR_OK
    assert result["warnings"] == []
    assert result["weather"]["collected_at"] == "t1"  # 각자의 수집 시각을 그대로 유지


def test_weather_fails_air_kept(monkeypatch):
    patch(monkeypatch, {"error": "기상청 호출 실패"}, AIR_OK)
    result = briefing.build_briefing_data("서울 강남구")

    assert result["weather"] is None
    assert result["air"] == AIR_OK
    assert len(result["warnings"]) == 1 and "날씨" in result["warnings"][0]


def test_air_fails_weather_kept(monkeypatch):
    patch(monkeypatch, WEATHER_OK, {"error": "에어코리아 호출 실패"})
    result = briefing.build_briefing_data("서울 강남구")

    assert result["weather"] == WEATHER_OK
    assert result["air"] is None
    assert len(result["warnings"]) == 1 and "대기질" in result["warnings"][0]


def test_both_fail_returns_error(monkeypatch):
    patch(monkeypatch, {"error": "날씨 실패"}, {"error": "대기질 실패"})
    result = briefing.build_briefing_data("서울 강남구")

    assert "error" in result
    assert "weather" not in result and "air" not in result  # 브리핑 데이터를 만들지 않는다
    assert len(result["warnings"]) == 2


def test_unexpected_exception_does_not_leak(monkeypatch):
    # 예외 메시지에 비밀(키)이 들어 있어도 결과에 나오면 안 된다
    patch(monkeypatch, RuntimeError("secret-key-123"), AIR_OK)
    result = briefing.build_briefing_data("서울 강남구")

    assert result["weather"] is None
    assert result["air"] == AIR_OK
    assert "secret-key-123" not in str(result)
    assert "RuntimeError" in result["warnings"][0]


# ---------- 지역 사전 확인 (날씨·대기질 호출 전에 걸러낸다) ----------

def _forbid_api_calls(monkeypatch):
    """날씨/대기질이 호출되면 기록해서 '호출되지 않았음'을 확인할 수 있게 한다."""
    calls = []

    def should_not_call(name):
        calls.append(name)
        return {}

    monkeypatch.setattr(briefing.weather, "get_weather", should_not_call)
    monkeypatch.setattr(briefing.air, "get_air_quality_by_name", should_not_call)
    return calls


def test_ambiguous_location_stops_before_api_calls(monkeypatch):
    msg = "'중구'에 해당하는 지역이 여러 곳입니다: 서울 중구, 대전 중구. 지역 이름을 더 구체적으로 입력해 주세요."

    def fake_get_location(name):
        raise LocationError(msg)

    monkeypatch.setattr(briefing.location, "get_location", fake_get_location)
    calls = _forbid_api_calls(monkeypatch)

    result = briefing.build_briefing_data("중구")

    assert result["error"] == msg      # 일반 문구로 가리지 않고 후보 안내를 그대로 전달
    assert result["warnings"] == []    # 중복 경고 없음
    assert calls == []                 # 날씨·대기질 API는 호출하지 않는다


def test_unknown_location_stops_before_api_calls(monkeypatch):
    monkeypatch.setattr(briefing.location, "get_location", lambda name: None)
    calls = _forbid_api_calls(monkeypatch)

    result = briefing.build_briefing_data("없는지역xyz")

    assert "없는지역xyz" in result["error"]
    assert calls == []


def test_location_lookup_error_is_passed_through(monkeypatch):
    def fake_get_location(name):
        raise LocationError("지역 검색 서비스에 일시적으로 연결할 수 없습니다")

    monkeypatch.setattr(briefing.location, "get_location", fake_get_location)
    calls = _forbid_api_calls(monkeypatch)

    result = briefing.build_briefing_data("서울 강남구")

    assert "일시적으로" in result["error"]
    assert calls == []


def test_unexpected_location_exception_does_not_leak(monkeypatch):
    def fake_get_location(name):
        raise RuntimeError("secret-key-123")

    monkeypatch.setattr(briefing.location, "get_location", fake_get_location)
    calls = _forbid_api_calls(monkeypatch)

    result = briefing.build_briefing_data("서울 강남구")

    assert "secret-key-123" not in str(result)   # 키가 결과에 나오면 안 된다
    assert "RuntimeError" in result["error"]
    assert calls == []