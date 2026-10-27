"""체감온도 계산 (겨울철 바람 체감온도). 네트워크를 쓰지 않는 순수 계산 함수."""

# 적용 범위: 기온 10℃ 이하이고 풍속 1.3m/s 이상일 때만 바람 체감온도를 계산한다
WIND_CHILL_MAX_TEMP_C = 10.0
WIND_CHILL_MIN_WIND_MS = 1.3


def wind_chill_c(temp_c: float | None, wind_ms: float | None) -> float | None:
    """기온(℃)과 풍속(m/s)으로 겨울철 바람 체감온도(℃)를 구한다.

    값이 없거나 적용 범위 밖(따뜻하거나 바람이 약함)이면 None을 반환한다.
    """
    if temp_c is None or wind_ms is None:
        return None
    if temp_c > WIND_CHILL_MAX_TEMP_C or wind_ms < WIND_CHILL_MIN_WIND_MS:
        return None
    wind_kmh = wind_ms * 3.6      # 공식은 풍속을 km/h로 받는다
    factor = wind_kmh ** 0.16
    value = 13.12 + 0.6215 * temp_c - 11.37 * factor + 0.3965 * factor * temp_c
    return round(value, 1)