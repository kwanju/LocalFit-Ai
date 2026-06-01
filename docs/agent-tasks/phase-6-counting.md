# Phase 6 — 카운팅 트리거 + 인터럽트

## 목적

v1 `CountingEngine` 자산을 재활용하면서 ADR-013의 `StartCountingAction` 디스패치와 결합한다. 사용자 발화로 카운팅 자동 시작 + 박자 멘트 TTS frame 주입 + 인터럽트 견고성 검증.

## 사전 조건

- Phase 5 완료 (능동 코치 + ActionDispatcher 동작)

## 관련 ADR

- ADR-014 (카운팅 엔진 메트로놈/타이머 + LLM 트리거)
- ADR-011 (Pipecat 인터럽트)

## 작업 항목

### 6-1. CountingEngine 재활용 + cue 풀 확장

- `app/core/counting.py` — v1 자산 그대로 (박자 정확도·`time.monotonic()` 그대로)
- 인터페이스 점검: `start(exercise, reps_or_seconds)`, `stop()`, `pause()`, `resume()`, `on_beat: Callable`, `on_complete: Callable`
- **`app/core/counting_cues.py` 신규** — ADR-014 §"박자 멘트 풀" 표대로 운동·구간별 cue 풀 + 진행 격려 멘트 풀 상수
- `CountingEngine.start()` 진입 시 cue 선택 방식 결정 (`config.counting.cue_selection: random | sequential`)
- 진행 격려 멘트는 박자 사이에 끼움 (`config.counting.encouragement.points: [0.33, 0.66, 0.95]` 시점)

### 6-2. CountingInjectProcessor (Pipecat FrameProcessor)

- `app/pipecat_services/processors/counting_inject.py`
- `CountingEngine.on_beat` 콜백에서 `TextFrame(text=cue)` 생성 → downstream push
- TextFrame이 SentenceAggregator를 거치지 않고 바로 TTS에 도달하도록 routing (또는 별도 TTS service 인스턴스 사용)
- 카운팅 박자 TTS와 LLM 응답 TTS 충돌 회피:
  - 옵션 A: LLM 응답 TTS 완료 후 첫 박자 시작 (1초 grace)
  - 옵션 B: 같은 TTS service queue에 frame 순차 enqueue (Pipecat이 직렬화)
- **권장 = B** (Pipecat queue 활용, 단순)

### 6-3. ActionDispatcher와 CountingEngine 결합

- Phase 5의 `ActionDispatcherProcessor.dispatch`에서 `StartCountingAction` 처리:
  ```python
  case StartCountingAction(exercise=ex, reps=r):
      await counting_engine.start(ex, r)
  ```
- `counting_engine` 인스턴스는 파이프라인 빌더가 주입

### 6-4. 인터럽트 정책 검증

- 사용자가 "그만", "잠깐", "멈춰" 등 발화 → `SafetyGuardProcessor`(또는 별도 InterruptKeywordProcessor)가 키워드 감지 → `counting_engine.pause()` 호출 + LLM 응답 흐름
- 부상 키워드 발화 → 카운팅 즉시 stop + 면책
- 화면 탭 인터럽트 (UI에서 WS로 `InterruptFrame` 전송) → Pipecat broadcast_interruption → LLM·TTS 모두 중단

### 6-5. 카운팅 완료 처리 + 자동 follow-up (능동 주도)

ADR-014 §"카운팅 완료 처리 + 세트 사이 흐름" 그대로 구현:

- `CountingEngine.on_complete` → `SetLogRepository.create(session_id, exercise, target, actual)` 호출
- **그 직후 ActionDispatcherProcessor가 자동 follow-up LLM 호출 트리거** (사용자 발화 없이) — 부트스트랩 메시지: "(세트 완료. 다음 세트/휴식/종료 중 하나를 짧게 제안하세요. 120자 이내.)"
- LLM 응답 = `text` + `actions[ProposeSetAction or 종료 제안]`
- 사용자 확답 룰 그대로 동작 (ConfirmRuleProcessor)
- 휴식 타이머 = `RestTimer` (CountingEngine과 별도 모듈 또는 `CountingEngine.start_rest(60)`)
  - 타이머 중간 격려 멘트 1~2회 + "30초 남았어요" 알림
- 휴식 완료 → `config.counting.auto_next_set` 분기 (true: 자동 다음 세트, false: 사용자 확답 요구)
- 모든 세트 완료 → 종료 제안 LLM 호출

### 6-6. config 갱신

ADR-014 §config 그대로:

```yaml
counting:
  beat_interval_sec: 2.0           # 메트로놈 기본 (1~4초)
  plank_default_sec: 30
  rest_default_sec: 60
  start_delay_sec: 1.0             # LLM 응답 TTS 완료 후 grace
  auto_next_set: false             # 휴식 후 자동 다음 세트 vs 사용자 확답
  cue_selection: "random"          # random | sequential
  encouragement:
    enabled: true
    points: [0.33, 0.66, 0.95]
```

### 6-7. 테스트

- `tests/test_counting_engine.py` — v1 자산 그대로, 박자 정확도 ±10% 통과
- `tests/test_counting_cues.py` — 운동·구간별 cue 풀 + 격려 멘트 풀 비어있지 않음 + 5종 이상 보장
- `tests/test_cue_selection.py` — random/sequential 선택 방식 단위 테스트 (seed 주입)
- `tests/test_counting_inject.py` — Pipecat MockTransport로 박자 → TextFrame 변환 확인
- `tests/test_action_dispatcher_counting.py` — `StartCountingAction` → `engine.start` 호출 검증
- `tests/test_set_complete_followup.py` — `on_complete` → SetLog 기록 + 자동 follow-up LLM 호출 트리거 확인
- `tests/test_interrupt_pause.py` — "그만" 발화 시 engine pause 확인
- `tests/test_e2e_voice_counting.py` (gpu mark) — 실제 음성으로 "푸시업 10회 시작" → 박자 멘트 TTS 출력 + 완료 후 follow-up

## Definition of Done

- [ ] 사용자 발화 "푸시업 10회 시작" → 자동 카운팅 시작 + 박자 멘트 TTS 출력
- [ ] 능동 코치 제안 → "좋아" 확답 → 자동 카운팅 시작
- [ ] 박자 정확도 ±10% (v1 자산 그대로)
- [ ] **박자 멘트가 운동·구간별 cue 풀에서 다양하게 출력** (같은 cue 연속 반복 안 됨)
- [ ] **진행 격려 멘트가 1/3·2/3·마지막 시점에 출력**
- [ ] **카운팅 완료 → SetLog 기록 + 자동 follow-up LLM 호출 → 다음 세트/휴식/종료 제안**
- [ ] 휴식 타이머 동작 + 격려 + "30초 남았어요" 알림
- [ ] 인터럽트 시나리오: "그만" → pause, 부상 키워드 → stop + 안전 응답
- [ ] 화면 탭 인터럽트 → TTS·LLM 중단
- [ ] ruff + pytest 통과
- [ ] git commit `feat(phase-6): 카운팅 트리거 + 박자 풀 + 자동 follow-up + 인터럽트`

## 리스크

- Pipecat TTS service에 박자 frame과 LLM 응답 frame을 직렬화하면 박자가 LLM 응답 뒤에 밀려서 박자 정확도 깨질 위험 → 별도 TTS 인스턴스 또는 별도 audio output queue 검토
- `InterruptFrame` 수신을 UI에서 어떻게 보낼지 — Pipecat 표준 메시지 포맷 확인

## 소요 추정

2~3일.

## 다음 phase

[Phase 7 — UI 재배선 + 검증](phase-7-ui-validation.md)
