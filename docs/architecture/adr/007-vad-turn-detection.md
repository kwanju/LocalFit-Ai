# ADR-007: VAD + Turn Detection — silero-vad + Pipecat Smart Turn

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-005 (STT), ADR-011 (Pipecat), ADR-014 (카운팅 인터럽트)

## 컨텍스트

v1은 silero-vad로 silence 기반 음성 활동 감지만 했다. 단점:
- "어... 그래서..." 같은 hesitation을 사용자 끝났다고 오인 → 코치가 끼어들기
- 침묵 임계값(예: 800ms)을 늘리면 자연스러운 대화 흐름 깨짐

Pipecat은 silero-vad 외에 **Smart Turn** — intonation 기반 ML turn 검출 모델 — 을 공식 지원한다. raw audio의 음높이·운율을 분석해 "사용자가 말을 끝내려는 의도"를 판별한다.

또한 PRD §3-1 P0 "운동 중 인터럽트"는 frame-level 양방향 InterruptionFrame 전파가 필요하다 — Pipecat 기본 제공.

## 결정

### VAD = silero-vad (Pipecat 내장)

- `pipecat.audio.vad.silero.SileroVADAnalyzer` 사용 (Pipecat의 silero 래퍼)
- 로컬 CPU 실행, 의존성 가벼움
- `confidence: 0.5`, `min_silence_duration_ms: 400` 기본 — 사용자 환경별 튜닝

### Turn Detection = Pipecat Smart Turn (점진 도입)

- 1단계 (MVP): silero VAD silence 기반만 사용 — v1 동작 유지
- 2단계 (검증 후): `pipecat.audio.turn.smart_turn.SmartTurnAnalyzer` 추가 — intonation 기반
- `config.vad.use_smart_turn: false` 기본, 사용자 검증 후 true 전환

### 인터럽트 정책

- 기본 활성 (`PipelineParams(allow_interruptions=True)`)
- 사용자 발화 감지 즉시 `InterruptionFrame` 양방향 전파 — TTS·LLM 모두 중단
- 카운팅 엔진(ADR-014)은 인터럽트와 **분리** — 카운팅은 LLM 응답과 무관하게 박자 유지 (PRD §4-1 "LLM 지연 중에도 카운팅 끊김 없이")

### config 예시

```yaml
vad:
  provider: "silero"
  silero:
    confidence: 0.5
    min_silence_duration_ms: 400
    sample_rate: 16000
  use_smart_turn: false        # 검증 후 true 전환
  smart_turn:
    threshold: 0.7
```

## 결과

### 긍정
- v1 silero 기반 유지로 회귀 위험 0
- Smart Turn은 옵션 — 검증 후 점진 활성화
- 인터럽트 처리는 Pipecat 기본 동작 — 자체 구현 부담 0
- 카운팅 박자는 인터럽트 영향 없음 — PRD 보존

### 부정
- Smart Turn 활성화 시 추가 ML 모델 로드 (~50MB) + CPU 추론
- 한국어 운율 학습 데이터 비율은 미공개 — 한국어 정확도 검증 필요

## 대안

| 후보 | 탈락 사유 |
|---|---|
| WebRTC VAD | silero보다 정확도 낮음 |
| Krisp VIVA VAD | 라이선스·비용 — 단일 사용자 환경 fit 안 됨 |
| Smart Turn만 단독 | 검증 부족 시점에 silero 폴백 필요 |

## References
- [silero-vad](https://github.com/snakers4/silero-vad)
- [Pipecat Smart Turn](https://docs.pipecat.ai/server/utilities/smart-turn/smart-turn-overview)
- [Pipecat Speech Input & Turn Detection](https://docs.pipecat.ai/guides/learn/speech-input)
