# Phase 2 — Pipecat 셸 + 음성 WS 마운트

## 목적

Pipecat `FastAPIWebsocketTransport`를 `/ws/voice`에 마운트하고, **mock STT/LLM/TTS**로 4-모드 라운드트립이 동작하는 최소 셸을 만든다. 실제 모델 통합은 phase 3~5에서.

## 사전 조건

- Phase 1 완료 (의존성·폴더·로깅 갖춤)

## 관련 ADR

- ADR-009 (FastAPI + Pipecat WS transport)
- ADR-011 (Pipecat 파이프라인 구조)
- ADR-012 (Service 작성 패턴)

## 작업 항목

### 2-1. mock Pipecat services 작성

- `app/pipecat_services/mock_llm_service.py` — 입력 transcription을 echo로 응답 (`"echo: {text}"`)
- `app/pipecat_services/mock_stt_service.py` — 받은 audio frame을 고정 텍스트("테스트")로 변환
- `app/pipecat_services/mock_tts_service.py` — 받은 text를 무음 PCM frame으로 변환

각 클래스는 Pipecat `Service` 상속, frame in/out만 처리. 실제 모델 호출 X.

### 2-2. 파이프라인 빌더 작성

- `app/pipecat_services/pipeline_builder.py` — mode(`S2S`/`C2S`/`C2C`/`S2C`)에 따라 파이프라인 조립
- 노드 순서: `[input → VAD → STT → LLM → TTS → output]` (mode별 STT/TTS 노드는 noop 또는 생략)
- `PipelineParams(allow_interruptions=True)`

### 2-3. ws_voice 엔드포인트

- `app/api/ws_voice.py` 신규
- WebSocket 연결 수립 → query param 또는 첫 message로 mode 수신 → `pipeline_builder.build(mode)` → `PipelineRunner.run(pipeline)`
- 종료 시 graceful cancel

### 2-4. FastAPI 라우터 통합

- `app/main.py`에 `ws_voice` 라우터 등록
- 기존 `ws_coach`는 라우터에서 분리 (코드는 남겨두되 마운트 안 함)

### 2-5. health 갱신

- `/health` 응답에 `pipecat: true` (파이프라인 빌더가 정상 import되면)

### 2-6. 통합 테스트

- `tests/test_ws_voice_shell.py` — Pipecat MockTransport(또는 자체 WS client)로 4모드 라운드트립 확인
- C2C 모드: 텍스트 입력 → echo 응답 텍스트 수신
- S2S 모드: 무음 audio → "테스트" STT → "echo: 테스트" LLM → 무음 TTS frame 수신

## Definition of Done

- [ ] `uvicorn app.main:app` 정상 기동
- [ ] `/health` `pipecat: true`
- [ ] `ws://127.0.0.1:8000/ws/voice?mode=C2C`로 텍스트 라운드트립 동작
- [ ] mode 별 라운드트립 통합 테스트 4종 통과
- [ ] ruff + pytest 통과
- [ ] git commit `feat(phase-2): Pipecat 셸 + /ws/voice 마운트 (mock services)`

## 리스크

- Pipecat `FastAPIWebsocketTransport`는 telephony 위주 — 일반 PWA 사용 사례 문서 적음. WebSocket frame 포맷·serializer를 직접 확인할 가능성 큼. 막히면 `WebsocketServerTransport` 또는 자체 wrap 어댑터 검토.

## 소요 추정

1~2일.

## 다음 phase

[Phase 3 — TTS Qwen3-TTS + SDPA + streaming](phase-3-tts.md)
