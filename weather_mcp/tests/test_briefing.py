"""briefing.py 테스트. 날씨/대기질 함수를 가짜로 바꿔서 성공·실패 조합을 확인한다."""
from weather_mcp.services import briefing

# 가짜 응답 (실제 응답의 일부 필드만 흉내 낸다)
WEATHER_OK = {"location": "서울 강남구", "source": "kma", "collected_at": "t1", "warnings": []}
AIR_OK = {"location": "서울 강남구", "source": "airkorea", "collected_at": "t2", "pm10": 19, "warnings": []}


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