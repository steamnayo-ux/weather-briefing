"""카카오 로컬 API 지역 검색 단독 테스트. 키는 출력하지 않는다."""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("KAKAO_REST_API_KEY")
HEADERS = {"Authorization": f"KakaoAK {KEY}"}
BASE = "https://dapi.kakao.com/v2/local/search"

# 구 단위, 시 단위, 장소명을 섞어서 어떻게 나오는지 본다
QUERIES = ["중구", "경북 안동시", "서울 중구 세종대로 110", "강남"]


def show(kind: str, query: str) -> None:
    resp = httpx.get(f"{BASE}/{kind}.json", headers=HEADERS,
                     params={"query": query}, timeout=10)
    body = resp.json()
    if resp.status_code != 200:
        # 오류 정보만 출력 (키·헤더는 출력하지 않는다)
        print(f"  [{kind}] 실패 {resp.status_code}", body.get("errorType"), body.get("message"))
        return
    docs = body.get("documents", [])
    print(f"  [{kind}] {len(docs)}건")
    for d in docs[:3]:
        name = d.get("place_name") or d.get("address_name")
        print("   ", name, "|", d.get("address_name"), "| 경도", d.get("x"), "위도", d.get("y"))


for q in QUERIES:
    print("검색어:", q)
    show("address", q)
    show("keyword", q)