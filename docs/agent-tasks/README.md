# Agent Tasks — v3-rewrite

v1 base에서 출발해 19개 ADR과 PRD v4를 구현하기 위한 phase 작업 명세. 각 phase는 명확한 인수 조건(Definition of Done)을 가진다.

v1 시점 phase 0~6은 `_archive/v1/`에 보존(참고용). v3는 phase 1~7 신규.

## Phase 인덱스

| # | Phase | 핵심 산출물 | 관련 ADR |
|---|---|---|---|
| 1 | [v1 base 정리 + 의존성 추가](phase-1-base-prep.md) | v2 산출물 없는 깨끗한 base 확인, pipecat-ai · instructor · loguru 의존성 추가, 폴더 구조(ADR-012) 재배치, v1 자체 Protocol 폐기 | 012, 017 |
| 2 | [Pipecat 셸 + 음성 WS 마운트](phase-2-pipecat-shell.md) | `/ws/voice` Pipecat 파이프라인 마운트 (mock STT/LLM/TTS로 라운드트립), FastAPI lifespan 통합 | 009, 011 |
| 3 | [TTS — Qwen3-TTS + SDPA + streaming](phase-3-tts.md) | `Qwen3TTSClient` (transformers + SDPA) + `Qwen3TTSService` (Pipecat) + sentence-streaming + 첫 청크 < 500ms 측정 | 006, 012, 018 |
| 4 | [STT + VAD — Pipecat 통합](phase-4-stt-vad.md) | `WhisperSTTService` (16kHz 강제) + `SileroVADAnalyzer` 통합, 4-모드 토글 | 005, 007, 011 |
| 5 | [능동 코치 — instructor + Action Dispatcher](phase-5-active-coach.md) | `StructuredOllamaService` (instructor + Pydantic) + `CoachContextBuilder` + `SafetyGuardProcessor` + `ConfirmRuleProcessor` + `ActionDispatcherProcessor` + 능동 인사 | 013, 012 |
| 6 | [카운팅 트리거 + 인터럽트](phase-6-counting.md) | v1 `CountingEngine` 재활용 + `CountingInjectProcessor` + `StartCountingAction` 디스패치 결합 + 인터럽트 검증 | 014, 011 |
| 7 | [UI 재배선 + 검증](phase-7-ui-validation.md) | `useAudio` WS 메시지 포맷을 Pipecat에 맞춤, 4-모드 토글, PRD §7-1 자동 검증 + 수동 청취 체크리스트 | 010, 019 |
| 8 | [운동 캘린더 + 코치 컨텍스트 강화](phase-8-workout-calendar.md) | `/api/calendar` 신규, react-activity-calendar 히트맵 UI, `CoachContextBuilder`에 주간 패턴·미수행 알림 inject | 020, 013 |

## 작업 순서 가이드

- 각 phase는 **앞 phase의 인수 조건이 통과**된 뒤 진입.
- phase 1·2는 인프라 셋업이라 빠르게(반나절~1일).
- phase 3 (TTS SDPA 검증)이 **가장 큰 리스크 게이트** — 첫 청크 < 500ms가 안 나오면 MeloTTS fallback 또는 다른 모델 ADR 재검토.
- phase 5·6은 능동 코치 + 카운팅으로 사용자가 가장 자주 만질 영역. 시간 여유 두고 진행.
- phase 7 UI는 비교적 적은 변경 (WS 메시지 포맷만). 검증이 본체.
- phase 8은 phase 7과 독립 작업 — 음성 파이프라인 안정화 후 별도로 진입. 백엔드(API + 강도 산정) + UI(캘린더 컴포넌트) + 코치 컨텍스트 강화로 분리되어 점진 머지 가능.

## 산출물 공통 요구

- ruff + pyright 통과
- pytest 비-GPU 스위트 통과
- 각 phase 종료 시 사용자에게 "작업 완료 보고" (CLAUDE.md §9 형식)
- 커밋 메시지: Conventional Commits + 한국어 본문

## v1 자산 재활용 매핑

CLAUDE.md §12 참조. phase별로 그대로 가져올 모듈과 폐기할 모듈이 미리 표로 정해져 있다.
