# ADR-014: 카운팅 엔진 — 메트로놈/타이머 + LLM 트리거

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-011 (Pipecat), ADR-013 (능동 코치 트리거)
- **계승**: v1 `app/core/counting.py` (CountingEngine 자산)

## 컨텍스트

### v1 상태
- 메트로놈(풀업·푸시업·스쿼트) / 타이머(플랭크) 박자 엔진은 v1에서 구현 완료
- 박자 정확도 ±10% (PRD 7-1 #2) — `time.monotonic()` 기반 절대 시각 사용 (sleep 누적 방지, v1 검증)
- **문제는 트리거**: 사용자 발화로 카운팅이 시작 안 됨 → UI 버튼만 트리거. 사용자 피드백 "운동 카운팅이 기능하지 않아"의 정체.

### v3 해결
- 트리거 = ADR-013 능동 코치의 `StartCountingAction` 디스패치
- 박자 엔진 = v1 자산 재활용 (수정 최소)
- vision 기반(MediaPipe Pose) 카운팅은 **MVP 범위 밖** — P2 검토 (사용자 결정, 2026-05-31)

## 결정

### 카운팅 엔진 = 메트로놈/타이머 유지 (v1 자산)

- **위치**: `app/core/counting.py` (Domain Core, ADR-012 분리 정신)
- **외부 의존성 0**: Pipecat·FastAPI·SQLModel 모두 import 안 함
- **인터페이스**:

```python
@dataclass
class CountingEngine:
    on_beat: Callable[[BeatEvent], Awaitable[None]]   # 박자 콜백 (TTS/UI에 frame inject)
    on_complete: Callable[[CompleteEvent], Awaitable[None]]

    async def start(self, exercise: ExerciseName, target_reps_or_seconds: int) -> None: ...
    async def stop(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
```

### 박자 정책 (PRD §5 계승)

| 운동 | 모드 | 박자 구성 |
|---|---|---|
| 풀업 | 메트로놈 | 올라가기 + 내려가기 |
| 푸시업 | 메트로놈 | 내려가기 + 올라가기 |
| 스쿼트 | 메트로놈 | 앉기 + 서기 |
| 플랭크 | 타이머 | 초 단위 카운트다운 |

운동 종목은 MVP에서 4종 고정. 추가 종목(런지·버피·점프스쿼트 등)은 사용자 의향 있으나 **추후 별도 ADR**로 결정 (`Literal[...]` enum 확장 + cue 풀 추가).

### 박자 멘트 풀 (멘트 다양화)

같은 cue를 반복하면 지루하므로 **운동·구간별 cue 풀에서 랜덤 또는 순환 선택**한다. v1은 운동별 단일 cue였으나 v3에서 멘트 풀로 확장.

| 운동 | 구간 | cue 풀 (각 5종 권장) |
|---|---|---|
| 풀업 | 당기기 | "올라가요!" / "당기세요!" / "끌어올려요!" / "한 번 더 당겨요!" / "꽉 잡고!" |
| 풀업 | 내리기 | "내려오세요" / "천천히" / "컨트롤" / "버티며 내려요" / "긴장 유지" |
| 푸시업 | 내리기 | "내려가요!" / "천천히" / "가슴까지!" / "버티며" / "코어 단단히" |
| 푸시업 | 올리기 | "올라와요!" / "밀어내요!" / "쭉 펴서!" / "한 번 더!" / "끝까지!" |
| 스쿼트 | 앉기 | "앉아요!" / "엉덩이 뒤로!" / "허벅지 평행!" / "천천히" / "무릎 발끝 방향!" |
| 스쿼트 | 일어서기 | "올라와요!" / "쭉 펴서!" / "엉덩이 조여요!" / "발바닥 전체로!" / "한 번 더!" |
| 플랭크 | 카운트다운 | "{N}초!" / "{N}초 남았어요" / "{N}초, 코어에 힘!" / "{N}초, 호흡!" / "{N}초, 버텨요!" |

추가로 **진행 격려 멘트** (박자와 별개, 1/3 / 2/3 / 마지막 1렙 지점에 끼움):
- 1/3 지점: "좋아요, 호흡 유지!" / "리듬 좋아요!" / "잘하고 있어요!"
- 2/3 지점: "거의 다 왔어요!" / "조금만 더!" / "마지막까지!"
- 마지막 1렙: "마지막!" / "한 번 더 끝!" / "완성!"

실제 cue 풀은 `app/core/counting_cues.py` (phase-6 작성)에 상수로. 랜덤 선택은 `random.choice`로 단순화 (재현 가능 테스트는 seed 주입).

### 트리거 경로 (ADR-013과 통합)

```
사용자: "푸시업 10회 시작하자"
   ↓
SafetyGuardProcessor (부상 키워드 X)
   ↓
StructuredOllamaService → CoachResponse(text="좋아요, 시작할게요!", actions=[StartCountingAction(exercise="푸시업", reps=10)])
   ↓
ActionDispatcherProcessor.dispatch:
   - StartCountingAction → counting_engine.start("푸시업", 10)
   ↓
SentenceAggregator → TTS "좋아요, 시작할게요!"
   ↓ (병렬)
CountingEngine.on_beat → TTS frame "하나 — 내려가요!" → ...
```

### TTS 박자 멘트와 LLM 응답의 순서

- 원칙: **박자는 항상 LLM 응답 뒤에 붙여 실행** — "좋아요, 시작할게요" 응답 TTS 완료 후 1초 grace + 첫 박자
- 구현: 같은 TTS service queue에 LLM 응답 frame 먼저 enqueue → 박자 frame을 그 뒤에 enqueue (Pipecat이 직렬화)
- 충돌 회피 디테일은 phase-6 개발 과정에서 실제 frame 흐름을 보며 검증. 큰 문제로 보이지 않으나 race condition 시 grace 시간·queue 우선순위 조정으로 해결

### Pipecat 통합 (CountingInjectProcessor)

```python
# app/pipecat_services/processors/counting_inject.py
class CountingInjectProcessor(FrameProcessor):
    """CountingEngine의 박자 이벤트를 TTS frame으로 변환해 파이프라인에 주입."""

    def __init__(self, engine: CountingEngine):
        super().__init__()
        engine.on_beat = self._inject_beat

    async def _inject_beat(self, event: BeatEvent):
        text = event.cue   # 예: "하나 — 내려가요!"
        await self.push_frame(TextFrame(text=text), FrameDirection.DOWNSTREAM)
```

### 카운팅 완료 처리 + 세트 사이 흐름 (능동 주도 원칙 적용)

ADR-013 §0 능동 주도 원칙에 따라, **카운팅 완료 후 코치가 먼저 다음 행동을 제안**한다. 사용자가 직접 "다음 세트" 같이 발화하기를 기다리지 않는다.

흐름:

```
CountingEngine.on_complete (마지막 렙 완료)
   ↓
SetLogRepository.create(session_id, exercise, target_reps, actual_reps)  ← DB 기록
   ↓
ActionDispatcherProcessor가 자동 follow-up LLM 호출 트리거 (사용자 발화 없이)
   부트스트랩 user 메시지: "(세트 완료. 다음 세트/휴식/종료 중 하나를 짧게 제안하세요. 120자 이내.)"
   ↓
LLM 응답 예: text="잘했어요! 1분 쉬고 한 세트 더 갈까요?", actions=[ProposeSetAction(...)]
   ↓
SentenceAggregator → TTS 재생
   ↓
사용자 확답 ("좋아") → ConfirmRuleProcessor → 휴식 타이머 시작
   ↓
휴식 60초 (config) — 타이머 동안 격려 멘트 1~2회 + "30초 남았어요" 알림
   ↓
휴식 완료 → 자동 다음 세트 시작 (또는 다시 확답 룰 — config로 선택)
   ↓
모든 세트 완료 → 코치가 "오늘 운동 마칠까요?" 종료 제안
```

핵심: **사용자가 능동적으로 운동 진행을 결정하지 않아도 코치가 모든 분기를 먼저 제안**. ADR-013 §0 원칙의 운동 중 실행. 단 사용자가 발화로 흐름을 바꾸면(예: "오늘은 여기까지", "1세트만 더 하고 끝낼게") LLM이 수용 (ADR-013 §0 (b)).

### 인터럽트 정책

- 사용자가 운동 중 "그만", "잠깐", "멈춰" 등 발화 → STT → 인터럽트 키워드 감지 → `counting_engine.pause()` 호출 + LLM 응답 흐름
- 사용자가 부상 키워드 발화 → 카운팅 즉시 중단 + 안전 응답 (ADR-013 §면책·안전 — 홈트 간소화)
- 화면 탭 인터럽트 (UI에서 WS로 `InterruptionFrame` 전송) → Pipecat broadcast_interruption → LLM·TTS·카운팅 모두 중단
- 휴식 종료 후 자동 재개는 `config.counting.auto_next_set` 으로 선택 (true: 자동, false: 사용자 확답 요구)

### 박자 정확도 보장 (v1 정책 계승)

- `time.monotonic()` 절대 시각 기반 — `asyncio.sleep(delta)` 누적 drift 방지
- 다음 박자 시각 = `start_time + beat_interval * beat_index`
- 박자 누적 오차 ±10% (PRD §5-2)

### config

```yaml
counting:
  beat_interval_sec: 2.0           # 메트로놈 기본 (1~4초)
  plank_default_sec: 30
  rest_default_sec: 60
  start_delay_sec: 1.0             # LLM 응답 TTS 완료 후 grace
  auto_next_set: false             # 휴식 후 자동 다음 세트 vs 사용자 확답
  cue_selection: "random"          # random | sequential (멘트 풀 선택 방식)
  encouragement:                   # 진행 격려 멘트 (1/3, 2/3, 마지막)
    enabled: true
    points: [0.33, 0.66, 0.95]
```

## 결과

### 긍정
- v1 자산(`core/counting.py`) 재활용 — 박자 정확도 회귀 위험 0
- 트리거가 LLM 액션으로 자연스럽게 동작 — 사용자 발화로 시작
- **카운팅 완료 → 코치 자동 follow-up** — ADR-013 §0 능동 주도 원칙 일관 적용
- 박자 멘트 풀로 다양화 — 사용자 지루함 감소
- Pipecat에 의존하지 않는 Domain Core — 테스트 단순
- vision 미사용 — 카메라 권한·프레임아웃·CPU/GPU 부담 0

### 부정
- 사용자 동작과 무관한 박자 — 사용자가 박자를 못 맞추면 무의미한 카운팅
- 진짜 "AI 카운팅"이 아님 — P2 vision 기반은 별도 ADR로 검토 (MediaPipe Pose 99.5% 정확도 입증)
- 카운팅 완료 → 자동 follow-up 호출이 매 세트마다 1회 추가 LLM 호출 — 평균 응답 1초이므로 휴식 시간 안에 충분히 처리

## 대안

| 후보 | 탈락 사유 |
|---|---|
| MediaPipe Pose 기반 vision 카운팅 (P0) | 카메라 권한·프레임아웃 대응·UI 변경 부담. MVP 범위 밖. P2 검토 |
| MMPose / OpenPose | MediaPipe 대비 무거움, 한국어 fitness 도메인 자료 적음 |
| 단순 타이머 (메트로놈 폐기) | PRD §5-1 운동별 박자 요구사항 미달 |
| 음성 분석 기반 (사용자 호흡·리듬) | 연구 단계, 신뢰도·노이즈 영향 큼 |

## 후속

- **운동 종목 확장** (런지·버피·점프스쿼트 등) — 사용자 의향 있음. 추후 별도 ADR로 종목 + cue 풀 + 박자 패턴 결정
- (P2) vision 기반 카운팅 ADR — MediaPipe Pose 도입 시점·UI 변경·privacy(로컬 처리 보장) 검토
- (P2) 헬스장 모드(C2S) 화면에서 폼 피드백 (현재는 음성으로만)
- (P2) cue 풀 사용자 커스터마이즈 — 본인 스타일 멘트 추가 가능

## References
- v1 `app/core/counting.py` — 박자 엔진 자산
- PRD v4 §5 (카운팅 박자 정책)
- [MediaPipe Pose](https://developers.google.com/mediapipe/solutions/vision/pose_landmarker) — P2 검토용
- [Real-Time Fitness Exercise Classification and Counting](https://arxiv.org/html/2411.11548v1) — vision 기반 99.5% 정확도 사례
