---
description: Phase 4 — STT (faster-whisper) + silero VAD Pipecat 통합 (16kHz 강제)
---
`docs/agent-tasks/phase-4-stt-vad.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(005, 007, 011)만 읽어라.
- **16kHz 강제 리샘플** — v1 known issue(32kHz 입력 시 transcript 어긋남) 재발 방지. ADR-005 §결정.
- 옵션 B 채택 (자체 `LocalFitWhisperSTTService`) — Pipecat 공식 WhisperSTTService 직접 사용하지 마라.
- Smart Turn은 활성화하지 마라 (P1, `use_smart_turn: false`).
- 끝나면 `CLAUDE.md` §9 보고 + 32kHz 리샘플 정합성 검증 + S2C 모드 라운드트립 통과 확인.
- 모호하면 멈추고 사용자에게 물어라.
