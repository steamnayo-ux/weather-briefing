"""읽기 전용 API 라우터 (/api/...).

- server.py 의 도구 함수를 그대로 호출하고, 응답 가공은 tool_output.py 를 재사용한다.
- 엔드포인트는 def(동기)로 둔다. 외부 API 가 느려도 FastAPI 가 스레드풀에서 실행한다.
- 발송 이력(DB)은 건드리지 않는다.
"""
from typing import Annotated

from fastapi import APIRouter, Query

from weather_mcp import server as tools
from weather_mcp.api_response import ApiError, ok_body
from weather_mcp.services import location as location_service
from weather_mcp.services.location_resolve import (
    LocationAmbiguous,
    LocationError,
    LocationLookupError,
)

router = APIRouter(prefix="/api")

Location = Annotated[str, Query(min_length=1, max_length=50, description="지역 이름 (구 단위 권장)")]
Hour = Annotated[int, Query(ge=0, le=23)]


def _to_api_error(exc: Exception) -> ApiError:
    """지역 확인 중 생긴 예외를 API 오류로 바꾼다. (하위 클래스부터 검사)"""
    if isinstance(exc, LocationAmbiguous):
        return ApiError(409, "AMBIGUOUS_LOCATION", str(exc), getattr(exc, "candidates", None))
    if isinstance(exc, LocationLookupError):
        return ApiError(502, "UPSTREAM_ERROR", str(exc))
    if isinstance(exc, LocationError):
        return ApiError(404, "LOCATION_NOT_FOUND", str(exc))
    # 예상 밖 예외는 str(exc)에 키/URL 이 들어갈 수 있어 이름만 남긴다
    return ApiError(500, "INTERNAL_ERROR", f"지역 확인 중 예상치 못한 오류 ({type(exc).__name__})")


def _check_location(name: str) -> None:
    """도구를 부르기 전에 지역을 확인한다. 문제가 있으면 ApiError 를 올린다."""
    try:
        loc = location_service.get_location(name)
    except Exception as exc:
        raise _to_api_error(exc) from None
    if loc is None:
        raise ApiError(404, "LOCATION_NOT_FOUND", f"'{name}'에 해당하는 지역을 찾지 못했습니다")


def _check_hours(start_hour: int | None, end_hour: int | None) -> None:
    if start_hour is not None and end_hour is not None and start_hour > end_hour:
        raise ApiError(422, "INVALID_PARAM", "start_hour 는 end_hour 보다 클 수 없습니다")


@router.get("/locations/search")
def api_search_location(q: Annotated[str, Query(min_length=1, max_length=50)]) -> dict:
    """지역 검색. 후보 목록을 돌려준다."""
    try:
        results = tools.search_location(q)
    except Exception as exc:
        raise _to_api_error(exc) from None
    return {"ok": True, "count": len(results), "results": results}


@router.get("/weather")
def api_weather(location: Location) -> dict:
    _check_location(location)
    return ok_body(tools.get_weather(location_name=location), "get_weather")


@router.get("/hourly")
def api_hourly(location: Location, date: str = "오늘", start_hour: Hour = 0, end_hour: Hour = 23) -> dict:
    _check_hours(start_hour, end_hour)
    _check_location(location)
    result = tools.get_hourly_forecast(
        location_name=location, date=date, start_hour=start_hour, end_hour=end_hour
    )
    return ok_body(result, "get_hourly_forecast")


@router.get("/air-quality")
def api_air_quality(location: Location) -> dict:
    _check_location(location)
    return ok_body(tools.get_air_quality(location_name=location), "get_air_quality")


@router.get("/uv")
def api_uv(location: Location, date: str = "오늘", start_hour: Hour = 0, end_hour: Hour = 23) -> dict:
    _check_hours(start_hour, end_hour)
    _check_location(location)
    result = tools.get_uv_index(
        location_name=location, date=date, start_hour=start_hour, end_hour=end_hour
    )
    return ok_body(result, "get_uv_index")


@router.get("/recommendations")
def api_recommendations(
    location: Location,
    activity: Annotated[str, Query(min_length=1, max_length=20, description="활동 이름 (러닝, 산책 등)")],
    date: str = "오늘",
    start_hour: int | None = Query(None, ge=0, le=23),
    end_hour: int | None = Query(None, ge=0, le=23),
) -> dict:
    _check_hours(start_hour, end_hour)
    _check_location(location)
    result = tools.recommend_activity(
        location_name=location,
        activity_name=activity,
        date=date,
        start_hour=start_hour,
        end_hour=end_hour,
    )
    return ok_body(result, "recommend_activity")