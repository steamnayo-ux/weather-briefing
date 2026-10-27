"""하루 요약(최저·최고기온, 최대 강수확률) 테스트. 네트워크는 쓰지 않는다."""
from datetime import datetime

from weather_mcp.services import weather

DATE = "20261027"


def item(date, time, category, value):
    return {"fcstDate": date, "fcstTime": time, "category": category, "fcstValue": value}


def test_uses_tmn_and_tmx_when_present():
    items = [item(DATE, "0600", "TMN", "8.0"), item(DATE, "1500", "TMX", "18.0"),
             item(DATE, "0600", "TMP", "9"), item(DATE, "1500", "TMP", "17")]  # TMP보다 TMN·TMX가 우선
    result = weather._summarize_day(items, DATE)
    assert result["temp_min_c"] == 8.0
    assert result["temp_max_c"] == 18.0


def test_falls_back_to_hourly_temperature():
    items = [item(DATE, "0600", "TMP", "9"), item(DATE, "1500", "TMP", "17"),
             item(DATE, "1800", "TMP", "14")]
    result = weather._summarize_day(items, DATE)
    assert (result["temp_min_c"], result["temp_max_c"]) == (9.0, 17.0)


def test_only_target_date_counts():
    items = [item(DATE, "0900", "TMP", "10"), item("20261028", "0300", "TMP", "2"),
             item("20261028", "1500", "POP", "90")]
    result = weather._summarize_day(items, DATE)
    assert (result["temp_min_c"], result["temp_max_c"]) == (10.0, 10.0)
    assert result["precipitation_probability_max"] is None


def test_max_probability_of_the_day():
    items = [item(DATE, "0600", "POP", "0"), item(DATE, "1500", "POP", "60"),
             item(DATE, "1800", "POP", "30")]
    assert weather._summarize_day(items, DATE)["precipitation_probability_max"] == 60


def test_negative_temperatures_and_missing_values():
    items = [item(DATE, "0600", "TMP", "-7"), item(DATE, "1500", "TMP", "-3"),
             item(DATE, "1800", "TMP", "-999")]  # 결측값은 무시한다
    result = weather._summarize_day(items, DATE)
    assert (result["temp_min_c"], result["temp_max_c"]) == (-7.0, -3.0)
    assert weather._summarize_day([], DATE) == {
        "temp_min_c": None, "temp_max_c": None, "precipitation_probability_max": None}


def test_day_base_uses_0200_of_today():
    now = datetime(2026, 10, 27, 7, 0, tzinfo=weather.KST)
    assert weather._day_base(now) == ("20261027", "0200")


def test_day_base_before_0210_uses_yesterday_2300():
    early = datetime(2026, 10, 27, 1, 30, tzinfo=weather.KST)
    just_before = datetime(2026, 10, 27, 2, 9, tzinfo=weather.KST)
    just_after = datetime(2026, 10, 27, 2, 10, tzinfo=weather.KST)
    assert weather._day_base(early) == ("20261026", "2300")
    assert weather._day_base(just_before) == ("20261026", "2300")
    assert weather._day_base(just_after) == ("20261027", "0200")


def _patch_weather(monkeypatch, fake_call):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    monkeypatch.setattr(weather, "get_location",
                        lambda name: {"name": "테스트", "lat": 37.37, "lon": 127.11})
    monkeypatch.setattr(weather, "_call_kma", fake_call)


def test_get_weather_includes_daily_summary(monkeypatch):
    today = datetime.now(weather.KST).strftime("%Y%m%d")

    def fake_call(url, params):
        if url == weather.NCST_URL:
            return [{"category": "T1H", "obsrValue": "15.0"}, {"category": "PTY", "obsrValue": "0"}]
        return [item(today, "0600", "TMN", "8.0"), item(today, "1500", "TMX", "18.0"),
                item(today, "1800", "POP", "60")]

    _patch_weather(monkeypatch, fake_call)
    result = weather.get_weather("테스트")
    assert result["temperature_c"] == 15.0  # 현재 기온은 그대로 남는다
    assert (result["temp_min_c"], result["temp_max_c"]) == (8.0, 18.0)
    assert result["precipitation_probability_max"] == 60


def test_get_weather_survives_daily_failure(monkeypatch):
    def fake_call(url, params):
        if url == weather.NCST_URL:
            return [{"category": "T1H", "obsrValue": "15.0"}]
        raise weather.KmaError("실패", code="99")

    _patch_weather(monkeypatch, fake_call)
    result = weather.get_weather("테스트")
    assert result["temperature_c"] == 15.0
    assert result["temp_min_c"] is None and result["temp_max_c"] is None
    assert any("하루 요약" in w for w in result["warnings"])