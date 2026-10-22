"""대기질 조회 서비스 (에어코리아: 근접측정소 찾기 + 실시간 측정값)."""
import time
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from weather_mcp.services.location import get_location
from weather_mcp.services.location_resolve import LocationError
from weather_mcp.services.tm import latlon_to_tm
from weather_mcp.services.cache import TTLCache

# weather_mcp/.env 를 경로로 직접 지정해서 읽는다 (실행 위치와 무관하게 동작)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KST = timezone(timedelta(hours=9))
BASE = "https://apis.data.go.kr/B552584"
NEARBY_URL = f"{BASE}/MsrstnInfoInqireSvc/getNearbyMsrstnList"           # 근접측정소
REALTIME_URL = f"{BASE}/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"  # 실시간 측정값

# 서버가 느릴 때 게이트웨이가 약 30초 뒤 504를 돌려주는 것이 관찰되어, 그 응답까지 기다린다
TIMEOUT = httpx.Timeout(35.0, connect=5.0)  # 읽기 35초, 연결 5초
MAX_ATTEMPTS = 2  # 일시적 오류(타임아웃, 502/503/504)일 때만 1회 재시도
RETRY_STATUS = {502, 503, 504}  # 게이트웨이의 일시적 오류 코드
RETRY_WAIT_SECONDS = 1.0  # 재시도 전 잠깐 쉰다

# 등급 코드 -> 한글
GRADE_TEXT = {1: "좋음", 2: "보통", 3: "나쁨", 4: "매우나쁨"}

# 결과 캐시 (프로그램이 살아 있는 동안만 유지, 재시작하면 비워진다)
STATION_CACHE = TTLCache(ttl_seconds=24 * 60 * 60)  # 측정소 목록: 거의 안 바뀜 (임시 TTL)
REALTIME_CACHE = TTLCache(ttl_seconds=10 * 60)      # 측정값: 1시간 단위 갱신 (임시 TTL)


class AirKoreaError(Exception):
    """에어코리아 API 호출/응답 오류. 메시지에 인증키(URL)가 들어가지 않게 주의."""


