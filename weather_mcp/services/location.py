"""위치 조회 서비스.

1단계에서는 소수의 지역만 하드코딩한 임시 데이터를 사용한다.
2단계에서 실제 주소 -> 좌표 -> 격자 변환으로 교체한다.
"""

# 임시 데이터: 격자(nx, ny)는 기상청 단기예보 기준 예시 값
_LOCATIONS = {
    "서울 종로구": {"lat": 37.5729, "lon": 126.9794, "nx": 60, "ny": 127},
    "서울 강남구": {"lat": 37.5172, "lon": 127.0473, "nx": 61, "ny": 126},
}


def search_location(query: str) -> list[dict]:
    """검색어가 포함된 지역 목록을 반환한다."""
    query = query.strip()
    results = []
    for name, info in _LOCATIONS.items():
        if query in name:  # 부분 일치
            results.append({"name": name, **info})
    return results


def get_location(name: str) -> dict | None:
    """정확한 이름으로 지역 하나를 반환한다. 없으면 None."""
    info = _LOCATIONS.get(name)
    return {"name": name, **info} if info else None