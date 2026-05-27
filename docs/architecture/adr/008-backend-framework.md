# ADR-008: 백엔드 프레임워크로 FastAPI 채택

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-001 (Python), ADR-007 (SQLModel)

## 컨텍스트

백엔드는 다음을 제공해야 한다.

- REST 엔드포인트 (세션 시작/종료, 설정 CRUD)
- WebSocket (실시간 코칭·카운팅 이벤트 push)
- 비동기 처리 (STT/LLM/TTS 동시 실행)
- Python 3.11+ 타입 힌트 친화성

## 결정

**FastAPI**를 채택한다. WebSocket은 FastAPI 내장 지원 사용.

ASGI 서버: `uvicorn`. 단일 워커, 단일 사용자 기준.

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## 결과

### 긍정
- asyncio 네이티브 — Session Orchestrator의 동시 실행과 자연스럽게 결합
- Pydantic 기반 타입 검증 자동
- WebSocket과 REST를 한 앱에서 처리
- 자동 OpenAPI 문서 (`/docs`) — 단독 테스트 시 유용

### 부정
- ASGI 서버 별도 실행 — Windows 서비스화 시 약간 작업

## 대안

| 후보 | 탈락 사유 |
|---|---|
| Flask + Flask-SocketIO | 동기 기반, asyncio 통합 시 마찰 |
| Starlette 직접 사용 | FastAPI의 기반, 보일러플레이트 ↑ |
| Django + Channels | 오버킬 |
| aiohttp | 타입 시스템·OpenAPI 자동화 약함 |
