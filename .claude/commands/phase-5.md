---
description: Phase 5 — 능동 코치 (instructor + Pydantic + Action Dispatcher + 응답 길이 70/120)
---
`docs/agent-tasks/phase-5-active-coach.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(013, 012)만 읽어라.
- ADR-013 §0 핵심 원칙 = **코치 항상 능동 주도**. ACTIVE_COACH_PROTOCOL에 5개 항목 모두 명시 (능동 주도 / 응답 스키마 / 응답 길이 / 캘린더 활용 / 수용 정책).
- 응답 길이 = 능동 인사 70자, 능동 제안 120자, 일반 500자, 안전 150자, 카운팅 5~15자.
- 캘린더 데이터(주간 패턴·마지막 운동·휴식 streak)는 phase-8에서 보강 — phase-5 시점엔 hook만 비워둠.
- 안전 처리 = 홈트 간소화 (119 자동 호출 X, ADR-013 §면책·안전).
- instructor `max_retries=2`, `mode=instructor.Mode.JSON`.
- 끝나면 `CLAUDE.md` §9 보고 + 능동 인사 LLM 호출 응답 길이 검증 + 부상 키워드 SafetyGuardProcessor 인터셉트 검증.
- 프롬프트 튜닝 시 LLM이 일관되게 70/120 지키지 못하면 멈추고 사용자에게 물어라.
