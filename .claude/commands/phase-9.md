---
description: Phase v4-9 — Google Calendar 연동 (OAuth2 Desktop, 등록 확인 게이트) (022)
---
`docs/agent-tasks/v4/phase-9-google-calendar.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(022, 027, 021, 002, 013)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: 로컬-only(ADR-002)는 **캘린더에 한해 완화**(ADR-021). 본인 계정 1개, 멀티계정·`user_id` 분기 금지.
- OAuth2 Desktop client + 토큰 안전저장. 운동 일정 등록은 확답 게이트(자동 등록 금지). 기존 `app/api/calendar.py`(로컬 히트맵)와 이름 충돌 → 신규 gcal 네임스페이스 분리.
- 신규 의존성(google-api-python-client·google-auth-oauthlib)은 사용자 승인 후 추가(§8).
- `CLAUDE.md` §4 폴더 구조 고정, §6 외부 호출 정책. 끝나면 §9 보고 형식 + code-review-checklist 자가 점검 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
