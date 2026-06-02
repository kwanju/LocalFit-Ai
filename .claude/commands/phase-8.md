---
description: Phase 8 — 운동 캘린더 (react-activity-calendar) + 코치 컨텍스트 강화
---
`docs/agent-tasks/phase-8-workout-calendar.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(020, 013, 008, 012)만 읽어라.
- ADR-020이 본 phase의 단일 진실 소스. 라이브러리 = `react-activity-calendar` (pnpm add).
- 강도 산정 식 = volume 기반 level 0~4 (ADR-020 §"강도 산정 식").
- `app/core/calendar_metrics.py` 신규 — 순수 함수만 (4계층 분리, ADR-012).
- `GET /api/calendar?from=...&to=...` 신규.
- `CoachContextBuilder.build()`에 주간 패턴·마지막 운동·휴식 streak inject (ADR-013 §컨텍스트 빌더 + ADR-020 §능동 코치 컨텍스트 강화).
- 빈 DB 상태 빈 상태 UI + 1주일 strip 뷰 fallback.
- 끝나면 `CLAUDE.md` §9 보고 + 캘린더 화면 동작 + 능동 코치가 캘린더 패턴 언급 (수동 검증 5회 중 3회 이상).
- 모호하면 멈추고 사용자에게 물어라.
