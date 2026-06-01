# Phase 3 — TTS: Qwen3-TTS + SDPA + sentence-streaming

## 목적

v1의 50초 지연을 해결한다. Qwen3-TTS를 SDPA 어텐션으로 로드하고 sentence-streaming을 활성화하여 **첫 청크 < 500ms** 목표 달성.

## 사전 조건

- Phase 2 완료 (mock TTS로 라운드트립 동작 중)
- `data/ref_voice.wav` 존재 (6초 이상 한국어 단일 화자)
- RTX 5090 + cu128 + transformers 4.45+ 환경

## 관련 ADR

- ADR-006 (TTS Qwen3-TTS + SDPA + streaming) — **본 phase의 단일 진실 소스**
- ADR-012 (Service 작성 패턴)
- ADR-018 (지연 메트릭)

## 작업 항목

### 3-1. Qwen3TTSClient (Domain Adapter)

- `app/adapters/tts/qwen3_client.py` 작성
- `transformers.AutoModel.from_pretrained(model, attn_implementation="sdpa", device_map="cuda:0", torch_dtype=torch.bfloat16)`
- `__init__` 시 `get_conditioning_latents(ref_audio_path)` 호출 → `(speaker_embedding, conditioning_latent)` 캐시
- `async def stream(text: str) -> AsyncIterator[bytes]` — generator로 PCM 청크 yield
- `async def synthesize(text: str) -> bytes` — 단일 호출 (스트리밍 없이 합본 WAV bytes)
- 16-bit PCM mono 24kHz 출력

### 3-2. Qwen3TTSService (Pipecat 통합)

- `app/pipecat_services/qwen3_tts_service.py` 작성
- `pipecat.services.tts.base.TTSService` 상속
- `async def run_tts(self, text: str)` 안에서 `client.stream(text)` 호출 → `TTSAudioRawFrame` yield
- `sample_rate=24000`, `num_channels=1`

### 3-3. SentenceAggregator 통합

- Pipecat의 `SentenceAggregator`를 LLM과 TTS 사이에 배치 (또는 기본 내장 활용)
- 첫 sentence 도달 즉시 TTS 시작 — 다음 sentence는 백그라운드 합성

### 3-4. 지연 메트릭

- `app/utils/latency.py`에 `LatencyTracker` 컨텍스트 매니저 (ADR-018)
- `Qwen3TTSService.run_tts` 진입과 첫 청크 yield 시점 측정 → `tts.first_chunk={ms}` 로그

### 3-5. 파이프라인 빌더 갱신

- Phase 2의 mock TTS를 `Qwen3TTSService`로 교체 (활성 옵션)
- C2S/S2S 모드에서만 TTS 노드 활성, C2C/S2C는 noop

### 3-6. 테스트

- `tests/test_qwen3_client.py` — gpu mark, 짧은 텍스트 합성 + 첫 청크 시간 측정
- `tests/test_qwen3_service.py` — mock client 주입한 frame 변환 테스트 (비-GPU)
- `tests/test_ws_voice_tts.py` — S2S 모드 라운드트립에서 실제 audio frame 도착 확인

## Definition of Done

- [ ] `Qwen3TTSClient` 로드 시 GPU 메모리 ~3.5GB 점유 확인
- [ ] 짧은 한국어 문장("안녕하세요, 운동 시작할까요?") 첫 청크 **< 500ms** 측정 (5회 평균)
- [ ] sentence-streaming으로 4문장 응답 합성 시 첫 청크 < 700ms
- [ ] S2S 모드 ws_voice 라운드트립에서 24kHz mono PCM frame 도착
- [ ] 지연 메트릭 로그 (`latency.tts.first_chunk=...`) 기록
- [ ] ruff + pytest (비-GPU) 통과 + gpu mark 테스트 수동 실행 통과
- [ ] git commit `feat(phase-3): TTS Qwen3-TTS + SDPA + sentence-streaming`

## 리스크

- **첫 청크 < 500ms 미달성 시**: 사용자 보고 → Qwen3-TTS 설정 추가 튜닝(`torch.compile`, batch size, dtype 변경 등) 시도. 그래도 미달이면 별도 ADR로 대체 모델 비교·결정 (MVP 시점에 fallback 어댑터 미리 작성 안 함 — YAGNI)
- transformers `AutoModel` + Qwen3-TTS 모델 카드의 streaming generator API가 실제 어떻게 노출되는지는 모델 카드 코드 직접 확인 필요. 막히면 모델 카드의 `inference_stream` 예제 그대로 따라가기
- bfloat16 미지원 layer 발견 시 float16으로 폴백 (config 한 줄)

## 소요 추정

2~3일 (모델 카드 코드 + SDPA 설정 + streaming 검증).

## 다음 phase

[Phase 4 — STT + VAD](phase-4-stt-vad.md)
