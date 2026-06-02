---
description: Phase 6 — 카운팅 트리거 + 박자 멘트 풀 + 완료 자동 follow-up + 인터럽트
---
`docs/agent-tasks/phase-6-counting.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(014, 011, 013)만 읽어라.
- v1 `app/core/counting.py` 재활용 — 박자 정확도 ±10% 회귀 위험 0.
- `app/core/counting_cues.py` 신규 — ADR-014 §"박자 멘트 풀" 표대로 운동·구간별 cue 풀 + 진행 격려 멘트 풀.
- 카운팅 완료 → SetLog 기록 + **자동 follow-up LLM 호출** (능동 주도 원칙, ADR-013 §0).
- 박자는 LLM 응답 TTS 완료 후 (응답 뒤 박자, `start_delay_sec`).
- 박자·LLM 응답 충돌은 phase-6 실제 frame 흐름 보며 검증.
- 끝나면 `CLAUDE.md` §9 보고 + 박자 정확도 + 멘트 다양화 + follow-up 동작 검증.
- 모호하면 멈추고 사용자에게 물어라.
