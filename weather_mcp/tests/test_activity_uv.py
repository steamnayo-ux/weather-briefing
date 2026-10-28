"""recommend_activity가 자외선을 올바르게 연결하는지 본다 (규칙 자체는 assess_activity 테스트가 맡는다)."""
from weather_mcp.services import activity
from weather_mcp.services.location_resolve import LocationError

# 오늘이 아닌 날짜라서 미세먼지(에어코리아) 호출은 일어나지 않는다
HOURLY = {"location": "서울", "date": "2099-01-01", "collected_at": "x", "forecast_base": "y"}
UV_INFO = {"uv_max": 7, "uv_level": "높음", "uv_max_at": "12:00",
           "area_level": "읍면동", "announced_at": "2099010109"}


def _setup(monkeypatch, uv_func, notes=None):
    captured = {}
    monkeypatch.setattr(activity.weather, "get_hourly_forecast", lambda *a, **k: dict(HOURLY))

    def fake_assess(kind, hourly, **kwargs):
        captured.update(kwargs)
        return {"verdict": "좋음", "notes": list(notes or [])}

    monkeypatch.setattr(activity, "assess_activity", fake_assess)
    monkeypatch.setattr(activity.uv, "get_uv_index", uv_func)
    return captured


def test_자외선_최대값이_규칙에_전달된다(monkeypatch):
    seen = {}

    def fake_uv(name, date_text, start, end):
        seen["args"] = (name, date_text, start, end)
        return UV_INFO

    captured = _setup(monkeypatch, fake_uv)
    r = activity.recommend_activity("서울", "외출", "내일", 17, 19)
    assert captured["uv_index"] == 7
    assert seen["args"] == ("서울", "2099-01-01", 17, 19)  # 해석된 날짜와 같은 시간 구간
    assert r["uv"]["uv_level"] == "높음"
    assert r["notes"] == []  # 값이 있으면 '확인하지 못했어요'를 붙이지 않는다


def test_자외선_조회가_실패해도_판정은_그대로(monkeypatch):
    def boom(*a, **k):
        raise activity.uv.UvServiceError("권한 오류")

    captured = _setup(monkeypatch, boom)
    r = activity.recommend_activity("서울", "러닝", "오늘")
    assert captured["uv_index"] is None
    assert r["verdict"] == "좋음"
    assert activity.UV_UNKNOWN_NOTE in r["notes"]
    assert r["uv"] is None


def test_지역_오류도_추천을_막지_않는다(monkeypatch):
    def boom(*a, **k):
        raise LocationError("지역 문제")

    captured = _setup(monkeypatch, boom)
    r = activity.recommend_activity("서울", "산책", "오늘")
    assert captured["uv_index"] is None
    assert activity.UV_UNKNOWN_NOTE in r["notes"]


def test_자외선_값을_모르면_None이고_안내가_붙는다(monkeypatch):
    captured = _setup(monkeypatch, lambda *a, **k: None)
    r = activity.recommend_activity("서울", "산책", "오늘")
    assert captured["uv_index"] is None
    assert activity.UV_UNKNOWN_NOTE in r["notes"]


def test_규칙이_이미_자외선_안내를_넣었으면_중복하지_않는다(monkeypatch):
    _setup(monkeypatch, lambda *a, **k: None, notes=["자외선지수는 알 수 없어요."])
    r = activity.recommend_activity("서울", "산책", "오늘")
    assert len(r["notes"]) == 1