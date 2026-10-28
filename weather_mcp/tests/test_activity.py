"""활동 추천 테스트. 네트워크는 쓰지 않는다."""
import re
import pytest
from datetime import datetime, timedelta

from weather_mcp.services import activity, weather

@pytest.fixture(autouse=True)
def _no_uv_lookup(monkeypatch):
    """기존 활동 추천 테스트는 자외선을 보지 않는다. 실제 위치·기상청 호출을 막고
    판정에 영향 없는 낮은 값을 돌려준다 (자외선 연결은 test_activity_uv.py가 맡는다)."""
    monkeypatch.setattr(
        activity.uv, "get_uv_index",
        lambda *a, **k: {"uv_max": 1, "uv_level": "낮음", "uv_max_at": "12:00",
                         "area_level": "읍면동", "announced_at": "x"},
    )


def make_hour(time="09:00", temp=15.0, pop=0, pty="없음", humidity=50, wind=2.0, chill=None):
    """시간대별 예보의 한 시각 (get_hourly_forecast의 hours 한 줄과 같은 모양)."""
    return {"time": time, "temperature_c": temp, "sky": "맑음", "precipitation_type": pty,
            "precipitation_probability": pop, "precipitation_amount": "강수없음",
            "snow_amount": "적설없음", "humidity_pct": humidity, "wind_speed_ms": wind,
            "wind_chill_c": chill}


def make_hourly(*hours):
    return {"hours": list(hours), "summary": weather._summarize_hours(list(hours))}


def test_activity_aliases():
    assert activity.normalize_activity("달리기") == "러닝"
    assert activity.normalize_activity("퇴근길") == "외출"
    assert activity.normalize_activity("빨래 널기") == "빨래"
    assert activity.normalize_activity("산책") == "산책"
    assert activity.normalize_activity("스키") is None


def test_running_good_day():
    result = activity.assess_activity("러닝", make_hourly(make_hour()), dust_rank=0)
    assert result["verdict"] == "좋음"
    assert result["reasons"] == [activity.GOOD_REASON]
    assert result["items"] == [] and result["notes"] == []


def test_running_avoided_in_rain():
    result = activity.assess_activity("러닝", make_hourly(make_hour(pty="비", pop=70)), dust_rank=0)
    assert result["verdict"] == "비추천"


def test_running_avoided_when_dust_is_bad():
    hourly = make_hourly(make_hour())
    assert activity.assess_activity("러닝", hourly, dust_rank=2)["verdict"] == "비추천"
    assert activity.assess_activity("러닝", hourly, dust_rank=1)["verdict"] == "좋음"


def test_running_hot_and_windy_are_cautions():
    result = activity.assess_activity("러닝", make_hourly(make_hour(temp=29, wind=9)), dust_rank=0)
    assert result["verdict"] == "주의"
    assert "물" in result["items"]
    assert len(result["reasons"]) == 2


def test_running_uv_only_when_given():
    hourly = make_hourly(make_hour())
    assert activity.assess_activity("러닝", hourly, dust_rank=0)["verdict"] == "좋음"
    assert activity.assess_activity("러닝", hourly, dust_rank=0, uv_index=5)["verdict"] == "좋음"
    strong = activity.assess_activity("러닝", hourly, dust_rank=0, uv_index=7)
    assert strong["verdict"] == "주의"
    assert "자외선 차단제" in strong["items"]


def test_running_avoided_when_feels_very_cold():
    freezing = make_hourly(make_hour(temp=-5, wind=6, chill=-12))
    mild = make_hourly(make_hour(temp=-5, wind=6, chill=-9))
    assert activity.assess_activity("러닝", freezing, dust_rank=0)["verdict"] == "비추천"
    assert activity.assess_activity("러닝", mild, dust_rank=0)["verdict"] == "좋음"


def test_unknown_dust_adds_note_but_keeps_verdict():
    result = activity.assess_activity("러닝", make_hourly(make_hour()), dust_rank=None)
    assert result["verdict"] == "좋음"
    assert result["notes"] == [activity.DUST_UNKNOWN_NOTE]
    outing = activity.assess_activity("외출", make_hourly(make_hour()), dust_rank=None)
    assert outing["notes"] == []  # 외출은 미세먼지를 모른다고 알릴 필요가 없다


def test_walk_dust_and_cold_levels():
    hourly = make_hourly(make_hour())
    bad = activity.assess_activity("산책", hourly, dust_rank=2)
    assert bad["verdict"] == "주의" and "마스크" in bad["items"]
    assert activity.assess_activity("산책", hourly, dust_rank=3)["verdict"] == "비추천"
    chilly = make_hourly(make_hour(temp=0, wind=1.0))
    assert activity.assess_activity("산책", chilly, dust_rank=0)["verdict"] == "주의"
    frozen = make_hourly(make_hour(temp=-3, wind=6, chill=-16))
    assert activity.assess_activity("산책", frozen, dust_rank=0)["verdict"] == "비추천"


