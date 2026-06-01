# Phase 4 — STT + VAD: Pipecat 통합

## 목적

faster-whisper STT와 silero VAD를 Pipecat 파이프라인에 통합한다. **16kHz 리샘플 강제**로 v1 known issue 해소. 4-모드(S2S/S2C) 음성 입력 정상화.

## 사전 조건

- Phase 3 완료 (TTS 동작 중)

## 관련 ADR

- ADR-005 (STT faster-whisper + 16kHz 강제)
- ADR-007 (VAD silero, Smart Turn은 P1)
- ADR-011 (Pipecat 통합)

## 작업 항목

### 4-1. FasterWhisperClient (Domain Adapter)

- `app/adapters/stt/faster_whisper_client.py` 재작성 (v1 자산 base)
- 진입부에서 입력 샘플레이트 != 16000이면 `librosa.resample(..., orig_sr=src, target_sr=16000)` 강제
- `async def transcribe(audio: bytes, sample_rate: int) -> str`
- `large-v3-turbo`, `cuda`, `float16`, `language="ko"`, `vad_filter=True`, `beam_size=1`

### 4-2. WhisperSTTService (Pipecat 통합)

- 두 가지 선택지:
  - (A) Pipecat `pipecat.services.whisper.stt.WhisperSTTService`를 직접 사용 (16kHz 정합성 확인 필요)
  - (B) `pipecat.services.stt.base.STTService` 상속한 자체 `LocalFitWhisperSTTService` 작성, 내부에서 `FasterWhisperClient.transcribe` 호출
- **권장 = B** (16kHz 강제 명시적, 어댑터 mock 가능)

### 4-3. SileroVADAnalyzer 통합

- `pipecat.audio.vad.silero.SileroVADAnalyzer` 사용
- config 파라미터: `confidence: 0.5`, `min_silence_duration_ms: 400`, `sample_rate: 16000`
- `FastAPIWebsocketTransport` 또는 파이프라인 input에 VAD analyzer 연결

### 4-4. 파이프라인 빌더 갱신

- Phase 2의 mock STT를 `LocalFitWhisperSTTService`로 교체
- S2S/S2C 모드에서만 STT + VAD 활성

### 4-5. 인터럽트 정책 검증

- 사용자 발화 감지 → TTS 진행 중인 frame 중단 (Pipecat broadcast_interruption 기본)
- 통합 테스트로 인터럽트 시나리오 확인

### 4-6. Smart Turn (옵션, P1 준비)

- `config.vad.use_smart_turn: false` 기본 (활성화 안 함)
- 구조만 준비: 활성화 시 `SmartTurnAnalyzer` 추가 (실제 활성은 P1)

### 4-7. 지연 메트릭

- `LatencyTracker("stt.transcribe")` — 발화 종료부터 transcript 완성까지 측정

### 4-8. 테스트

- `tests/test_faster_whisper_client.py` — gpu mark, 한국어 짧은 WAV transcribe
- `tests/test_faster_whisper_resample.py` — 32kHz WAV 입력 → 16kHz 리샘플 후 transcribe 정상
- `tests/test_whisper_service.py` — mock client 주입한 frame 변환
- `tests/test_ws_voice_stt.py` — S2C 모드 라운드트립으로 audio → transcript text 도착 확인

## Definition of Done

- [ ] 32kHz WAV 입력해도 transcript 어긋남 0 (v1 known issue 해소)
- [ ] S2C 모드 ws_voice 라운드트립에서 한국어 음성 → 텍스트 응답
- [ ] silero VAD 발화 종료 후 200~600ms 이내 STT 시작
- [ ] 인터럽트 통합 테스트 통과 (TTS 중 새 발화 감지 → TTS 중단)
- [ ] `latency.stt.transcribe` 로그 기록
- [ ] ruff + pytest (비-GPU) 통과 + gpu mark 테스트 수동 통과
- [ ] git commit `feat(phase-4): STT faster-whisper + silero VAD Pipecat 통합`

## 리스크

- Pipecat의 silero analyzer가 `FastAPIWebsocketTransport`와 정합성 — 검증 필요 (telephony 위주 transport)
- 16kHz 강제 리샘플로 인한 CPU 부담 (librosa) — 측정해서 5ms 이하 확인

## 소요 추정

1~2일.

## 다음 phase

[Phase 5 — 능동 코치](phase-5-active-coach.md)
