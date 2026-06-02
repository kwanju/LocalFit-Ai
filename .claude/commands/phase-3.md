---
description: Phase 3 — TTS Qwen3-TTS + SDPA + sentence-streaming (첫 청크 <500ms 목표)
---
`docs/agent-tasks/phase-3-tts.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(006, 012, 018)만 읽어라.
- ADR-006이 본 phase의 단일 진실 소스. 핵심 = `attn_implementation="sdpa"` + `device_map="cuda:0"` + `torch_dtype=torch.bfloat16` + sentence-streaming.
- MeloTTS fallback 어댑터는 미리 작성하지 마라 (YAGNI, ADR-006).
- 보이스 클로닝 유지 (Base 모델), `data/ref_voice.wav` 재사용.
- 첫 청크 지연 측정 + 로그 기록 (`latency.tts.first_chunk`).
- 끝나면 `CLAUDE.md` §9 보고 + Qwen3-TTS 합성 결과 5회 평균 첫 청크 시간 보고.
- <500ms 목표 미달 시 사용자 보고 + 별도 ADR 제안 (대체 모델 비교).
- transformers 모델 카드의 streaming generator API 확인 시 모호하면 멈추고 사용자에게 물어라.
