"""위치 조회 서비스 (카카오 로컬 API).

검색어를 지역 하나(이름, 위도, 경도)로 확정한다.
- 어떤 후보를 고를지는 location_resolve.py의 규칙을 따른다.
- 이 파일은 API 호출, 캐시, 오류 변환만 담당한다.

반환/오류 약속
- 확정: dict {"name", "lat", "lon", "matched_address", ...}
- 결과 없음: None
- 여러 지역에 해당: LocationAmbiguous (추측하지 않고 후보를 알린다)
- 검색 서비스 장애: LocationLookupError ('지역 없음'과 구분)
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from weather_mcp.services.cache import TTLCache
from weather_mcp.services.location_resolve import (
    LocationLookupError,
    build_candidates,
    resolve_location,
)

# weather_mcp/.env 를 경로로 직접 지정해서 읽는다 (air.py와 같은 방식)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = "https://dapi.kakao.com/v2/local/search"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)  # 읽기 10초, 연결 5초

# 카카오 응답 원본 캐시 (좌표는 거의 안 바뀌므로 길게, 성공한 응답만 저장)
DOCS_CACHE = TTLCache(ttl_seconds=24 * 60 * 60)


def _parse_response(status_code: int, body) -> list[dict]:
    """HTTP 상태와 본문을 해석해 documents 목록을 돌려준다. 실패하면 LocationLookupError.

    오류 메시지에는 키·URL·응답 본문을 넣지 않는다.
    """
    if status_code in (401, 403):
        raise LocationLookupError(
            "지역 검색 권한 오류입니다 (카카오 REST API 키와 카카오맵 사용 설정을 확인하세요)"
        )
    if status_code != 200:
        raise LocationLookupError(f"지역 검색에 실패했습니다 (HTTP {status_code})")
    docs = body.get("documents") if isinstance(body, dict) else None
    if not isinstance(docs, list):
        raise LocationLookupError("지역 검색 응답 형식이 예상과 다릅니다")
    return docs


def _call_kakao(kind: str, query: str) -> list[dict]:
    """카카오 로컬 API를 한 번 호출한다. kind는 'address' 또는 'keyword'."""
    key = os.getenv("KAKAO_REST_API_KEY")
    if not key:
        raise LocationLookupError("KAKAO_REST_API_KEY가 설정되지 않았습니다 (.env 확인)")
    try:
        resp = httpx.get(
            f"{BASE_URL}/{kind}.json",
            headers={"Authorization": f"KakaoAK {key}"},
            params={"query": query},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError:
        # 예외 메시지에 URL이 들어갈 수 있어 내용은 버리고 고정 문장만 쓴다
        raise LocationLookupError("지역 검색 서비스에 연결하지 못했습니다") from None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return _parse_response(resp.status_code, body)


def _fetch_docs(kind: str, query: str) -> list[dict]:
    """캐시를 거쳐 카카오 응답(documents)을 가져온다. 실패(예외)는 캐시하지 않는다."""
    cache_key = (kind, query)
    cached = DOCS_CACHE.get(cache_key)
    if cached is not None:
        return cached[0]
    docs = _call_kakao(kind, query)
    DOCS_CACHE.set(cache_key, docs, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return docs


def _normalize(text: str) -> str:
    """앞뒤 공백을 지우고 중간의 연속 공백을 하나로 줄인다."""
    return " ".join((text or "").split())


def _lookup(query: str) -> tuple[list[dict], list[dict]]:
    """주소 검색을 먼저 하고, 주소 결과가 없을 때만 키워드 검색을 한다."""
    address_docs = _fetch_docs("address", query)
    if build_candidates(address_docs, []):
        return address_docs, []  # 주소로 후보가 나오면 키워드 호출은 생략
    return address_docs, _fetch_docs("keyword", query)


def search_location(query: str) -> list[dict]:
    """검색어에 해당하는 지역 후보 목록을 반환한다. (MCP 도구가 호출하는 함수)

    여러 곳이어도 오류 없이 후보 전체를 돌려준다. 검색 서비스 장애는 LocationLookupError.
    """
    query = _normalize(query)
    if not query:
        return []
    address_docs, keyword_docs = _lookup(query)
    return build_candidates(address_docs, keyword_docs)


def get_location(name: str) -> dict | None:
    """검색어를 지역 하나로 확정한다. 없으면 None, 여러 곳이면 LocationAmbiguous."""
    query = _normalize(name)
    if not query:
        return None
    address_docs, keyword_docs = _lookup(query)
    return resolve_location(query, address_docs, keyword_docs)
