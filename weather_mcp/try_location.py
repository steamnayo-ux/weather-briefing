"""지역 검색 실제 호출 확인 (카카오 로컬 API). 키는 출력하지 않는다.

실행: 프로젝트 루트에서  python -m weather_mcp.try_location
"""
from weather_mcp.services import location
from weather_mcp.services.location_resolve import LocationError

# 구 단위, 장소명, 중복 지역명, 도로명, 약칭, 없는 지역을 섞어서 본다
QUERIES = [
    "분당구",
    "판교역",
    "성남 판교역",
    "중구",
    "강남",
    "제주시",
    "경북 안동시",
    "서울 중구 세종대로 110",
    "없는지역xyz",
]

for q in QUERIES:
    print("검색어:", q)
    try:
        loc = location.get_location(q)
    except LocationError as exc:
        # 후보가 여러 곳이거나 검색 서비스 오류 (메시지에 키/URL 없음)
        print("  ->", type(exc).__name__, "|", exc)
        continue
    if loc is None:
        print("  -> 결과 없음")
    else:
        print("  ->", loc["name"], "|", loc["matched_address"],
              "| 위도", loc["lat"], "경도", loc["lon"])
