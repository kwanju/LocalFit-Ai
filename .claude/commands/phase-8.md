---
description: Phase v4-8 — 능동 알림 + 백그라운드 스케줄러 (트레이 toast → 세션) (027)
---
`docs/agent-tasks/v4/phase-8-active-notifications.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(027, 021, 030, 022)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: 트레이 상주 경량 스케줄러(모델 없음) + native toast(운동시간/체크인) + 클릭→앱 포커스→세션 시작(모델 로드는 phase 7 시점). 음소거 시간대 존중.
- 상시 가동/선제 발화 아님(ADR-021 세션 모델 유지). 스케줄 소스 = 플랜(phase 4)/캘린더(phase 9), 미연동 시 로컬 fallback.
- 의존: phase 6(트레이) + phase 4(스케줄 소스). `CLAUDE.md` §4 폴더 구조 고정, §6 외부 호출 정책, §8 의존성 추가 시 사용자 확인 필수.
- 끝나면 `CLAUDE.md` §9 보고 형식 + `docs/conventions/code-review-checklist.md` 자가 점검 결과 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
