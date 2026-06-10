---
description: Phase v4-5 — 첫 세션 대화형 체력검증 (자가보고 → 기준선 저장) (028)
---
`docs/agent-tasks/v4/phase-5-first-session-assessment.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(028, 025, 024, 013)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: v3(master 동결)와 충돌 시 ADR-021 에 따라 v4 결정이 우선. 진실 소스 = `docs/future/v4-vision.md` §0-2 + 각 ADR.
- 자가보고 기반(실측 세트 X), 보수적 시작. 단발 `propose_set` → 대화형 plan-building tool-use 로 확장. baseline 은 phase 2 가 깐 `fitness_baseline` 1층에 저장.
- `CLAUDE.md` §4 폴더 구조 고정, §6 외부 호출 정책, §8 의존성 추가 시 사용자 확인 필수.
- 끝나면 `CLAUDE.md` §9 보고 형식 + `docs/conventions/code-review-checklist.md` 자가 점검 결과 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
