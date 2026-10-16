"""날씨 + 대기질 데이터를 하나로 합치는 서비스.

AI 호출 없이 데이터 수집과 실패 처리만 담당한다.
한쪽만 실패하면 성공한 쪽만 담고 이유를 warnings에 남기고,
둘 다 실패하면 브리핑 없이 error를 반환한다.
"""
from datetime import datetime, timedelta, timezone

from weather_mcp.services import air, weather

KST = timezone(timedelta(hours=9))


def _safe_call(label: str, func, location_name: str) -> tuple[dict | None, str | None]:
    """func(location_name)을 호출해 (결과, 실패 이유)를 반환한다.

    성공하면 (결과, None), 실패하면 (None, 이유).
    예상치 못한 예외는 str(exc)에 키/URL이 들어갈 수 있어서 예외 이름만 남긴다.
    """
    try:
        result = func(location_name)
    except Exception as exc:
        return None, f"{label} 조회 중 예상치 못한 오류 ({type(exc).__name__})"
    if not isinstance(result, dict):
        return None, f"{label} 응답 형식이 올바르지 않습니다"
    if "error" in result:
        return None, f"{label}: {result['error']}"
    return result, None


def build_briefing_data(location_name: str) -> dict:
    """날씨와 대기질을 합친 브리핑용 데이터를 반환한다.

    실패한 쪽은 None으로 두어, 다음 단계에서 AI에게 '확인 불가'로 전달할 수 있게 한다.
    각 데이터는 자신의 source, collected_at을 그대로 유지한다.
    """
    weather_data, weather_problem = _safe_call("날씨", weather.get_weather, location_name)
    air_data, air_problem = _safe_call("대기질", air.get_air_quality_by_name, location_name)

    warnings = [p for p in (weather_problem, air_problem) if p]

    if weather_data is None and air_data is None:
        return {"error": "날씨와 대기질 정보를 모두 가져오지 못했습니다", "warnings": warnings}

    return {
        "location": location_name,
        "weather": weather_data,  # 실패하면 None
        "air": air_data,          # 실패하면 None
        "warnings": warnings,
        "built_at": datetime.now(KST).isoformat(timespec="seconds"),
    }