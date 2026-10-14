# weather-briefing

날씨/대기질 AI 브리핑 MCP 프로젝트

## 실행 환경 (Windows)
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## MCP Inspector 테스트
```bat
npx @modelcontextprotocol/inspector python -m weather_mcp.server
```

## 진행 단계
- [x] 1단계: MCP 서버 기초 (mock 데이터)
- [ ] 2단계: 공공 API 통합
- [ ] 3단계: AI 브리핑
- [ ] 4단계: 카카오톡 연동
- [ ] 5단계: 운영 환경