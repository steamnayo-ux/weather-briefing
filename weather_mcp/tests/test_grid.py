import pytest
from services.grid import latlon_to_grid


# (이름, 위도, 경도, 기대 nx, 기대 ny)
@pytest.mark.parametrize("name, lat, lon, nx, ny", [
    ("서울", 37.5665, 126.9780, 60, 127),
    ("부산", 35.1796, 129.0756, 98, 76),
    ("제주", 33.4996, 126.5312, 53, 38),
])
def test_known_cities(name, lat, lon, nx, ny):
    assert latlon_to_grid(lat, lon) == (nx, ny)


def test_out_of_korea_raises():
    # 도쿄 좌표는 한국 범위 밖 -> 오류가 나야 정상
    with pytest.raises(ValueError):
        latlon_to_grid(35.68, 139.69)