---
description: Phase v4-6 — Tauri 셸 통합 (런타임 교체) + S-4 마이크 fix (031)
---
`docs/agent-tasks/v4/phase-6-tauri-shell.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(031, 009, 011, 005)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: ADR-031 채택으로 Tauri 데스크탑은 예외 허용(010 Superseded). 단 pywebview/PyInstaller/Electron 은 여전히 금지.
- 탐사 산출물(`ui/src-tauri/**`, spike-result §5 런북) 제품화. Pipecat WS(`/ws/voice`) 무변경. STT 16kHz 강제(마이크 sampleRate 정합).
- ⚠️ S-4 마이크 입력(webview2 getUserMedia)은 탐사 유일 미검증·최대 리스크 — 집 환경에서 반드시 통과시켜야 S2S 모드가 산다. FAIL 시 차선책 보고.
- `CLAUDE.md` §4 폴더 구조 고정, §6 외부 호출 정책, §8 의존성 추가 시 사용자 확인 필수.
- 끝나면 `CLAUDE.md` §9 보고 형식 + `docs/conventions/code-review-checklist.md` 자가 점검 결과 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
