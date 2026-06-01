# Task: Phase 4B — FastAPI 엔드포인트

## 배경 자료
- `AGENTS.md`
- `docs/architecture/adr/008-backend-framework.md`
- `docs/architecture/adr/014-process-lifecycle.md` (/health)
- `docs/architecture/adr/002-mvp-topology.md` (127.0.0.1)
- Phase 4A Orchestrator (의존)

## 작업 범위
1. `app/main.py` — FastAPI 앱, lifespan으로 모델 로딩, 127.0.0.1 바인딩
2. `app/api/health.py` — GET /health (어댑터별 health() 집계)
3. `app/api/session.py` — 세션 시작/종료/조회 (REST)
4. `app/api/routine.py` — 루틴 CRUD
5. `app/api/onboarding.py` — 온보딩 (PRD 부록 A 3단계)
6. `app/api/ws_coach.py` — WebSocket /ws/coach (실시간 양방향)
7. `tests/integration/test_api.py` — 주요 엔드포인트 1개씩

## 제약
- 모든 엔드포인트 async def
- Orchestrator를 dependency 주입
- 127.0.0.1 바인딩 (ADR-002)
- WebSocket 재연결 고려 (클라이언트는 Phase 5)
- 비즈니스 로직은 core로 위임 (api는 얇게)

## 완료 기준
- /health가 어댑터 상태 정확히 반환
- WebSocket으로 채팅 메시지 왕복 (C2C 흐름)
- uv run uvicorn app.main:app 실행 성공

## 자가 보고
AGENTS.md 9번. checklist A·D·F·G 확인.
