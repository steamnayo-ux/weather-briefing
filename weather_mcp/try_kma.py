"""기상청 초단기실황 단독 호출 테스트 (MCP 연결 전 확인용)"""
import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from services.grid import latlon_to_grid

load_dotenv()  # .env 파일의 값을 환경변수로 읽어온다
API_KEY = os.getenv("DATA_GO_KR_API_KEY")
URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
KST = timezone(timedelta(hours=9))  # 한국 시간 (UTC+9)


def get_base_datetime(now: datetime) -> tuple[str, str]:
    """초단기실황 기준 날짜/시각 계산 (40분 전의 정시)"""
    base = now - timedelta(minutes=40)
    return base.strftime("%Y%m%d"), base.strftime("%H00")


def main():
    if not API_KEY:
        raise SystemExit(".env에서 DATA_GO_KR_API_KEY를 찾지 못했어요.")

    # 서울시청 좌표 -> 격자 변환 (어제 만든 함수 재사용!)
    nx, ny = latlon_to_grid(37.5665, 126.9780)
    now = datetime.now(KST)
    base_date, base_time = get_base_datetime(now)

    params = {
        "serviceKey": API_KEY,
        "pageNo": 1,
        "numOfRows": 10,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    print(f"요청: 격자=({nx},{ny}), 기준={base_date} {base_time}")

    resp = httpx.get(URL, params=params, timeout=10)
    resp.raise_for_status()  # HTTP 오류(4xx/5xx)면 여기서 멈춤

    try:
        data = resp.json()
    except ValueError:
        # 키 오류 등은 JSON이 아니라 XML로 올 때가 있다
        print("JSON이 아닌 응답:", resp.text[:300])
        return

    header = data["response"]["header"]
    if header["resultCode"] != "00":  # "00"이 정상
        print("API 오류:", header["resultCode"], header["resultMsg"])
        return

    items = data["response"]["body"]["items"]["item"]
    result = {it["category"]: it["obsrValue"] for it in items}
    print("결과:", result)
    print("source: 기상청 초단기실황 / collected_at:", now.isoformat())


if __name__ == "__main__":
    main()