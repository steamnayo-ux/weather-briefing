import pytest

from weather_mcp.services.tm import latlon_to_tm


def test_origin_point():
    # 중부원점(위도 38, 경도 127)은 (200000, 500000)이어야 한다
    x, y = latlon_to_tm(38.0, 127.0)
    assert x == pytest.approx(200000.0, abs=0.01)
    assert y == pytest.approx(500000.0, abs=0.01)


# 기대값은 pyproj(WGS84 -> EPSG:5181)로 계산한 값
@pytest.mark.parametrize("name, lat, lon, x, y", [
    ("강남구청", 37.515336, 127.049357, 204363.52, 446207.37),
    ("서울시청", 37.5665, 126.9780, 198056.37, 451885.03),
    ("부산", 35.1796, 129.0756, 389076.80, 188993.76),
    ("제주", 33.4996, 126.5312, 156437.52, 758.48),
])
def test_matches_pyproj(name, lat, lon, x, y):
    got_x, got_y = latlon_to_tm(lat, lon)
    assert got_x == pytest.approx(x, abs=0.5)
    assert got_y == pytest.approx(y, abs=0.5)