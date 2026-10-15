"""위경도(WGS84) -> TM 중부원점(EPSG:5181) 변환. 에어코리아 근접측정소 조회용.

GRS80 타원체 + Transverse Mercator 투영 (Krüger 급수).
"""
import math

# 중부원점 TM 파라미터
_A = 6378137.0               # GRS80 장반경 (m)
_F = 1 / 298.257222101       # GRS80 편평률
_LAT0, _LON0 = 38.0, 127.0   # 원점 위도/경도
_K0 = 1.0                    # 축척계수
_FE, _FN = 200000.0, 500000.0  # 가산 동경/북위 (m)

# 투영에 쓰는 상수 (한 번만 계산)
_N = _F / (2 - _F)
_E = math.sqrt(_F * (2 - _F))
_AA = _A / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64)
_ALPHA = (
    _N / 2 - 2 * _N**2 / 3 + 5 * _N**3 / 16,
    13 * _N**2 / 48 - 3 * _N**3 / 5,
    61 * _N**3 / 240,
)


def _conformal(lat_rad: float, dlon_rad: float) -> tuple[float, float]:
    """등각 위도 기반의 중간값(xi', eta')을 계산한다."""
    tau = math.tan(lat_rad)
    sigma = math.sinh(_E * math.atanh(_E * tau / math.sqrt(1 + tau**2)))
    tau_p = tau * math.sqrt(1 + sigma**2) - sigma * math.sqrt(1 + tau**2)
    xi_p = math.atan2(tau_p, math.cos(dlon_rad))
    eta_p = math.asinh(math.sin(dlon_rad) / math.sqrt(tau_p**2 + math.cos(dlon_rad) ** 2))
    return xi_p, eta_p


def _xi_eta(lat_rad: float, dlon_rad: float) -> tuple[float, float]:
    """급수 보정을 적용한 (xi, eta)를 계산한다."""
    xi_p, eta_p = _conformal(lat_rad, dlon_rad)
    xi, eta = xi_p, eta_p
    for j, alpha in enumerate(_ALPHA, start=1):
        xi += alpha * math.sin(2 * j * xi_p) * math.cosh(2 * j * eta_p)
        eta += alpha * math.cos(2 * j * xi_p) * math.sinh(2 * j * eta_p)
    return xi, eta


def latlon_to_tm(lat: float, lon: float) -> tuple[float, float]:
    """위도/경도를 받아 TM 중부원점 (x, y) 좌표(m)를 반환한다."""
    xi, eta = _xi_eta(math.radians(lat), math.radians(lon - _LON0))
    xi0, _ = _xi_eta(math.radians(_LAT0), 0.0)  # 원점 위도의 기준값
    x = _K0 * _AA * eta + _FE
    y = _K0 * _AA * (xi - xi0) + _FN
    return x, y