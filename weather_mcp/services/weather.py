"""날씨 조회 서비스 (2단계: 기상청 초단기실황 + 단기예보 연동)."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from weather_mcp.services.grid import latlon_to_grid
from weather_mcp.services.location import get_location
from weather_mcp.services.location_resolve import LocationError

# weather_mcp/.env 를 경로로 직접 지정해서 읽는다 (실행 위치와 무관하게 동작)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KST = timezone(timedelta(hours=9))
KMA_BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
NCST_URL = f"{KMA_BASE}/getUltraSrtNcst"  # 초단기실황 (현재 관측값)
FCST_URL = f"{KMA_BASE}/getVilageFcst"    # 단기예보 (하늘상태, 강수확률)

# 강수형태(PTY) 코드 -> 한글
PTY_TEXT = {
    0: "없음", 1: "비", 2: "비/눈", 3: "눈",
    5: "빗방울", 6: "빗방울/눈날림", 7: "눈날림",
}
# 하늘상태(SKY) 코드 -> 한글 (2는 없음)
SKY_TEXT = {1: "맑음", 3: "구름많음", 4: "흐림"}
# 단기예보 발표 시각(시)
FCST_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
# 해당 발표분의 자료가 아직 없을 때 쓰는 기상청 결과 코드 (NO_DATA)
NO_DATA_CODE = "03"


class KmaError(Exception):
    """기상청 API 호출/응답 오류. 메시지에 인증키(URL)가 들어가지 않게 주의.

    code: 기상청 resultCode (HTTP/형식 오류처럼 코드가 없으면 None)
    """

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


def _to_float(value) -> float | None:
    """문자열을 float로 변환. 변환 불가이거나 결측값(-999)이면 None."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return None if num <= -900 else num


def _base_datetime(now: datetime) -> tuple[str, str]:
    """초단기실황 기준 날짜/시각: 40분 전의 정시 (자료가 40분 이후 제공됨)."""
    base = now - timedelta(minutes=40)
    return base.strftime("%Y%m%d"), base.strftime("%H00")


def _forecast_base_candidates(now: datetime, count: int = 3) -> list[tuple[str, str]]:
    """단기예보 발표시각 후보를 최신 -> 이전 순서로 count개 반환한다.

    발표 10분 후부터 조회 가능하다고 보고 계산한다.
    """
    available = now - timedelta(minutes=10)
    candidates = []
    for day_offset in (0, 1):  # 오늘과 어제 후보 (02:10 이전엔 어제 23시 발표분)
        day = (available - timedelta(days=day_offset)).date()
        for hour in FCST_BASE_HOURS:
            candidates.append(datetime(day.year, day.month, day.day, hour, tzinfo=KST))
    valid = sorted((c for c in candidates if c <= available), reverse=True)
    return [(c.strftime("%Y%m%d"), c.strftime("%H00")) for c in valid[:count]]


def _forecast_base_datetime(now: datetime) -> tuple[str, str]:
    """가장 최근 발표시각 하나만 반환한다."""
    return _forecast_base_candidates(now, 1)[0]


def _pick_forecast_slot(items: list[dict], now: datetime) -> tuple[str | None, dict]:
    """현재 시각 이후 가장 가까운 예보 시각의 (시각키, {카테고리: 값})을 반환."""
    target = now.strftime("%Y%m%d%H00")
    slots: dict[str, dict[str, str]] = {}
    for it in items:
        key = it["fcstDate"] + it["fcstTime"]  # 예: "202610151000"
        slots.setdefault(key, {})[it["category"]] = it["fcstValue"]
    later = [k for k in slots if k >= target]  # 문자열 비교로 시각 비교 가능
    if not later:
        return None, {}
    key = min(later)
    return key, slots[key]


