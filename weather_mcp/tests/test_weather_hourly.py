"""시간대별 예보 테스트. 네트워크는 쓰지 않는다."""
from datetime import date, datetime

from weather_mcp.services import weather

DATE = "20261027"


def hour_items(day, time, TMP="15", POP="0", PTY="0", SKY="1", PCP="강수없음", REH="50", WSD="2.0"):
    """한 시각의 예보 item 묶음 (기상청은 시각마다 항목별로 따로 준다)."""
    values = {"TMP": TMP, "POP": POP, "PTY": PTY, "SKY": SKY, "PCP": PCP,
              "SNO": "적설없음", "REH": REH, "WSD": WSD}
    return [{"fcstDate": day, "fcstTime": time, "category": c, "fcstValue": v}
            for c, v in values.items()]


# ---- 날짜 해석 ----

def test_resolve_date_words_and_formats():
    now = datetime(2026, 10, 27, 9, 0, tzinfo=weather.KST)
    assert weather._resolve_forecast_date("오늘", now) == date(2026, 10, 27)
    assert weather._resolve_forecast_date(None, now) == date(2026, 10, 27)
    assert weather._resolve_forecast_date("내일", now) == date(2026, 10, 28)
    assert weather._resolve_forecast_date("모레", now) == date(2026, 10, 29)
    assert weather._resolve_forecast_date("2026-10-28", now) == date(2026, 10, 28)
    assert weather._resolve_forecast_date("20261029", now) == date(2026, 10, 29)
    assert weather._resolve_forecast_date("다음주", now) is None


# ---- 시간별 목록 만들기 ----

def test_build_hourly_filters_date_and_hours_in_order():
    items = (hour_items(DATE, "1800", TMP="14") + hour_items(DATE, "1700", TMP="16")
             + hour_items(DATE, "2000", TMP="12") + hour_items("20261028", "1700", TMP="5"))
    hours = weather._build_hourly(items, DATE, 17, 18)
    assert [h["time"] for h in hours] == ["17:00", "18:00"]  # 시간 순서, 범위 밖·다른 날짜 제외
    assert hours[0]["temperature_c"] == 16.0
    assert hours[0]["sky"] == "맑음"
    assert hours[0]["precipitation_probability"] == 0
    assert hours[0]["humidity_pct"] == 50
    assert hours[0]["wind_speed_ms"] == 2.0


def test_forecast_precipitation_type_codes():
    items = (hour_items(DATE, "0900", PTY="0") + hour_items(DATE, "1000", PTY="4")
             + hour_items(DATE, "1100", PTY="9"))
    types = [h["precipitation_type"] for h in weather._build_hourly(items, DATE, 0, 23)]
    assert types == ["없음", "소나기", "알 수 없음(9)"]  # 4=소나기, 모르는 코드는 숨기지 않는다


def test_precipitation_amount_text_is_kept():
    items = hour_items(DATE, "1500", PTY="1", PCP="1.0mm")
    assert weather._build_hourly(items, DATE, 0, 23)[0]["precipitation_amount"] == "1.0mm"


def test_summary_lists_rainy_hours():
    items = (hour_items(DATE, "1700", TMP="16", POP="30") + hour_items(DATE, "1800", TMP="14", POP="70", PTY="1")
             + hour_items(DATE, "1900", TMP="13", POP="60", PTY="4"))
    summary = weather._summarize_hours(weather._build_hourly(items, DATE, 17, 19))
    assert summary == {"temp_min_c": 13.0, "temp_max_c": 16.0,
                       "precipitation_probability_max": 70,
                       "precipitation_times": ["18:00", "19:00"]}


def test_summary_of_empty_hours():
    assert weather._summarize_hours([]) == {
        "temp_min_c": None, "temp_max_c": None,
        "precipitation_probability_max": None, "precipitation_times": []}


# ---- get_hourly_forecast 전체 흐름 ----

def _patch(monkeypatch, fake_call, location=None):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    monkeypatch.setattr(weather, "get_location",
                        lambda name: location or {"name": "테스트", "lat": 37.37, "lon": 127.11})
    monkeypatch.setattr(weather, "_call_kma", fake_call)


def _today():
    return datetime.now(weather.KST).strftime("%Y%m%d")


def test_get_hourly_forecast_returns_requested_range(monkeypatch):
    today = _today()
    calls = []

    def fake_call(url, params):
        calls.append(params)
        return (hour_items(today, "1700") + hour_items(today, "1800", POP="80", PTY="1")
                + hour_items(today, "1900") + hour_items(today, "2000"))

    _patch(monkeypatch, fake_call)
    result = weather.get_hourly_forecast("테스트", "오늘", 18, 19)
    assert [h["time"] for h in result["hours"]] == ["18:00", "19:00"]
    assert result["summary"]["precipitation_times"] == ["18:00"]
    assert result["summary"]["precipitation_probability_max"] == 80
    assert result["warnings"] == []
    assert calls[0]["numOfRows"] == weather.HOURLY_ROWS  # 내일·모레까지 들어오는 크기


def test_get_hourly_forecast_warns_when_no_hours(monkeypatch):
    _patch(monkeypatch, lambda url, params: hour_items(_today(), "2300"))
    result = weather.get_hourly_forecast("테스트", "오늘", 6, 8)
    assert result["hours"] == []
    assert result["warnings"]


def test_get_hourly_forecast_retries_older_base_on_no_data(monkeypatch):
    today = _today()
    calls = []

    def fake_call(url, params):
        calls.append(params)
        if len(calls) == 1:
            raise weather.KmaError("자료 없음", code=weather.NO_DATA_CODE)
        return hour_items(today, "1800")

    _patch(monkeypatch, fake_call)
    result = weather.get_hourly_forecast("테스트", "오늘", 0, 23)
    assert len(calls) == 2
    assert calls[0]["base_time"] != calls[1]["base_time"] or calls[0]["base_date"] != calls[1]["base_date"]
    assert result["forecast_base"] == f"{calls[1]['base_date']} {calls[1]['base_time']}"
    assert len(result["hours"]) == 1


def test_get_hourly_forecast_rejects_bad_input(monkeypatch):
    def must_not_call(url, params):
        raise AssertionError("입력이 잘못되면 API를 부르면 안 된다")

    _patch(monkeypatch, must_not_call)
    assert "error" in weather.get_hourly_forecast("테스트", "다음주")
    assert "error" in weather.get_hourly_forecast("테스트", "2020-01-01")   # 과거
    assert "error" in weather.get_hourly_forecast("테스트", "2099-01-01")   # 너무 먼 미래
    assert "error" in weather.get_hourly_forecast("테스트", "오늘", 19, 17)  # 시작 > 끝
    assert "error" in weather.get_hourly_forecast("테스트", "오늘", 0, 24)   # 범위 밖


def test_get_hourly_forecast_unknown_location(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "test-key")
    monkeypatch.setattr(weather, "get_location", lambda name: None)
    assert "알 수 없는 지역" in weather.get_hourly_forecast("없는곳")["error"]


def test_get_hourly_forecast_kma_error_becomes_error_dict(monkeypatch):
    def fake_call(url, params):
        raise weather.KmaError("기상청 API 호출 실패 (ConnectError)")

    _patch(monkeypatch, fake_call)
    assert "error" in weather.get_hourly_forecast("테스트")