def _to_float(value) -> float | None:
    """문자열을 float로 변환. None, '-', '' 처럼 변환할 수 없으면 None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    """문자열을 int로 변환. 변환할 수 없으면 None."""
    num = _to_float(value)
    return int(num) if num is not None else None


def _grade_text(value) -> str | None:
    """등급 코드('1'~'4')를 한글로 바꾼다. 알 수 없으면 None."""
    num = _to_int(value)
    return GRADE_TEXT.get(num) if num is not None else None


def _has_pm_data(row: dict) -> bool:
    """미세먼지(PM10, PM2.5) 값이 하나라도 있는지 확인한다."""
    return _to_float(row.get("pm10Value")) is not None or _to_float(row.get("pm25Value")) is not None


def _build_result(station: dict, row: dict) -> dict:
    """측정소 정보와 측정값 한 줄을 응답 형식으로 정리한다."""
    return {
        "station_name": station["stationName"],
        "station_distance_km": _to_float(station.get("tm")),
        "data_time": row.get("dataTime"),
        "pm10": _to_int(row.get("pm10Value")),
        "pm10_grade": _grade_text(row.get("pm10Grade1h")),
        "pm25": _to_int(row.get("pm25Value")),
        "pm25_grade": _grade_text(row.get("pm25Grade1h")),
    }


def _call_airkorea(url: str, params: dict) -> list[dict]:
    """에어코리아 API를 호출해 items 목록을 반환한다. 실패하면 AirKoreaError.

    일시적 오류(타임아웃, 502/503/504)만 한 번 더 시도하고, 그 밖의 오류는 바로 중단한다.
    """
    data = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = httpx.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            break  # 성공
        except httpx.TimeoutException as exc:  # HTTPError보다 먼저 잡아야 한다
            failure, retryable = type(exc).__name__, True
        except httpx.HTTPStatusError as exc:  # HTTPError보다 먼저 잡아야 한다
            code = exc.response.status_code
            failure, retryable = f"HTTP {code}", code in RETRY_STATUS
        except (httpx.HTTPError, ValueError) as exc:
            failure, retryable = type(exc).__name__, False

        if retryable and attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_WAIT_SECONDS)
            continue
        # str(exc)에는 URL(인증키 포함)이 들어갈 수 있어서 이름/상태코드만 노출
        raise AirKoreaError(f"에어코리아 API 호출 실패 ({failure})") from None

    try:
        header = data["response"]["header"]
        if header["resultCode"] != "00":  # "00"이 정상
            raise AirKoreaError(f"에어코리아 API 오류: {header['resultCode']} {header['resultMsg']}")
        return data["response"]["body"]["items"] or []  # 데이터가 없으면 ""로 올 수 있다
    except (KeyError, TypeError):
        raise AirKoreaError("에어코리아 응답 형식이 예상과 다릅니다") from None

def _now_iso() -> str:
    """현재 시각(KST)을 초 단위 문자열로 반환한다."""
    return datetime.now(KST).isoformat(timespec="seconds")


def _get_stations(api_key: str, tm_x: float, tm_y: float) -> list[dict]:
    """근접측정소 목록을 반환한다. 캐시에 있으면 API를 호출하지 않는다."""
    key = (round(tm_x, 2), round(tm_y, 2))  # 같은 좌표면 같은 목록
    hit = STATION_CACHE.get(key)
    if hit is not None:
        return hit[0]  # (값, 수집 시각) 중 값만 사용

    stations = _call_airkorea(NEARBY_URL, {
        "serviceKey": api_key, "returnType": "json",
        "tmX": round(tm_x, 2), "tmY": round(tm_y, 2),
    })
    if stations:  # 빈 결과는 캐시하지 않는다
        STATION_CACHE.set(key, stations, _now_iso())
    return stations


def _get_realtime_rows(api_key: str, name: str) -> tuple[list[dict], str]:
    """측정소의 실시간 측정값과 '실제 수집 시각'을 반환한다."""
    hit = REALTIME_CACHE.get(name)
    if hit is not None:
        return hit  # (rows, 처음 API에서 받은 시각)

    rows = _call_airkorea(REALTIME_URL, {
        "serviceKey": api_key, "returnType": "json",
        "stationName": name, "dataTerm": "DAILY",
        "pageNo": 1, "numOfRows": 1, "ver": "1.3",
    })
    fetched_at = _now_iso()
    if rows and _has_pm_data(rows[0]):  # 미세먼지 값이 있는 성공 결과만 캐시
        REALTIME_CACHE.set(name, rows, fetched_at)
    return rows, fetched_at


def get_air_quality(lat: float, lon: float) -> dict:
    """위경도에서 가장 가까운 측정소의 미세먼지 정보를 반환한다.

    가장 가까운 측정소에 값이 없으면(점검 등) 다음으로 가까운 측정소를 시도한다.
    실패하면 잘못된 값을 만들지 않고 {"error": ...}를 반환한다.
    """
    # 한국 범위를 벗어난 좌표는 잘못된 입력으로 처리 (엉뚱한 측정소 방지)
    if not (32.0 <= lat <= 39.5 and 124.0 <= lon <= 132.0):
        return {"error": f"한국 범위를 벗어난 좌표입니다: lat={lat}, lon={lon}"}

    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        return {"error": "API 키가 설정되지 않았습니다 (.env 확인)"}

    tm_x, tm_y = latlon_to_tm(lat, lon)  # 근접측정소 API는 TM 좌표를 요구한다
    now = datetime.now(KST)

    # 1) 가까운 측정소 목록 (가까운 순, 보통 3개)
    try:
                stations = _get_stations(api_key, tm_x, tm_y)
    except AirKoreaError as exc:
        return {"error": str(exc)}
    if not stations:
        return {"error": "근처 측정소를 찾지 못했습니다"}

    # 2) 가까운 측정소부터 실시간 측정값 조회 (값이 없으면 다음 측정소로)
    warnings: list[str] = []
    for station in stations:
        name = station.get("stationName")
        if not name:
            continue
        try:
                       rows, fetched_at = _get_realtime_rows(api_key, name)
        except AirKoreaError as exc:
            return {"error": str(exc)}  # 키/네트워크 오류는 다른 측정소를 시도해도 소용없다

        if rows and _has_pm_data(rows[0]):
            result = _build_result(station, rows[0])
            result.update(
                source="airkorea",
                collected_at=fetched_at,
                warnings=warnings,
            )
            return result
        warnings.append(f"{name} 측정소에 미세먼지 값이 없어 다음 측정소를 확인했습니다")

    return {"error": "근처 측정소에서 미세먼지 데이터를 받지 못했습니다", "warnings": warnings}


def get_air_quality_by_name(location_name: str) -> dict:
    """지역 이름으로 미세먼지 정보를 반환한다. (MCP 도구가 호출하는 함수)"""
    try:
        loc = get_location(location_name)
    except LocationError as exc:
        # 후보가 여러 곳이거나 지역 검색 서비스 오류: 메시지에 키/URL이 없어 그대로 전달한다
        return {"error": str(exc)}
    if loc is None:
        return {"error": f"알 수 없는 지역: {location_name}"}
    try:
        lat, lon = loc["lat"], loc["lon"]
    except KeyError:
        return {"error": f"좌표 정보가 없습니다: {location_name}"}

    result = get_air_quality(lat, lon)
    if "error" in result:
        return result
    return {"location": loc["name"], **result}