def _call_kma(url: str, params: dict) -> list[dict]:
    """기상청 API를 호출해 item 목록을 반환한다. 실패하면 KmaError."""
    try:
        resp = httpx.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # str(exc)에는 URL(인증키 포함)이 들어갈 수 있어서 클래스 이름만 노출
        raise KmaError(f"기상청 API 호출 실패 ({type(exc).__name__})") from None

    try:
        header = data["response"]["header"]
        code = header["resultCode"]
        if code != "00":  # "00"이 정상
            raise KmaError(f"기상청 API 오류: {code} {header['resultMsg']}", code=code)
        return data["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        raise KmaError("기상청 응답 형식이 예상과 다릅니다") from None


def _params(api_key: str, base_date: str, base_time: str, nx: int, ny: int, rows: int) -> dict:
    """기상청 API 공통 요청 파라미터."""
    return {
        "serviceKey": api_key, "pageNo": 1, "numOfRows": rows,
        "dataType": "JSON", "base_date": base_date, "base_time": base_time,
        "nx": nx, "ny": ny,
    }


def _fetch_forecast(api_key: str, nx: int, ny: int, now: datetime):
    """단기예보를 최신 발표분부터 조회한다. 자료가 없으면(NO_DATA) 이전 발표분으로 재시도.

    반환: (예보시각키, {카테고리: 값}, 사용한 발표분 "YYYYMMDD HHMM")
    실패하면 KmaError, 모든 후보에서 해당 시각을 못 찾으면 (None, {}, None).
    """
    last_error: KmaError | None = None
    for f_date, f_time in _forecast_base_candidates(now):
        try:
            items = _call_kma(FCST_URL, _params(api_key, f_date, f_time, nx, ny, 300))
        except KmaError as exc:
            last_error = exc
            if exc.code == NO_DATA_CODE:
                continue  # 이 발표분은 아직 없음 -> 한 단계 이전 발표분으로 재시도
            raise  # 키 오류, 네트워크 오류 등은 재시도해도 소용없으니 중단
        key, values = _pick_forecast_slot(items, now)
        if key is not None:
            return key, values, f"{f_date} {f_time}"
    if last_error is not None:
        raise last_error  # 모든 후보가 NO_DATA였던 경우
    return None, {}, None


def get_weather(location_name: str) -> dict:
    """지역 이름으로 현재 날씨를 반환한다.

    출처(source)와 수집 시각(collected_at)을 항상 함께 담는다.
    핵심 값(기온)이 없으면 {"error": ...}만 반환하고,
    보조 값(예보)이 실패하면 None으로 두고 warnings에 이유를 남긴다.
    """
    try:
        loc = get_location(location_name)
    except LocationError as exc:
        # 후보가 여러 곳이거나 지역 검색 서비스 오류: 메시지에 키/URL이 없어 그대로 전달한다
        return {"error": str(exc)}
    if loc is None:
        return {"error": f"알 수 없는 지역: {location_name}"}

    api_key = os.getenv("DATA_GO_KR_API_KEY")
    if not api_key:
        return {"error": "API 키가 설정되지 않았습니다 (.env 확인)"}

    try:
        nx, ny = latlon_to_grid(loc["lat"], loc["lon"])
    except (KeyError, ValueError):
        return {"error": f"좌표 변환 실패: {location_name}"}

    now = datetime.now(KST)

    # 1) 초단기실황 (핵심): 실패하면 브리핑을 만들지 않는다
    base_date, base_time = _base_datetime(now)
    try:
        items = _call_kma(NCST_URL, _params(api_key, base_date, base_time, nx, ny, 10))
        obs = {it["category"]: it["obsrValue"] for it in items}
    except KmaError as exc:
        return {"error": str(exc)}
    except (KeyError, TypeError):
        return {"error": "기상청 응답 형식이 예상과 다릅니다"}

    temperature = _to_float(obs.get("T1H"))
    if temperature is None:
        return {"error": "기온 데이터를 받지 못했습니다"}

    humidity = _to_float(obs.get("REH"))
    pty = _to_float(obs.get("PTY"))

    # 2) 단기예보 (보조): 실패해도 현재 날씨는 반환, 값은 None + warnings
    sky = None
    pop = None
    forecast_for = None
    forecast_base = None
    warnings: list[str] = []
    try:
        key, fc, forecast_base = _fetch_forecast(api_key, nx, ny, now)
        if key is None:
            warnings.append("예보 데이터에서 해당 시각을 찾지 못했습니다")
        else:
            forecast_for = f"{key[:8]} {key[8:]}"
            sky_code = _to_float(fc.get("SKY"))
            sky = SKY_TEXT.get(int(sky_code)) if sky_code is not None else None
            pop_val = _to_float(fc.get("POP"))
            pop = int(pop_val) if pop_val is not None else None
    except KmaError as exc:
        warnings.append(f"예보 조회 실패: {exc}")
    except (KeyError, TypeError):
        warnings.append("예보 응답 형식이 예상과 다릅니다")

    return {
        "location": loc["name"],
        "source": "kma",
        "collected_at": now.isoformat(timespec="seconds"),
        "observed_at": f"{base_date} {base_time}",  # 실황 관측 기준 시각
        "forecast_base": forecast_base,             # 사용한 예보 발표분
        "forecast_for": forecast_for,               # 예보값이 해당하는 시각
        "temperature_c": temperature,
        "humidity_pct": int(humidity) if humidity is not None else None,
        "precipitation_mm": _to_float(obs.get("RN1")),
        "precipitation_type": PTY_TEXT.get(int(pty)) if pty is not None else None,
        "wind_speed_ms": _to_float(obs.get("WSD")),
        "sky": sky,
        "precipitation_probability": pop,
        "warnings": warnings,
    }