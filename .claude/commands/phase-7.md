---
description: Phase 7 — UI 재배선 (Pipecat WS 포맷) + 4모드 토글 + PRD §7-1 검증
---
`docs/agent-tasks/phase-7-ui-validation.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(010, 019)만 읽어라.
- v1 ui/* 코드 거의 그대로 — WS 메시지 포맷만 Pipecat에 맞게 조정.
- 마이크 캡처 = 16kHz mono 강제 (ADR-005 정합).
- Service Worker는 자산 캐시만, `/api/*`·`/ws/*` 캐시 금지.
- 데스크탑 패키징 시도 금지 (ADR-010 — pywebview/PyInstaller/Electron/Tauri 모두 X).
- 자동 검증 9종(PRD §7-1) 통과 + `docs/qa-checklist-v4.md` 작성.
- 끝나면 `CLAUDE.md` §9 보고 + 4모드 라운드트립 통합 테스트 + `scripts/dev.bat` 동작 확인.
- 사용자 수동 청취 검증은 사용자가 직접 — 자동화 어려운 부분 보고에 명시.
- 모호하면 멈추고 사용자에게 물어라.
