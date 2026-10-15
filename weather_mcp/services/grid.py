"""위경도 -> 기상청 격자(nx, ny) 변환 (Lambert Conformal Conic)"""
import math

# 기상청 공식 투영 파라미터 (고정값)
_RE = 6371.00877   # 지구 반경 (km)
_GRID = 5.0        # 격자 간격 (km)
_SLAT1 = 30.0      # 표준 위도 1
_SLAT2 = 60.0      # 표준 위도 2
_OLON = 126.0      # 기준점 경도
_OLAT = 38.0       # 기준점 위도
_XO = 43           # 기준점 X 격자
_YO = 136          # 기준점 Y 격자


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """위도/경도를 받아 (nx, ny) 격자 좌표를 반환한다."""
    # 한국 범위를 벗어난 값은 잘못된 입력으로 처리 (오류 시 잘못된 브리핑 방지)
    if not (32.0 <= lat <= 39.5 and 124.0 <= lon <= 132.0):
        raise ValueError(f"한국 범위를 벗어난 좌표입니다: lat={lat}, lon={lon}")

    degrad = math.pi / 180.0  # 도 -> 라디안
    re = _RE / _GRID
    slat1 = _SLAT1 * degrad
    slat2 = _SLAT2 * degrad
    olon = _OLON * degrad
    olat = _OLAT * degrad

    # 투영 상수 계산
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    # 입력 좌표 변환
    ra = math.tan(math.pi * 0.25 + lat * degrad * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * degrad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = math.floor(ra * math.sin(theta) + _XO + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + _YO + 0.5)
    return nx, ny