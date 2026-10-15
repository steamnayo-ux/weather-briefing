"""weather.py의 순수 함수(시각 계산, 예보 슬롯 선택) 테스트. API 호출 없이 동작한다."""
from datetime import datetime, timedelta, timezone

from weather_mcp.services.weather import (
    _base_datetime,
    _forecast_base_candidates,
    _forecast_base_datetime,
    _pick_forecast_slot,
)

KST = timezone(timedelta(hours=9))


# --- 초단기실황 기준 시각 계산 ---
def test_base_datetime_normal():
    # 14:25 -> 40분 전 13:45 -> 정시 1300
    assert _base_datetime(datetime(2026, 10, 15, 14, 25, tzinfo=KST)) == ("20261015", "1300")


def test_base_datetime_midnight_rollover():
    # 00:20 -> 전날 23:40 -> 날짜가 어제, 시각 2300
    assert _base_datetime(datetime(2026, 10, 15, 0, 20, tzinfo=KST)) == ("20261014", "2300")


# --- 단기예보 발표시각 계산 ---
def test_forecast_base_normal():
    # 10:34 -> 발표 10분 후 기준 가장 최근 발표는 08시
    assert _forecast_base_datetime(datetime(2026, 10, 15, 10, 34, tzinfo=KST)) == ("20261015", "0800")


def test_forecast_base_just_after_release():
    # 02:10 정각에는 02시 발표분 사용 가능
    assert _forecast_base_datetime(datetime(2026, 10, 15, 2, 10, tzinfo=KST)) == ("20261015", "0200")


def test_forecast_base_before_release_uses_yesterday():
    # 02:05는 아직 02시 발표분이 없으므로 어제 23시 발표분
    assert _forecast_base_datetime(datetime(2026, 10, 15, 2, 5, tzinfo=KST)) == ("20261014", "2300")


# --- 예보 발표시각 후보 (NO_DATA 재시도용) ---
def test_forecast_candidates_latest_first():
    # 14:33 -> 14시, 11시, 08시 발표분 순서
    got = _forecast_base_candidates(datetime(2026, 10, 15, 14, 33, tzinfo=KST))
    assert got == [("20261015", "1400"), ("20261015", "1100"), ("20261015", "0800")]


def test_forecast_candidates_cross_midnight():
    # 02:05 -> 어제 23시, 20시, 17시 발표분
    got = _forecast_base_candidates(datetime(2026, 10, 15, 2, 5, tzinfo=KST))
    assert got == [("20261014", "2300"), ("20261014", "2000"), ("20261014", "1700")]


# --- 예보 슬롯 선택 ---
def _item(time, category, value):
    """테스트용 예보 항목을 만든다."""
    return {"fcstDate": "20261015", "fcstTime": time, "category": category, "fcstValue": value}


def test_pick_forecast_slot_current_hour():
    items = [
        _item("0900", "SKY", "1"),
        _item("1000", "SKY", "3"),
        _item("1000", "POP", "20"),
        _item("1100", "SKY", "4"),
    ]
    key, values = _pick_forecast_slot(items, datetime(2026, 10, 15, 10, 34, tzinfo=KST))
    assert key == "202610151000"
    assert values == {"SKY": "3", "POP": "20"}


def test_pick_forecast_slot_none_when_all_past():
    # 예보가 전부 현재 시각보다 과거면 (None, {})를 돌려준다
    items = [_item("0900", "SKY", "1")]
    key, values = _pick_forecast_slot(items, datetime(2026, 10, 15, 10, 34, tzinfo=KST))
    assert key is None and values == {}