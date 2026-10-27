"""체감온도 테스트. 네트워크는 쓰지 않는다."""
import pytest

from weather_mcp.services import weather
from weather_mcp.services.feels_like import wind_chill_c


def test_known_value_at_10c():
    # 기온 10℃, 풍속 5km/h -> 약 9.755 (공식 검증용 값)
    assert wind_chill_c(10, 5 / 3.6) == pytest.approx(9.8, abs=0.1)


def test_below_zero_with_wind():
    assert wind_chill_c(0, 5) == pytest.approx(-4.9, abs=0.1)


def test_very_cold_and_windy():
    assert wind_chill_c(-10, 10) == pytest.approx(-20.3, abs=0.1)


def test_not_applicable_when_warm():
    assert wind_chill_c(10.1, 5) is None
    assert wind_chill_c(25, 5) is None


def test_not_applicable_when_calm():
    assert wind_chill_c(0, 1.2) is None
    assert wind_chill_c(0, 0) is None


def test_boundaries_apply():
    assert wind_chill_c(10, 1.3) is not None  # 기온 10℃, 풍속 1.3m/s는 적용 범위 안


def test_missing_values():
    assert wind_chill_c(None, 5) is None
    assert wind_chill_c(0, None) is None


def test_wind_chill_never_warmer_than_air():
    for temp in (10, 5, 0, -5, -15):
        for wind in (1.3, 3, 8, 15):
            assert wind_chill_c(temp, wind) <= temp


def _hour_items(day, time, temp, wind):
    values = {"TMP": temp, "WSD": wind, "POP": "0", "PTY": "0", "SKY": "1",
              "PCP": "강수없음", "SNO": "적설없음", "REH": "50"}
    return [{"fcstDate": day, "fcstTime": time, "category": c, "fcstValue": v}
            for c, v in values.items()]


def test_hourly_includes_wind_chill():
    items = _hour_items("20261027", "0900", "0", "5.0")
    hour = weather._build_hourly(items, "20261027", 0, 23)[0]
    assert hour["wind_chill_c"] == pytest.approx(-4.9, abs=0.1)


def test_hourly_wind_chill_is_none_when_not_applicable():
    items = _hour_items("20261027", "1500", "15", "2.0")
    hour = weather._build_hourly(items, "20261027", 0, 23)[0]
    assert hour["wind_chill_c"] is None