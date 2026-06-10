---
description: Phase v4-2 — 영속 메모리 (2층: 부상·제약 전량주입 + 자유텍스트) (025)
---
`docs/agent-tasks/v4/phase-2-persistent-memory.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(025, 008, 013, 002)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: v3(master 동결)와 충돌 시 ADR-021 에 따라 v4 결정이 우선. 진실 소스 = `docs/future/v4-vision.md` §0-2 + 각 ADR.
- `CLAUDE.md` §4 폴더 구조 고정(특히 `core/` 외부 import 0), §6 외부 호출 정책, §8 의존성 추가 시 사용자 확인 필수.
- ★ 핵심: `CoachContextBuilder` 확장 — 부상/제약은 cap(700자) 무관 전량 주입. cap 정책 재설계 필요. 안전 직결이라 손실 0 우선.
- 결정 포인트(2-1 테이블 vs JSON / 2-5 즉시저장 vs ConfirmRule)는 사용자에게 보고 후 진행.
- 끝나면 `CLAUDE.md` §9 보고 형식 + `docs/conventions/code-review-checklist.md` 자가 점검 결과 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