def test_outing_umbrella_levels():
    raining = activity.assess_activity("외출", make_hourly(make_hour(pty="비", pop=70)))
    assert raining["verdict"] == "주의" and raining["items"] == ["우산"]
    likely = activity.assess_activity("외출", make_hourly(make_hour(pop=70)))
    assert likely["items"] == ["우산"]
    maybe = activity.assess_activity("외출", make_hourly(make_hour(pop=30)))
    assert maybe["verdict"] == "주의" and maybe["items"] == ["작은 우산"]
    low = activity.assess_activity("외출", make_hourly(make_hour(pop=20)))
    assert low["verdict"] == "좋음"


def test_outing_clear_day_has_no_items():
    result = activity.assess_activity("외출", make_hourly(make_hour()), dust_rank=0)
    assert result["verdict"] == "좋음" and result["items"] == []


def test_laundry_rules():
    def verdict(*hours, dust=None):
        return activity.assess_activity("빨래", make_hourly(*hours), dust_rank=dust)["verdict"]

    assert verdict(make_hour()) == "좋음"
    assert verdict(make_hour(pty="비", pop=70)) == "비추천"
    assert verdict(make_hour(pop=60)) == "비추천"
    assert verdict(make_hour(pop=40)) == "주의"
    assert verdict(make_hour(humidity=80), make_hour(time="10:00", humidity=80)) == "주의"
    assert verdict(make_hour(temp=3)) == "주의"
    assert verdict(make_hour(), dust=2) == "주의"


def test_no_hours_means_unknown():
    empty = {"hours": [], "summary": weather._summarize_hours([])}
    result = activity.assess_activity("러닝", empty, dust_rank=0)
    assert result["verdict"] == "판단불가"
    assert result["reasons"] == [activity.NO_HOURS_REASON]


def test_unknown_activity_is_error():
    assert "error" in activity.assess_activity("스키", make_hourly(make_hour()))


def test_reasons_contain_no_digits():
    scenarios = [
        ("러닝", make_hourly(make_hour(pty="비", pop=70)), 2, 7),
        ("러닝", make_hourly(make_hour(temp=29, wind=9)), None, 7),
        ("산책", make_hourly(make_hour(temp=-3, wind=6, chill=-16)), 3, None),
        ("외출", make_hourly(make_hour(pop=40, temp=0, wind=1.0)), 2, 8),
        ("빨래", make_hourly(make_hour(pop=70, humidity=85, temp=3)), 2, None),
    ]
    for kind, hourly, dust, uv in scenarios:
        result = activity.assess_activity(kind, hourly, dust_rank=dust, uv_index=uv)
        for text in result["reasons"] + result["items"] + result["notes"]:
            assert not re.search(r"\d", text), text  # 안내 문구에는 숫자를 넣지 않는다


def _fake_hourly(day, calls):
    def fake(name, date, start, end):
        calls.append((name, date, start, end))
        return {**make_hourly(make_hour()), "date": day, "location": "테스트",
                "collected_at": "수집시각", "forecast_base": "발표분", "warnings": []}
    return fake


def test_recommend_activity_uses_default_hours_and_air(monkeypatch):
    today = datetime.now(weather.KST).date().isoformat()
    calls = []
    monkeypatch.setattr(activity.weather, "get_hourly_forecast", _fake_hourly(today, calls))
    monkeypatch.setattr(activity.air, "get_air_quality_by_name",
                        lambda name: {"pm10_grade": "나쁨", "pm25_grade": "보통"})
    result = activity.recommend_activity("테스트", "달리기")
    assert calls == [("테스트", "오늘", 6, 22)]
    assert result["activity"] == "러닝"
    assert result["verdict"] == "비추천"  # 미세먼지 나쁨
    assert result["location"] == "테스트"


def test_recommend_activity_skips_air_for_other_days(monkeypatch):
    tomorrow = (datetime.now(weather.KST).date() + timedelta(days=1)).isoformat()

    def must_not_call(name):
        raise AssertionError("오늘이 아니면 대기질을 조회하면 안 된다")

    monkeypatch.setattr(activity.weather, "get_hourly_forecast", _fake_hourly(tomorrow, []))
    monkeypatch.setattr(activity.air, "get_air_quality_by_name", must_not_call)
    result = activity.recommend_activity("테스트", "러닝", "내일")
    assert result["verdict"] == "좋음"
    assert result["notes"] == [activity.DUST_TODAY_ONLY_NOTE]


def test_recommend_activity_passes_errors_through(monkeypatch):
    monkeypatch.setattr(activity.weather, "get_hourly_forecast",
                        lambda name, date, start, end: {"error": "알 수 없는 지역: 없는곳"})
    assert activity.recommend_activity("없는곳", "산책") == {"error": "알 수 없는 지역: 없는곳"}
    assert "error" in activity.recommend_activity("테스트", "스키")


def test_recommend_activity_end_hour_follows_start(monkeypatch):
    today = datetime.now(weather.KST).date().isoformat()
    calls = []
    monkeypatch.setattr(activity.weather, "get_hourly_forecast", _fake_hourly(today, calls))
    monkeypatch.setattr(activity.air, "get_air_quality_by_name", lambda name: {})
    activity.recommend_activity("테스트", "빨래", start_hour=20)  # 기본 끝 시각(18)보다 늦게 시작
    assert calls[0][2:] == (20, 20)