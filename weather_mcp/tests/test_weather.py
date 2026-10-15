from datetime import datetime, timedelta, timezone

from weather_mcp.services.weather import _base_datetime

KST = timezone(timedelta(hours=9))


def test_base_datetime_normal():
    # 14:25 -> 40분 전 13:45 -> 정시 1300
    assert _base_datetime(datetime(2026, 10, 15, 14, 25, tzinfo=KST)) == ("20261015", "1300")


def test_base_datetime_midnight_rollover():
    # 00:20 -> 전날 23:40 -> 날짜가 어제, 시각 2300
    assert _base_datetime(datetime(2026, 10, 15, 0, 20, tzinfo=KST)) == ("20261014", "2300")