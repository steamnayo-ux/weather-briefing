# weather-briefing

[![tests](https://github.com/steamnayo-ux/weather-briefing/actions/workflows/test.yml/badge.svg)](https://github.com/steamnayo-ux/weather-briefing/actions/workflows/test.yml)

기상청·에어코리아 공공데이터를 MCP 도구로 제공하고, 매일 아침 AI 브리핑을 카카오톡으로 보내는 **개인용 AI 날씨 비서**입니다.

## 핵심 설계 원칙

AI가 날씨를 "그럴듯하게" 말하는 것이 아니라, **실제 데이터만 근거로 말하게** 만드는 데 집중했습니다.

| 원칙 | 구현 |
|---|---|
| 수치는 코드가 고정 | LLM이 만든 문장에서 데이터에 없는 숫자를 검사 |
| 모르는 것은 모른다고 표시 | 특보 조회 기능이 없으므로 `warnings: []`를 "특보 없음"으로 읽지 않음. 원격 응답에는 `special_weather_report: "not_provided"` 부여 |
| 잘못된 브리핑은 보내지 않음 | 오류 브리핑은 카카오톡 발송 차단, 모호한 지역("중구")은 추측하지 않고 후보 안내 |
| 같은 날 중복 발송 금지 | 발송 이력(날짜+지역+채널) 기반 `claim_send`, 실패 시에만 재시도 |
| 기준 시각·출처 표시 | 모든 응답에 `source`, 관측·예보 시각 포함 |

## 아키텍처

```text
Claude 커넥터 ──► remote_server.py ──┐
                                      ├─► tool_output.py(응답 가공) ─► services ─► 기상청 / 에어코리아
카카오톡 ◄── run_daily.py ───────────┘                                   │
        ▲                                                                └─► Neon PostgreSQL (발송 이력·암호화 토큰)
        └── GitHub Actions ◄── cron-job.org (매일 07:07 KST, workflow_dispatch)
```

## 기능

**MCP 도구 (로컬 8개 / 원격 읽기 전용 6개)**

| 도구 | 설명 |
|---|---|
| `search_location` | 전국 지역 검색 (카카오 로컬 API, 모호하면 후보 안내) |
| `get_weather` | 현재 날씨 + 오늘 최저·최고, 강수확률 |
| `get_hourly_forecast` | 날짜·시간 범위별 시간대 예보 |
| `get_air_quality` | PM10·PM2.5 (근접 측정소) |
| `get_uv_index` | 자외선지수 |
| `recommend_activity` | 러닝·산책·퇴근길·빨래 판정과 근거 |
| `get_briefing`, `send_briefing_to_kakao` | AI 브리핑 생성·발송 (로컬 전용) |

**자동 브리핑**: 매일 07:07(KST) 카카오톡 "나에게 보내기"

## 기술 스택

Python 3.14 · MCP(FastMCP) · httpx · Gemini · Neon PostgreSQL · GitHub Actions · Render · cron-job.org · 카카오 API · pytest

## 설치와 실행 (Windows)

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy weather_mcp\.env.example weather_mcp\.env
```

`weather_mcp\.env`에 값을 채웁니다. 이 파일은 `.gitignore`로 제외되어 저장소에 올라가지 않습니다.

### 환경변수

| 이름 | 용도 | 필요한 경우 |
|---|---|---|
| `DATA_GO_KR_API_KEY` | 기상청·에어코리아 공공데이터포털 키 (공용) | 필수 |
| `KAKAO_REST_API_KEY` | 카카오 로컬 API(지역 검색), 카카오 로그인 | 필수 |
| `KAKAO_CLIENT_SECRET` | 카카오 토큰 발급·갱신 | 카카오톡 발송 시 |
| `GEMINI_API_KEY` | AI 브리핑 문장 생성 | 브리핑 생성 시 |
| `DAILY_LOCATION` | 매일 브리핑을 받을 지역 | 자동 발송 시 |
| `DATABASE_URL` | 발송 이력·토큰을 저장할 PostgreSQL | 외부 저장소 사용 시 |
| `TOKEN_ENCRYPTION_KEY` | 카카오 토큰 암호화 키 | 외부 저장소 사용 시 |
| `USE_EXTERNAL_STORE` | `1`이면 이력·토큰을 PostgreSQL에 저장 (GitHub Actions용) | 클라우드 실행 시 |
| `REMOTE_API_KEY` | 원격 MCP 서버 접근 키 (32자 이상) | 원격 서버 실행 시 |

로컬 개발에서는 `USE_EXTERNAL_STORE`를 비워 두면 SQLite·토큰 파일을 사용합니다.
원격 접근 키 생성: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### 실행과 테스트

```
:: MCP Inspector로 확인
npx @modelcontextprotocol/inspector python -m weather_mcp.server

:: 테스트
python -m pytest weather_mcp/tests
```

## 테스트

pytest 417개 통과(1개 건너뜀), push마다 GitHub Actions에서 자동 실행됩니다. 외부 API와 카카오 호출은 테스트에서 차단·가짜로 대체합니다.

## 사용 범위와 주의

- 개인용으로 설계했고 로그인·다중 사용자는 지원하지 않습니다.
- API 키, 카카오 토큰, 원격 커넥터 URL의 `?key=`는 저장소·채팅·스크린샷에 올리지 않습니다.
- 지역은 구 단위로 입력해야 정확합니다 ("서울"처럼 시 단위는 대표 좌표를 씁니다).

## 개발 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| 1~2 | MCP 서버, 기상청·에어코리아 연동 | 완료 |
| 3 | Gemini 브리핑, 숫자 검증 | 완료 |
| 4 | 카카오톡 발송, 토큰 갱신 | 완료 |
| 5 | 자동 발송, 이력·중복 방지, 원격 MCP 배포 | 완료 |
| 확장 | FastAPI 읽기 전용 API, Next.js 대시보드, 웹 채팅 | 진행 예정 |

## 스크린샷

(대시보드 완성 후 추가)