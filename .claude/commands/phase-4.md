---
description: Phase v4-4 — 운동 플랜 (주간 목표 + 일자 분배, 조정은 확인 게이트) (024)
---
`docs/agent-tasks/v4/phase-4-workout-plan.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(024, 013, 023, 025, 029)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: v3(master 동결)와 충돌 시 ADR-021 에 따라 v4 결정이 우선. 진실 소스 = `docs/future/v4-vision.md` §0-2 + 각 ADR.
- LLM 임의 조정 금지: 플랜 조정은 ConfirmRule 동의(확답 게이트) 후에만. tool-use 정확도는 9b 검증(phase 1 게이트)에 의존.
- `CLAUDE.md` §4 폴더 구조 고정, §6 외부 호출 정책, §8 의존성 추가 시 사용자 확인 필수.
- 끝나면 `CLAUDE.md` §9 보고 형식 + `docs/conventions/code-review-checklist.md` 자가 점검 결과 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
