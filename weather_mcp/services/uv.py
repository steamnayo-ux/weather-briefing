"""자외선지수 서비스 (기상청 생활기상지수 조회서비스 V5, getUVIdxV5).

흐름: 검색어 → 위치(위도·경도) → 행정구역 코드 → 지점코드(areaNo) 후보 → 최신 발표분 조회
      → 발표 시각 + N시간(hN)을 실제 시각으로 바꿔 구간 최대값을 구한다.

약속
- 값을 못 구하면 None (0으로 단정하지 않는다)
- 인증·한도 문제와 네트워크 장애는 UvServiceError
- 지역 문제는 location 쪽 LocationError가 그대로 올라온다
"""
import os
from datetime import date, datetime, timedelta, timezone
from urllib.parse import unquote

import httpx

from weather_mcp.services.cache import TTLCache
from weather_mcp.services.location import get_location, get_region_codes
from weather_mcp.services.location_resolve import LocationError

URL = "http://apis.data.go.kr/1360000/LivingWthrIdxServiceV5/getUVIdxV5"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
KST = timezone(timedelta(hours=9))  # 한국 시간

ANNOUNCE_TRIES = 3  # 최신 발표분부터 몇 개까지 거슬러 올라가 볼지
AUTH_CODES = {"20", "21", "22", "30", "31", "32", "33"}  # 인증·한도 문제 (코드 내려가기로 못 고침)
DAY_WORDS = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}

# 발표분은 3시간마다 바뀌므로 3시간 캐시 (데이터가 있는 응답만 저장)
ITEM_CACHE = TTLCache(ttl_seconds=3 * 60 * 60)


class UvServiceError(Exception):
    """자외선지수 호출이 인증·한도·네트워크 문제로 실패했을 때 발생한다. (키·URL은 메시지에 없다)"""


# ---------- 순수 함수 (네트워크 없음, 가짜 데이터로 테스트 가능) ----------

def uv_level(uv: int | None) -> str | None:
    """지수를 단계 이름으로 바꾼다. 모르면 None."""
    if uv is None:
        return None
    if uv < 3:
        return "낮음"
    if uv < 6:
        return "보통"
    if uv < 8:
        return "높음"
    if uv < 11:
        return "매우높음"
    return "위험"


def announce_times(now: datetime, count: int = ANNOUNCE_TRIES) -> list[str]:
    """최근 발표 시각 후보를 최신순으로 돌려준다. 발표는 00·03·…·21시 (예: 09시대 → 09시)."""
    base = now.replace(minute=0, second=0, microsecond=0)
    base -= timedelta(hours=base.hour % 3)
    return [(base - timedelta(hours=3 * i)).strftime("%Y%m%d%H") for i in range(count)]


def area_candidates(code: str | None) -> list[str]:
    """10자리 행정구역 코드에서 읍면동 → 시군구 → 시도 순서의 지점코드 후보를 만든다."""
    if not code or len(code) != 10 or not code.isdigit():
        return []
    result: list[str] = []
    for c in (code, code[:5] + "00000", code[:2] + "00000000"):
        if c not in result:
            result.append(c)
    return result


def area_level(area_no: str) -> str:
    """지점코드가 어느 단계인지 알려준다."""
    if area_no.endswith("00000000"):
        return "시도"
    if area_no.endswith("00000"):
        return "시군구"
    return "읍면동"


def _to_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None  # 빈 문자열("")이나 이상한 값은 모르는 값


def points_from_item(item: dict) -> list[dict]:
    """응답 item의 h0, h3, … 를 실제 시각으로 바꾼다. (hN = 발표 시각 + N시간)"""
    try:
        announced = datetime.strptime(item["date"], "%Y%m%d%H")
    except (KeyError, TypeError, ValueError):
        return []
    points = []
    for n in range(0, 79, 3):
        key = f"h{n}"
        if key in item:
            points.append({"at": announced + timedelta(hours=n), "uv": _to_int(item[key])})
    return points


def resolve_day(text: str | None, today: date) -> date:
    """'오늘·내일·모레·글피' 또는 'YYYY-MM-DD'를 날짜로 바꾼다."""
    if not text:
        return today
    text = text.strip()
    if text in DAY_WORDS:
        return today + timedelta(days=DAY_WORDS[text])
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"날짜를 이해하지 못했어요: {text} (오늘·내일·모레·글피 또는 YYYY-MM-DD)") from None


