"""날씨 조회 서비스 (2단계: 기상청 초단기실황 연동)."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from weather_mcp.services.grid import latlon_to_grid
from weather_mcp.services.location import get_location

# weather_mcp/.env 를 경로로 직접 지정해서 읽는다 (실행 위치와 무관하게 동작)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

KST = timezone(timedelta(hours=9))
KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

# 강수형태(PTY) 코드 -> 한글
PTY_TEXT = {
    0: "없음", 1: "비", 2: "비/눈", 3: "눈",
    5: "빗방울", 6: "빗방울/눈날림", 7: "눈날림",
}


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


def get_weather(location_name: str) -> dict:
    """지역 이름으로 현재 날씨를 반환한다.

    출처(source)와 수집 시각(collected_at)을 항상 함께 담는다.
    실패하면 잘못된 값을 만들지 않고 {"error": ...}만 반환한다.
    """
    loc = get_location(location_name)
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
    base_date, base_time = _base_datetime(now)
    params = {
        "serviceKey": api_key, "pageNo": 1, "numOfRows": 10,
        "dataType": "JSON", "base_date": base_date, "base_time": base_time,
        "nx": nx, "ny": ny,
    }

    try:
        resp = httpx.get(KMA_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # 주의: str(exc)에는 URL(인증키 포함)이 들어갈 수 있어서 클래스 이름만 노출
        return {"error": f"기상청 API 호출 실패 ({type(exc).__name__})"}

    try:
        header = data["response"]["header"]
        if header["resultCode"] != "00":  # "00"이 정상
            return {"error": f"기상청 API 오류: {header['resultCode']} {header['resultMsg']}"}
        items = data["response"]["body"]["items"]["item"]
        obs = {it["category"]: it["obsrValue"] for it in items}
    except (KeyError, TypeError):
        return {"error": "기상청 응답 형식이 예상과 다릅니다"}

    temperature = _to_float(obs.get("T1H"))
    if temperature is None:
        # 핵심 값(기온)이 없으면 브리핑을 만들지 않는다
        return {"error": "기온 데이터를 받지 못했습니다"}

    humidity = _to_float(obs.get("REH"))
    pty = _to_float(obs.get("PTY"))

    return {
        "location": loc["name"],
        "source": "kma",
        "collected_at": now.isoformat(timespec="seconds"),
        "observed_at": f"{base_date} {base_time}",  # 실제 관측 기준 시각
        "temperature_c": temperature,
        "humidity_pct": int(humidity) if humidity is not None else None,
        "precipitation_mm": _to_float(obs.get("RN1")),
        "precipitation_type": PTY_TEXT.get(int(pty)) if pty is not None else None,
        "wind_speed_ms": _to_float(obs.get("WSD")),
        "sky": None,                       # 다음 단계: 초단기예보(SKY)
        "precipitation_probability": None,  # 다음 단계: 단기예보(POP)
    }