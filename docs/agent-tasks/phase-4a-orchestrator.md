# Task: Phase 4A — Session Orchestrator

## 배경 자료
- `AGENTS.md`
- `docs/prd-v3.1.md` 2장 (4-모드), 4-1 (파이프라인)
- `docs/architecture/diagrams/` (세션 상태 머신, 4-모드 시퀀스)
- Phase 2 어댑터 + Phase 3 코어 (의존)

## 작업 범위
1. `app/core/state_machine.py` — 세션 라이프사이클 (dict 기반 상태 전이)
   - 상태: IDLE, CONDITION_CHECK, WARMUP, EXERCISING, REST, COOLDOWN, COMPLETED, PAUSED, ABORTED, INJURY_ALERT, SAFETY_CHECK, EMERGENCY_STOPPED, RECOVERED
2. `app/core/orchestrator.py` — SessionOrchestrator
   - 어댑터·코어 모듈 의존성 주입
   - 모드별 어댑터 체인 (S2S/C2S/C2C/S2C — on/off 조합)
   - INJURY_ALERT는 이벤트 인터셉터 (모든 입력 가로채기)
   - 인터럽트: cancelable Task로 LLM/TTS 중단
   - 카운팅 코루틴과 코칭 코루틴 병행
   - 세션 상태 DB 저장 (복원 대비)
3. `tests/integration/test_orchestrator.py` — Mock 어댑터로 4-모드 흐름 검증

## 제약
- core 순수성 유지 (FastAPI import 금지)
- 어댑터는 주입 (직접 생성 금지)
- 상태 전이마다 Session.status DB 업데이트
- P0 범위: S2S/C2C 우선, C2S/S2C는 후반 (PRD 우선순위)

## P0 단계적 구현
- 1차: IDLE/EXERCISING/PAUSED 3상태 + S2S/C2C
- 2차: 전체 상태 + 4모드 + INJURY 인터셉터

## 비범위
- API 노출 (Phase 4B)
- UI (Phase 5)

## 완료 기준
- Mock 어댑터로 모드별 라우팅 검증
- 부상 인터셉터 동작 (어느 상태든 차단)
- 인터럽트 시 LLM/TTS cancel, 카운팅 유지

## 자가 보고
AGENTS.md 9번. checklist 전 항목 (가장 복잡한 작업).
