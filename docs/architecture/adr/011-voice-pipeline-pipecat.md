# ADR-011: 음성 파이프라인 — Pipecat 전면 채택

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-005 (STT), ADR-006 (TTS), ADR-007 (VAD/Turn), ADR-009 (transport), ADR-012 (어댑터 계약), ADR-013 (능동 코치)

## 컨텍스트

v1은 자체 음성 파이프라인을 작성했다 — FastAPI WebSocket `/ws/coach`에서 audio chunk를 받아 silero VAD로 utterance 검출, faster-whisper STT, OllamaAdapter, Qwen3-TTS 어댑터를 순차 호출. 인터럽트는 `listen_start`/`audio_chunk`/`listen_stop` 메시지로 절반-듀플렉스 처리.

이 구조의 한계:
- **인터럽트가 견고하지 않음** — TTS 합성 도중 새 발화 감지 시 audio buffer flush·context 갱신을 직접 짜야 함, edge case 많음
- **Turn 검출이 silence 기반** — hesitation을 사용자 끝났다고 오인
- **TTS·LLM·STT가 직렬 처리** — TTS 합성 중 다음 turn 준비 병렬화 안 됨
- **검증된 패턴 부재** — audio frame race condition, sentence aggregation, sample rate 변환 등 모두 자체 구현 필요

오픈소스 후보(v3 사전 조사):

| 후보 | 강점 | 약점 |
|---|---|---|
| **Pipecat** | 30+ STT/25+ LLM/30+ TTS 어댑터, frame DAG, broadcast_interruption, Smart Turn, ParallelPipeline, FastAPI WebSocket transport | 0.x 단계 breaking change 빈번, WebSocket은 telephony 위주 |
| LiveKit Agents | WebRTC 강점, SFU 운영 자동화 | 단일 사용자엔 over-engineering, WebRTC SFU 의존 |
| RealtimeSTT/RealtimeTTS | 가볍고 단순 | 인터럽트·turn 검출 직접 구현, 어댑터 통합 비표준 |
| NeMo / ESPnet | 학술 중심, 모델 풍부 | 파이프라인 오케스트레이션 직접 구현 |

**원칙 — "바퀴 재발명 금지"** 에 따라 검증된 프레임워크를 채택. Pipecat이 우리 요구 (로컬 LLM Ollama + faster-whisper + custom Qwen3-TTS + FastAPI WebSocket + 단일 사용자)에 가장 잘 맞고, 인터럽트·turn 검출·sentence aggregation 같은 어려운 부분을 외주 가능.

## 결정

### 음성 파이프라인 = Pipecat 전면 채택

- **버전 핀**: `pipecat-ai >= 1.3.0` (1.x 안정 단계 진입 — 0.x 시절 대비 API breaking 위험 크게 감소. minor 업그레이드는 release notes 확인 후 진행, 메이저 업그레이드는 별도 ADR)
- v1의 자체 `/ws/coach` 핸들러 폐기 → `/ws/voice` Pipecat 파이프라인 마운트

### 파이프라인 구조

```
[WebSocket Input]
       ↓
[SileroVADAnalyzer]                    ← 사용자 발화 감지
       ↓ (UserStartedSpeakingFrame)
[WhisperSTTService]                    ← 16kHz 강제, 한국어
       ↓ (TranscriptionFrame)
[SafetyGuardProcessor]                 ← 우리 도메인 (ADR-012)
       ↓ (TranscriptionFrame 또는 InterruptFrame)
[ConfirmRuleProcessor]                 ← 능동 코치 확답 룰 (ADR-013)
       ↓
[ContextAggregator → LLMContextFrame]
       ↓
[OllamaLLMService + instructor]        ← JSON 구조화 출력
       ↓ (LLMResponseFrame: text + actions)
[ActionDispatcherProcessor]            ← actions 디스패치 (ADR-013/014)
       ↓ (TextFrame)
[SentenceAggregator]                   ← 문장 단위 분할
       ↓
[Qwen3TTSService]                      ← SDPA + streaming (ADR-006)
       ↓ (TTSAudioRawFrame)
[WebSocket Output]
```

### 인터럽트 정책

- `PipelineParams(allow_interruptions=True)` — 기본 활성
- 사용자 발화 감지 즉시 `broadcast_interruption()` — TTS·LLM 모두 중단
- 카운팅 엔진(ADR-014)은 별도 task로 분리 — Pipecat 파이프라인과 독립

### Smart Turn 정책

- 1단계: silero VAD silence만 사용
- 2단계: `SmartTurnAnalyzer` 추가 (ADR-007 점진 도입)

### 우리 도메인 컴포넌트의 Pipecat 통합

| 도메인 컴포넌트 | Pipecat 통합 방식 |
|---|---|
| SafetyGuard (부상 키워드 인터셉터) | `FrameProcessor` 상속, TranscriptionFrame 가로채기 |
| ConfirmRule (능동 코치 확답) | `FrameProcessor`, _pending_proposal 슬롯 유지 |
| ActionDispatcher (start_counting 등) | `FrameProcessor`, LLM 응답 후 actions 처리 |
| CountingEngine | Pipecat **밖**의 별도 asyncio task — TTS Service에 frame inject |
| SessionOrchestrator | Pipecat lifecycle 이벤트 핸들러 (`@transport.event_handler`) |

