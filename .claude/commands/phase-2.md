---
description: Phase 2 — Pipecat 셸 + /ws/voice 마운트 (mock STT/LLM/TTS로 4-모드 라운드트립)
---
`docs/agent-tasks/phase-2-pipecat-shell.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(009, 011, 012)만 읽어라.
- `app/pipecat_services/` 신규 폴더에 mock services + pipeline builder + ws_voice 핸들러 작성.
- v1 자체 `/ws/coach` 핸들러는 마운트하지 않음 (코드는 archive 표시).
- mode 별 STT/TTS 노드 on/off 토글로 4모드 처리.
- 끝나면 mode 별 라운드트립 통합 테스트 + `CLAUDE.md` §9 보고 형식.
- Pipecat 1.x API와 명세가 어긋나면 멈추고 사용자에게 물어라.
