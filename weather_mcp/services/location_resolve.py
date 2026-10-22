"""카카오 로컬 API 응답을 해석해 지역 하나로 확정하는 순수 함수 모음.

네트워크 호출이 없으므로 가짜 응답으로 테스트할 수 있다.
다음 단계에서 services/location.py의 실제 API 호출과 연결한다.

규칙
- 주소 검색 결과가 있으면 주소 결과만 쓴다 (키워드 결과는 엉뚱한 장소가 잡히기 쉽다).
- 주소 결과가 없을 때만 키워드 결과를 쓴다 (예: '판교역').
- 후보가 하나면 확정, 둘 이상이면 추측하지 않고 LocationAmbiguous로 알린다.
"""

MAX_SHOWN = 5            # 오류 메시지에 보여줄 후보 최대 개수
KEYWORD_CHECK_COUNT = 5  # 키워드 결과 중 지역 판단에 쓸 상위 개수 (뒤쪽은 잡음이 많다)


class LocationError(Exception):
    """지역 조회 오류의 공통 부모.

    weather.py·air.py는 `except LocationError` 한 줄로 아래 두 오류를 모두 처리한다.
    메시지에는 키나 URL이 들어가지 않으므로 사용자에게 그대로 보여줘도 안전하다.
    """


class LocationAmbiguous(LocationError):
    """검색어가 여러 지역에 해당할 때 발생한다. (지역을 추측하지 않는다)"""

    def __init__(self, message: str, candidates: list[dict]):
        super().__init__(message)
        self.candidates = candidates


class LocationLookupError(LocationError):
    """지역 검색 서비스 호출 자체가 실패했을 때 발생한다.

    '그런 지역이 없음'(None)과 구분하기 위한 오류다. (키 오류, 네트워크 오류, 서버 오류 등)
    """


def _to_coords(doc: dict) -> tuple[float, float] | None:
    """문서에서 (위도, 경도)를 꺼낸다. 카카오 응답은 x=경도, y=위도이고 문자열이다."""
    try:
        return float(doc["y"]), float(doc["x"])
    except (KeyError, TypeError, ValueError):
        return None  # 좌표가 없거나 숫자가 아니면 후보에서 제외


def region_of(address_name: str) -> str:
    """주소 문자열에서 시도 + 시군구(+ 일반구)까지만 잘라낸다.

    예) '경기 성남시 분당구 판교역로 160' -> '경기 성남시 분당구'
        '서울 강남구 삼성동 131'          -> '서울 강남구'
        '세종특별자치시 한누리대로 2130'   -> '세종특별자치시'
    """
    tokens = address_name.split()
    if not tokens:
        return ""
    region = [tokens[0]]
    if len(tokens) > 1 and tokens[1].endswith(("시", "군", "구")):
        region.append(tokens[1])
        # 일반구가 있는 시 (성남시 분당구, 수원시 영통구 등)
        if tokens[1].endswith("시") and len(tokens) > 2 and tokens[2].endswith("구"):
            region.append(tokens[2])
    return " ".join(region)


def _from_address_docs(docs: list[dict]) -> list[dict]:
    """주소 검색 결과를 후보로 만든다. 같은 주소 문자열은 한 번만 쓴다."""
    seen: set[str] = set()
    result = []
    for doc in docs:
        addr = (doc.get("address_name") or "").strip()
        coords = _to_coords(doc)
        if not addr or coords is None or addr in seen:
            continue
        seen.add(addr)
        result.append({
            "name": addr,
            "lat": coords[0],
            "lon": coords[1],
            "matched_address": addr,
        })
    return result


def _from_keyword_docs(docs: list[dict]) -> list[dict]:
    """키워드 검색 상위 결과를 시군구 단위로 묶어 후보로 만든다.

    name은 지역 이름(다시 검색해도 1건으로 확정되는 값)이고,
    좌표는 그 지역에서 가장 먼저 나온 장소의 것을 쓴다.
    """
    seen_regions: set[str] = set()
    result = []
    for doc in docs[:KEYWORD_CHECK_COUNT]:
        addr = (doc.get("address_name") or "").strip()
        coords = _to_coords(doc)
        if not addr or coords is None:
            continue
        region = region_of(addr)
        if region in seen_regions:
            continue
        seen_regions.add(region)
        result.append({
            "name": region,
            "lat": coords[0],
            "lon": coords[1],
            "matched_address": addr,
            "place_name": (doc.get("place_name") or "").strip(),
        })
    return result


def build_candidates(address_docs: list[dict], keyword_docs: list[dict]) -> list[dict]:
    """주소 결과가 있으면 그것만, 없으면 키워드 결과로 후보 목록을 만든다."""
    candidates = _from_address_docs(address_docs)
    if candidates:
        return candidates
    return _from_keyword_docs(keyword_docs)


def resolve_location(query: str, address_docs: list[dict], keyword_docs: list[dict]) -> dict | None:
    """검색어를 지역 하나로 확정한다.

    - 후보 없음: None
    - 후보 1개: 그 후보(dict)
    - 후보 2개 이상: LocationAmbiguous (추측하지 않는다)
    """
    candidates = build_candidates(address_docs, keyword_docs)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    names = [c["name"] for c in candidates]
    shown = ", ".join(names[:MAX_SHOWN])
    extra = len(names) - MAX_SHOWN
    if extra > 0:
        shown += f" 외 {extra}곳"
    raise LocationAmbiguous(
        f"'{query}'에 해당하는 지역이 여러 곳입니다: {shown}. 지역 이름을 더 구체적으로 입력해 주세요.",
        candidates,
    )