### 4-모드 구현

세션 시작 시 mode에 따라 파이프라인 조립 시점에 STT/TTS 노드를 빼거나 noop으로 대체:

| 모드 | STT 노드 | TTS 노드 |
|---|---|---|
| S2S | WhisperSTTService | Qwen3TTSService |
| C2S | (frontend가 text frame 직접 inject) | Qwen3TTSService |
| C2C | (text inject) | TextOutputProcessor (TTS 생략) |
| S2C | WhisperSTTService | TextOutputProcessor |

## 결과

### 긍정
- **인터럽트·sentence aggregation·turn 검출·VAD 통합·frame race condition** 모두 외주 — v1 자체 구현 부담 폭감
- 30+ 어댑터 풀에서 모델 교체 자유 (예: STT를 Deepgram으로 잠깐 비교해보기 등)
- ParallelPipeline로 TTS·LLM 병렬화 패턴 그대로 적용 가능 (PRD 지연 추가 단축)
- Smart Turn 같은 검증된 ML 기반 turn 검출 즉시 활용
- 커뮤니티 활발 — 문서·예제 풍부, 인터럽트 edge case가 이미 처리됨

### 부정
- **Pipecat 1.x 안정 단계**이지만 메이저 업그레이드(2.x) 시 breaking change 가능 — 메이저 업그레이드 정책은 별도 ADR로 명세
- **v1 자체 파이프라인 코드 대부분 폐기** — `app/api/ws_coach.py`, `app/core/orchestrator.py` 일부, 어댑터 Protocol(ADR-010 v1) 전부 재작성
- **FastAPIWebsocketTransport는 telephony 위주** — 일반 PWA 사용 사례 문서·예제 적음, 직접 시행착오 필요
- **Qwen3-TTS 공식 어댑터 없음** → 우리가 `TTSService` 상속한 어댑터 작성(ADR-006/012)
- **Pipecat 자체가 추가 의존성** — pip 패키지 무게, 학습 곡선
- **GPU 메모리 예산 변화 없음** — Pipecat은 모델을 직접 로드 안 함, 어댑터 안에 우리 모델 그대로

## 대안

| 후보 | 탈락 사유 |
|---|---|
| LiveKit Agents | WebRTC SFU 의존 — 단일 사용자엔 over-engineering, 운영 복잡 |
| RealtimeSTT + RealtimeTTS | 가볍지만 인터럽트·turn 검출 직접 구현 — Pipecat 채택 동기 무화 |
| NeMo / ESPnet | 모델 라이브러리 — 파이프라인 오케스트레이션 직접 구현 |
| TEN Framework | 신생, 한국 커뮤니티 자료 거의 없음 |
| 직접 작성 유지 (v1) | "바퀴 재발명 금지" 원칙 위배, 인터럽트 견고성 직접 책임 |
| Pipecat 부분 채택 (파이프라인만 + 카운팅 등은 자체) | ✅ 사실상 채택 — 도메인 로직(SafetyGuard·CountingEngine·SessionOrchestrator)은 우리가 유지, 음성 파이프라인만 Pipecat. ADR-012가 이 경계를 명세 |

## 마이그레이션 (v1 base → v3)

1. `pipecat-ai`, `pipecat-ai-flows` (필요 시) uv 추가
2. `app/api/ws_coach.py` 폐기 → `app/api/ws_voice.py`에 Pipecat 파이프라인 마운트
3. `app/adapters/{llm,stt,tts}/` 의 자체 Protocol 폐기 → Pipecat `Service` 상속 클래스로 재작성 (ADR-012)
4. `app/core/orchestrator.py`의 audio chunk·VAD·sentence 처리 코드 폐기 → Pipecat 파이프라인이 처리
5. `app/core/{safety, intent, counting}.py`는 도메인 로직으로 유지 → `FrameProcessor` 어댑터로 감싸 Pipecat에 등록
6. UI(`useAudio`)는 16kHz mono WebSocket 송수신 변경 (Pipecat WebSocket frame 포맷에 맞춤)

## 후속 검토

- Pipecat 메이저 버전(2.x) 업그레이드 정책 (별도 ADR)
- **WebRTC 도입은 헬스장 폰 시나리오(P1)에 한정** — 데스크탑 단일 사용자 환경에서는 WebSocket 유지가 원칙. WebRTC 전환은 Tailscale + 폰 PWA 검토 시점에 별도 ADR
- ParallelPipeline로 LLM·TTS 병렬화 적용 시점 (검증 후)

## References
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)
- [Pipecat Pipeline & Frame Processing](https://docs.pipecat.ai/guides/learn/pipeline)
- [Pipecat FastAPIWebsocketTransport](https://docs.pipecat.ai/server/services/transport/fastapi-websocket)
- [On-Premise Voice AI: Local Agents with Llama, Ollama, and Pipecat](https://webrtc.ventures/2025/03/on-premise-voice-ai-creating-local-agents-with-llama-ollama-and-pipecat/)
- [One-Second Voice-to-Voice Latency with Modal, Pipecat, and Open Models](https://modal.com/blog/low-latency-voice-bot)
- [LiveKit vs Pipecat 비교](https://sellerity.co/blog/livekit-pipecat-web-voice-agents)
