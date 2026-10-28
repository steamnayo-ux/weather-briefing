from datetime import date, datetime, timedelta, timezone

import pytest

from weather_mcp.services import uv

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 28, 9, 41, tzinfo=KST)

# 2026-10-28 09시 발표분 실제 응답 (서울). h0=오늘 09시, h24=내일 09시, h63부터는 빈 값
ITEM = {
    "code": "A07_2", "areaNo": "1100000000", "date": "2026102809",
    "h0": "4", "h3": "4", "h6": "2", "h9": "0", "h12": "0", "h15": "0", "h18": "0", "h21": "0",
    "h24": "3", "h27": "4", "h30": "0", "h33": "0", "h36": "0", "h39": "0", "h42": "0", "h45": "0",
    "h48": "2", "h51": "3", "h54": "1", "h57": "0", "h60": "0",
    "h63": "", "h66": "", "h69": "", "h72": "", "h75": "",
}


@pytest.mark.parametrize("value, expected", [
    (0, "낮음"), (2, "낮음"), (3, "보통"), (5, "보통"), (6, "높음"), (7, "높음"),
    (8, "매우높음"), (10, "매우높음"), (11, "위험"), (13, "위험"), (None, None),
])
def test_지수_단계(value, expected):
    assert uv.uv_level(value) == expected


def test_발표_시각_후보는_3시간_단위_최신순():
    assert uv.announce_times(NOW) == ["2026102809", "2026102806", "2026102803"]


def test_자정_근처는_전날로_넘어간다():
    now = datetime(2026, 10, 29, 1, 5, tzinfo=KST)
    assert uv.announce_times(now)[:2] == ["2026102900", "2026102821"]


def test_지점코드_후보는_읍면동_시군구_시도_순서():
    assert uv.area_candidates("1168064000") == ["1168064000", "1168000000", "1100000000"]
    assert uv.area_candidates("1168000000") == ["1168000000", "1100000000"]
    assert uv.area_candidates("1100000000") == ["1100000000"]
    assert uv.area_candidates(None) == []
    assert uv.area_candidates("abc") == []


def test_지점코드_단계():
    assert uv.area_level("1100000000") == "시도"
    assert uv.area_level("1168000000") == "시군구"
    assert uv.area_level("1168064000") == "읍면동"


def test_hN을_실제_시각으로_바꾼다():
    points = uv.points_from_item(ITEM)
    assert points[0] == {"at": datetime(2026, 10, 28, 9), "uv": 4}
    assert points[8]["at"] == datetime(2026, 10, 29, 9) and points[8]["uv"] == 3  # h24
    assert any(p["uv"] is None for p in points)  # 빈 문자열은 None


def test_날짜_해석():
    today = date(2026, 10, 28)
    assert uv.resolve_day(None, today) == today
    assert uv.resolve_day("내일", today) == date(2026, 10, 29)
    assert uv.resolve_day("2026-11-02", today) == date(2026, 11, 2)
    with pytest.raises(ValueError):
        uv.resolve_day("다음주", today)


def test_오늘_하루_최대값():
    r = uv.summarize_window(uv.points_from_item(ITEM), date(2026, 10, 28), 0, 23)
    assert r["uv_max"] == 4 and r["uv_level"] == "보통" and r["uv_max_at"] == "09:00"


def test_구간_최대값():
    r = uv.summarize_window(uv.points_from_item(ITEM), date(2026, 10, 28), 15, 18)
    assert r["uv_max"] == 2 and r["uv_max_at"] == "15:00"


def test_구간에_관측점이_없으면_직전_값을_쓴다():
    r = uv.summarize_window(uv.points_from_item(ITEM), date(2026, 10, 28), 19, 20)
    assert r["uv_max"] == 0 and r["uv_level"] == "낮음"


def test_내일과_모레():
    pts = uv.points_from_item(ITEM)
    tomorrow = uv.summarize_window(pts, date(2026, 10, 29), 0, 23)
    assert tomorrow["uv_max"] == 4 and tomorrow["uv_max_at"] == "12:00"
    after = uv.summarize_window(pts, date(2026, 10, 30), 0, 23)
    assert after["uv_max"] == 3 and after["uv_max_at"] == "12:00"


def test_모르는_값은_None():
    pts = uv.points_from_item(ITEM)
    assert uv.summarize_window(pts, date(2026, 10, 31), 0, 23) is None  # 값이 빈 문자열
    assert uv.summarize_window(pts, date(2026, 10, 28), 0, 8) is None   # 발표 이전 시각


def test_응답_해석_정상과_데이터없음():
    ok = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [ITEM]}}}}
    assert uv.parse_response(200, ok) == ITEM
    nodata = {"response": {"header": {"resultCode": "03"}}}
    assert uv.parse_response(200, nodata) is None
    assert uv.parse_response(200, None) is None
    assert uv.parse_response(500, None) is None


def test_인증_오류는_예외():
    with pytest.raises(uv.UvServiceError):
        uv.parse_response(403, None)
    with pytest.raises(uv.UvServiceError):
        uv.parse_response(200, {"response": {"header": {"resultCode": "30"}}})


def test_읍면동이_없으면_시군구로_내려간다(monkeypatch):
    calls = []
    monkeypatch.setattr(uv, "get_region_codes", lambda lat, lon: {"h_code": "1168064000", "b_code": "1168010100"})

    def fake_call(area_no, time_str):
        calls.append((area_no, time_str))
        return ITEM if area_no == "1168000000" else None

    monkeypatch.setattr(uv, "_call_uv", fake_call)
    r = uv.get_uv_index_at(37.5, 127.0, "서울 강남구", "오늘", now=NOW)
    assert r["area_no"] == "1168000000" and r["area_level"] == "시군구"
    assert r["uv_max"] == 4 and r["uv_level"] == "보통"
    assert calls == [("1168064000", "2026102809"), ("1168000000", "2026102809")]


def test_최신_발표분이_없으면_이전_발표분을_쓴다(monkeypatch):
    older = {**ITEM, "date": "2026102806"}
    monkeypatch.setattr(uv, "get_region_codes", lambda lat, lon: {"h_code": "1100000000", "b_code": None})
    monkeypatch.setattr(uv, "_call_uv", lambda area_no, time_str: older if time_str == "2026102806" else None)
    r = uv.get_uv_index_at(37.5, 127.0, "서울", "오늘", now=NOW)
    assert r["announced_at"] == "2026102806"


def test_코드를_못_얻으면_호출_없이_None(monkeypatch):
    monkeypatch.setattr(uv, "get_region_codes", lambda lat, lon: {"h_code": None, "b_code": None})

    def boom(area_no, time_str):
        raise AssertionError("호출하면 안 돼요")

    monkeypatch.setattr(uv, "_call_uv", boom)
    assert uv.get_uv_index_at(37.5, 127.0, "어딘가", "오늘", now=NOW) is None


def test_시간_구간이_잘못되면_오류():
    with pytest.raises(ValueError):
        uv.get_uv_index_at(37.5, 127.0, "서울", "오늘", start_hour=20, end_hour=10, now=NOW)