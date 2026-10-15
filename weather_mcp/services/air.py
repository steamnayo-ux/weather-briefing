"""대기질 조회 서비스 (에어코리아: 근접측정소 찾기 + 실시간 측정값)."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from weather_mcp.services.location import get_location
from weather_mcp.services.tm import latlon_to_tm

# weather_mcp/.env 를 경로로 직접 지정해서 읽는다 (실행 위치와 무관하게 동작)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KST = timezone(timedelta(hours=9))
BASE = "https://apis.data.go.kr/B552584"
NEARBY_URL = f"{BASE}/MsrstnInfoInqireSvc/getNearbyMsrstnList"           # 근접측정소
REALTIME_URL = f"{BASE}/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"  # 실시간 측정값

TIMEOUT = httpx.Timeout(15.0, connect=5.0)  # 읽기 15초, 연결 5초
MAX_ATTEMPTS = 2  # 타임아웃일 때만 1회 재시도

# 등급 코드 -> 한글
GRADE_TEXT = {1: "좋음", 2: "보통", 3: "나쁨", 4: "매우나쁨"}


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

    타임아웃(서버가 느릴 때)만 한 번 더 시도하고, 그 밖의 오류는 바로 중단한다.
    """
    data = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = httpx.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            break  # 성공
        except httpx.TimeoutException as exc:  # HTTPError보다 먼저 잡아야 한다
            if attempt == MAX_ATTEMPTS:
                raise AirKoreaError(f"에어코리아 API 호출 실패 ({type(exc).__name__})") from None
        except (httpx.HTTPError, ValueError) as exc:
            # str(exc)에는 URL(인증키 포함)이 들어갈 수 있어서 클래스 이름만 노출
            raise AirKoreaError(f"에어코리아 API 호출 실패 ({type(exc).__name__})") from None

    try:
        header = data["response"]["header"]
        if header["resultCode"] != "00":  # "00"이 정상
            raise AirKoreaError(f"에어코리아 API 오류: {header['resultCode']} {header['resultMsg']}")
        return data["response"]["body"]["items"] or []  # 데이터가 없으면 ""로 올 수 있다
    except (KeyError, TypeError):
        raise AirKoreaError("에어코리아 응답 형식이 예상과 다릅니다") from None


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
        stations = _call_airkorea(NEARBY_URL, {
            "serviceKey": api_key, "returnType": "json",
            "tmX": round(tm_x, 2), "tmY": round(tm_y, 2),
        })
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
            rows = _call_airkorea(REALTIME_URL, {
                "serviceKey": api_key, "returnType": "json",
                "stationName": name, "dataTerm": "DAILY",
                "pageNo": 1, "numOfRows": 1, "ver": "1.3",
            })
        except AirKoreaError as exc:
            return {"error": str(exc)}  # 키/네트워크 오류는 다른 측정소를 시도해도 소용없다

        if rows and _has_pm_data(rows[0]):
            result = _build_result(station, rows[0])
            result.update(
                source="airkorea",
                collected_at=now.isoformat(timespec="seconds"),
                warnings=warnings,
            )
            return result
        warnings.append(f"{name} 측정소에 미세먼지 값이 없어 다음 측정소를 확인했습니다")

    return {"error": "근처 측정소에서 미세먼지 데이터를 받지 못했습니다", "warnings": warnings}


def get_air_quality_by_name(location_name: str) -> dict:
    """지역 이름으로 미세먼지 정보를 반환한다. (MCP 도구가 호출하는 함수)"""
    loc = get_location(location_name)
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