def summarize_window(points: list[dict], day: date, start_hour: int, end_hour: int) -> dict | None:
    """그날 [start_hour, end_hour] 구간의 최대 지수를 구한다. 값을 하나도 모르면 None."""
    day_points = [p for p in points if p["at"].date() == day]
    chosen = [p for p in day_points if start_hour <= p["at"].hour <= end_hour]
    if not chosen:
        # 구간 안에 3시간 간격 관측점이 없으면, 시작 직전 값을 대표로 쓴다
        before = [p for p in day_points if p["at"].hour <= start_hour]
        chosen = before[-1:]
    known = [p for p in chosen if p["uv"] is not None]
    if not known:
        return None
    top = max(known, key=lambda p: p["uv"])
    return {
        "uv_max": top["uv"],
        "uv_level": uv_level(top["uv"]),
        "uv_max_at": top["at"].strftime("%H:%M"),
        "window": f"{start_hour:02d}~{end_hour:02d}시",
        "points": [
            {"time": p["at"].strftime("%H:%M"), "uv": p["uv"], "level": uv_level(p["uv"])}
            for p in chosen
        ],
    }


def parse_response(status_code: int, body) -> dict | None:
    """HTTP 상태와 본문을 해석해 item(dict)을 돌려준다. 데이터가 없으면 None.

    인증·한도 문제는 UvServiceError. 그 외 실패는 '데이터 없음'으로 보고 다음 후보로 넘어간다.
    """
    if status_code in (401, 403):
        raise UvServiceError("자외선지수 권한 오류입니다 (인증키와 활용신청 상태를 확인하세요)")
    if status_code != 200 or not isinstance(body, dict):
        return None
    response = body.get("response")
    if not isinstance(response, dict):
        return None
    code = str((response.get("header") or {}).get("resultCode", ""))
    if code in AUTH_CODES:
        raise UvServiceError(f"자외선지수 권한·한도 오류입니다 (코드 {code})")
    if code != "00":
        return None
    items = (response.get("body") or {}).get("items")
    item = items.get("item") if isinstance(items, dict) else None
    if isinstance(item, list):
        item = item[0] if item else None
    return item if isinstance(item, dict) else None


# ---------- 네트워크 ----------

def _call_uv(area_no: str, time_str: str) -> dict | None:
    """기상청을 한 번 호출한다. item(dict) 또는 None(데이터 없음)."""
    cache_key = (area_no, time_str)
    cached = ITEM_CACHE.get(cache_key)
    if cached is not None:
        return cached[0]

    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        raise UvServiceError("DATA_GO_KR_API_KEY가 설정되지 않았습니다 (.env 확인)")
    try:
        resp = httpx.get(
            URL,
            params={
                "serviceKey": unquote(key),  # 인코딩된 키가 들어와도 이중 인코딩되지 않게
                "areaNo": area_no,
                "time": time_str,
                "dataType": "JSON",
                "numOfRows": "10",
                "pageNo": "1",
            },
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        # 예외 메시지에 URL(키 포함)이 들어갈 수 있어 내용은 버린다
        raise UvServiceError("자외선지수 서비스에 연결하지 못했습니다") from None
    try:
        body = resp.json()
    except ValueError:
        body = None
    item = parse_response(resp.status_code, body)
    if item is not None:
        ITEM_CACHE.set(cache_key, item, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return item


def fetch_latest_item(area_nos: list[str], now: datetime) -> tuple[str, dict] | None:
    """최신 발표분부터, 각 발표분에서 읍면동 → 시군구 → 시도 순서로 시도한다."""
    for time_str in announce_times(now):
        for area_no in area_nos:
            item = _call_uv(area_no, time_str)
            if item:
                return area_no, item
    return None


# ---------- 공개 함수 ----------

def get_uv_index_at(
    lat: float,
    lon: float,
    region: str,
    date_text: str | None = "오늘",
    start_hour: int = 0,
    end_hour: int = 23,
    now: datetime | None = None,
) -> dict | None:
    """좌표 기준 자외선지수. 구간 [start_hour, end_hour] 안의 최대값을 돌려준다. 모르면 None."""
    if not (0 <= start_hour <= end_hour <= 23):
        raise ValueError("시간 구간은 0 <= 시작 <= 종료 <= 23 이어야 해요")
    now = now or datetime.now(KST)
    day = resolve_day(date_text, now.date())

    codes = get_region_codes(lat, lon)
    area_nos = area_candidates(codes.get("h_code") or codes.get("b_code"))
    if not area_nos:
        return None
    found = fetch_latest_item(area_nos, now)
    if found is None:
        return None
    area_no, item = found
    summary = summarize_window(points_from_item(item), day, start_hour, end_hour)
    if summary is None:
        return None
    return {
        "region": region,
        "area_no": area_no,
        "area_level": area_level(area_no),
        "announced_at": item.get("date"),
        "date": day.isoformat(),
        **summary,
    }


def get_uv_index(
    location_name: str,
    date_text: str | None = "오늘",
    start_hour: int = 0,
    end_hour: int = 23,
    now: datetime | None = None,
) -> dict | None:
    """검색어(지역 이름) 기준 자외선지수. 지역 문제는 LocationError."""
    loc = get_location(location_name)
    if loc is None:
        raise LocationError(f"'{location_name}'에 해당하는 지역을 찾지 못했어요")
    return get_uv_index_at(loc["lat"], loc["lon"], loc["name"], date_text, start_hour, end_hour, now)