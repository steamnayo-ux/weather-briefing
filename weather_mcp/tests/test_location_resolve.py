"""location_resolve.py 테스트. 네트워크 없이 가짜 카카오 응답만 사용한다."""
import pytest

from weather_mcp.services.location_resolve import (
    LocationAmbiguous,
    build_candidates,
    region_of,
    resolve_location,
)


def addr(name, x="127.0", y="37.5"):
    """주소 검색 응답 문서 흉내 (x=경도, y=위도, 문자열)."""
    return {"address_name": name, "x": x, "y": y}


def place(place_name, address, x="127.0", y="37.5"):
    """키워드 검색 응답 문서 흉내."""
    return {"place_name": place_name, "address_name": address, "x": x, "y": y}


@pytest.mark.parametrize("text, expected", [
    ("서울 강남구 삼성동 131", "서울 강남구"),
    ("경기 성남시 분당구 판교역로 160", "경기 성남시 분당구"),
    ("경북 안동시 풍천면 하회리 1176-1", "경북 안동시"),
    ("세종특별자치시 한누리대로 2130", "세종특별자치시"),
    ("제주특별자치도 제주시 첨단로 242", "제주특별자치도 제주시"),
    ("", ""),
])
def test_region_of(text, expected):
    assert region_of(text) == expected


def test_주소_한_건이면_확정하고_x는_경도_y는_위도():
    r = resolve_location("강남", [addr("서울 강남구", x="127.047", y="37.517")], [])
    assert r["name"] == "서울 강남구"
    assert r["lat"] == 37.517
    assert r["lon"] == 127.047
    assert r["matched_address"] == "서울 강남구"


def test_같은_주소는_중복_제거():
    r = resolve_location("강남", [addr("서울 강남구"), addr("서울 강남구")], [])
    assert r["name"] == "서울 강남구"


def test_주소_여러_건이면_추측하지_않고_후보를_알린다():
    docs = [addr("서울 중구"), addr("인천 영종구"), addr("인천 제물포구")]
    with pytest.raises(LocationAmbiguous) as exc:
        resolve_location("중구", docs, [])
    assert [c["name"] for c in exc.value.candidates] == ["서울 중구", "인천 영종구", "인천 제물포구"]
    assert "서울 중구" in str(exc.value)
    assert "'중구'" in str(exc.value)


def test_후보가_많으면_5개만_보여주고_나머지는_개수로():
    docs = [addr(f"지역{i}구") for i in range(7)]
    with pytest.raises(LocationAmbiguous) as exc:
        resolve_location("구", docs, [])
    msg = str(exc.value)
    assert "지역4구" in msg
    assert "지역5구" not in msg
    assert "외 2곳" in msg
    assert len(exc.value.candidates) == 7  # 후보 데이터는 전부 보존


def test_주소_결과가_있으면_키워드_결과는_무시():
    keyword = [place("서울선릉과정릉", "서울 강남구 삼성동 131"), place("다른곳", "부산 중구 1")]
    r = resolve_location("강남", [addr("서울 강남구")], keyword)
    assert r["name"] == "서울 강남구"


def test_주소_0건이면_키워드로_대체하고_같은_지역이면_확정():
    keyword = [
        place("판교역", "경기 성남시 분당구 삼평동 681", x="127.111", y="37.394"),
        place("판교역 3번출구", "경기 성남시 분당구 삼평동 682", x="127.112", y="37.395"),
    ]
    r = resolve_location("판교역", [], keyword)
    assert r["name"] == "경기 성남시 분당구"
    assert r["place_name"] == "판교역"
    assert r["lat"] == 37.394  # 그 지역에서 가장 먼저 나온 장소의 좌표
    assert r["lon"] == 127.111


def test_키워드_결과가_여러_시군구에_걸리면_후보_안내():
    keyword = [place("스타벅스", "서울 강남구 1"), place("스타벅스", "서울 서초구 2")]
    with pytest.raises(LocationAmbiguous) as exc:
        resolve_location("스타벅스", [], keyword)
    assert [c["name"] for c in exc.value.candidates] == ["서울 강남구", "서울 서초구"]


def test_키워드는_상위_5개만_보고_뒤쪽_잡음은_무시():
    keyword = [place(f"판교역{i}", "경기 성남시 분당구 삼평동 1") for i in range(5)]
    keyword.append(place("멀리있는곳", "부산 중구 1"))  # 6번째는 판단에서 제외
    r = resolve_location("판교역", [], keyword)
    assert r["name"] == "경기 성남시 분당구"


def test_결과가_없으면_None():
    assert resolve_location("없는곳", [], []) is None


def test_좌표가_잘못된_문서는_후보에서_제외():
    docs = [addr("서울 중구", x="abc"), addr("서울 강남구")]
    r = resolve_location("테스트", docs, [])
    assert r["name"] == "서울 강남구"  # 좌표가 깨진 후보는 빠져서 1건으로 확정


def test_모든_좌표가_잘못되면_None():
    assert resolve_location("테스트", [{"address_name": "서울 중구"}], []) is None


def test_build_candidates는_주소가_있으면_주소만():
    cands = build_candidates([addr("서울 중구")], [place("덕수궁", "서울 중구 정동 5-1")])
    assert [c["name"] for c in cands] == ["서울 중구"]
