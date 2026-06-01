# ADR-013: 능동 코치 — instructor + JSON 구조화 출력 + 액션 디스패치

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-003 (Ollama), ADR-004 (qwen3:8b), ADR-011 (Pipecat), ADR-012 (어댑터), ADR-014 (카운팅)
- **계승**: `_archive/v1/021-active-coach.md` (v1 시점 단일응답 JSON action 하이브리드)
- v1 시점 ADR-021은 Accepted 됐으나 **코드 미구현**. v3에서 구현까지 완수.

## 컨텍스트

### PRD v4 요구사항 (P0)

- "AI 코칭 대화 엔진 — 의도 분류 후 응답" ✅ v1 구현
- "실시간 일정 자동 조정 — 상황 감지 → 루틴 재계산 → 사용자 확인 → 적용" ❌ v1 미구현
- "운동 기록 + 루틴 분석 — 주간 패턴 → 개선안 제안" ❌ v1 미구현

v1 출시본의 `core/orchestrator._handle_text`는 `_run_llm → _run_tts`만 호출 — 사용자 입력 "푸시업 10회 시작하자"로도 카운팅이 시작되지 않는다. UI 버튼만 카운팅 트리거가 됨. **코치가 너무 수동적**이라는 사용자 피드백의 핵심 원인.

DB·Repository는 `WorkoutSession.get_recent(n)`, `SetLog.get_by_session`, `ConditionLog`, `RoutineRepository.list_all`, `UserProfileRepository.get`을 이미 제공한다. **데이터 표면은 갖춰져 있고, 코치(LLM)가 활용하는 흐름만 비어 있다.**

### v1 ADR-021의 결정과 한계

v1 시점에 옵션 C(단일응답 JSON action 하이브리드)를 채택했다:
- 매 LLM 호출 1회로 `{text, actions[]}` 응답
- actions: `propose_set`, `start_counting`, `log_condition` 3종
- Ollama `format="json"` 강제

한계:
- **자체 JSON 파서** — schema drift·partial JSON·retry 직접 구현
- **Pipecat 미사용 시점** — 인터럽트·sentence aggregation 직접 구현 부담
- **코드 미구현** 상태로 종료

v3에서는 같은 정신을 이어받되, **instructor 라이브러리로 JSON 구조화 출력의 신뢰성·retry·schema validation 외주**하고, Pipecat 파이프라인에 통합한다.

## 결정

### §0. 핵심 원칙 (모든 하위 결정의 전제)

**코치는 항상 능동적으로 운동을 주도한다.** 사용자가 먼저 요청하기를 기다리지 않는다.

- 세션 시작 시: 사용자 발화 없이 코치가 먼저 인사 + 오늘의 운동 제안
- 세트 사이: 코치가 다음 세트/휴식/종료를 먼저 제안
- 컨디션 변화 감지 시: 코치가 먼저 강도 조정·휴식 제안
- 사용자 발화는 코치 제안에 대한 **응답·수정·거절**이 주된 패턴. 사용자가 운동을 먼저 설계하는 경우는 예외 케이스

이 원칙이 §1~§13 모든 하위 결정의 전제다. LLM 시스템 프롬프트(`ACTIVE_COACH_PROTOCOL`)와 응답 길이 정책 모두 이 원칙을 따른다.

#### 완화 메커니즘 (필요 시 사용자가 톤 조절 가능)

능동 주도가 부담스러운 상황에서 사용자가 다음 두 가지로 톤 조절 가능:

- **(a) 전체 비활성**: `config.coach.proactive_opener: false` — 세션 시작 능동 인사 OFF (v1 수동 흐름 회귀)
- **(b) 자연어 요청**: 사용자가 발화로 "오늘은 내가 정할게", "추천 그만" 등 의향 표현 → LLM이 시스템 프롬프트의 "사용자가 다른 의향 표현 시 그것을 우선 수용. 능동 제안은 다음 turn으로 미룬다" 규칙에 따라 자연스럽게 수용
- **(c) (P2) 자동 완화 룰**: "N회 연속 거절 시 M분간 능동 제안 자제" — MVP에서는 미구현. 사용자 피드백 후 별도 ADR로 결정

(a)는 config로, (b)는 LLM이 시스템 프롬프트 따라 자율 처리. MVP는 (a)(b)로 충분.

### 응답 스키마 (Pydantic)

```python
# app/core/coach_response.py
from typing import Literal
from pydantic import BaseModel, Field

class ProposeSetAction(BaseModel):
    type: Literal["propose_set"] = "propose_set"
    exercise: Literal["풀업", "푸시업", "스쿼트", "플랭크"]
    reps: int = Field(ge=1, le=100)
    sets: int = Field(ge=1, le=10)
    rest_sec: int = Field(ge=15, le=300)

class StartCountingAction(BaseModel):
    type: Literal["start_counting"] = "start_counting"
    exercise: Literal["풀업", "푸시업", "스쿼트", "플랭크"]
    reps: int = Field(ge=1, le=100)

class LogConditionAction(BaseModel):
    type: Literal["log_condition"] = "log_condition"
    fatigue_level: int = Field(ge=1, le=10)
    notes: str | None = None

CoachAction = ProposeSetAction | StartCountingAction | LogConditionAction

class CoachResponse(BaseModel):
    text: str = Field(min_length=1, max_length=500)   # hard cap (안전망)
    actions: list[CoachAction] = Field(default_factory=list)
```

응답 종류별 soft limit는 시스템 프롬프트로 안내 (§"응답 길이 정책" 참조). Pydantic `max_length=500`은 LLM이 멋대로 폭주할 때의 안전망.

### LLM 호출 — instructor 결합

```python
import instructor
from openai import AsyncOpenAI

client = instructor.from_openai(
    AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
    mode=instructor.Mode.JSON,
)

response: CoachResponse = await client.chat.completions.create(
    model="qwen3:8b",
    messages=[
        {"role": "system", "content": SAFETY_PREFIX + ACTIVE_COACH_PROTOCOL + context},
        *history,
        {"role": "user", "content": user_text},
    ],
    response_model=CoachResponse,
    max_retries=2,       # ★ JSON schema 위반 시 자동 재시도
)
```

**instructor의 장점**:
- Pydantic 모델로 schema 자동 생성 + LLM에 inject
- Schema 위반 시 자동 retry (max_retries) — v1의 fallback parser 부담 제거
- Type-safe 결과 — `response.actions[0].exercise` 같은 IDE 자동완성
- 다양한 backend (Ollama, OpenAI, Anthropic) 동일 인터페이스

### 시스템 프롬프트 구조

```
[SAFETY_SYSTEM_PREFIX]                ← 한국어 강제 + 안전 규칙 + 부상 무시 거부
[ACTIVE_COACH_PROTOCOL]               ← §0 능동 주도 원칙 + 응답 스키마 + 액션 예시 + 응답 길이 가이드 + 캘린더 활용 안내
[사용자 컨텍스트]                       ← CoachContextBuilder 출력 (캘린더 패턴 포함, 700자 이내)
```

`ACTIVE_COACH_PROTOCOL` 본문이 본 ADR의 핵심. 다음 항목을 명시:

1. **능동 주도 원칙** — "당신은 사용자의 운동을 능동적으로 주도하는 코치다. 사용자가 먼저 운동을 제안하기를 기다리지 마라."
2. **응답 스키마** — `{text, actions[]}` 형식 + 3종 액션 정의
3. **응답 길이 가이드** — "능동 인사 = 70자, 능동 제안 = 120자, 사용자 발화 응답 = 평소 톤 (200~500자), 안전 응답 = 150자. 사용자가 부담 없이 짧게 응답할 수 있도록 능동 응답은 짧게."
4. **캘린더 패턴 활용 안내** — "사용자의 캘린더 패턴을 자연스럽게 언급하여 능동 제안을 한다. 예: '지난주 화요일처럼 푸시업 어떠세요?', '5일 만의 운동이네요, 가볍게 시작할까요?'"
5. **수용 정책** — "사용자가 다른 의향(거절·변경 요청·자체 제안)을 표현하면 그것을 우선 수용. 능동 제안은 다음 turn으로 미룬다."

### 컨텍스트 빌더 (Domain Core)

```python
# app/core/coach_context.py
class CoachContextBuilder:
    """프로필 + 최근 N회 세션 + 활성 루틴 + 최근 컨디션 + 캘린더 패턴을 700자 이내 자연어로."""

    async def build(self, *, recent_sessions: int = 5) -> str:
        profile = await self.profile_repo.get()
        sessions = await self.session_repo.get_recent(n=recent_sessions)
        routine = await self.routine_repo.list_all()
        conditions = await self.condition_repo.get_recent(n=3)

        # 캘린더 데이터 (ADR-020 연계)
        weekly_pattern = compute_weekly_pattern(sessions_4w)        # "월·수·금 주 3회"
        last_exercise = compute_last_exercise_dates(sessions_30d)   # {"푸시업": "5일 전"}
        rest_streak = detect_rest_streak(sessions, now)             # 0 또는 2+

        now = datetime.now()
        time_label = self._time_of_day(now)   # "아침" / "낮" / "저녁" / "새벽"

        return self._format(
            profile, sessions, routine, conditions, time_label,
            weekly_pattern, last_exercise, rest_streak,
        )
```

- `compute_*` 함수는 `app/core/calendar_metrics.py` (ADR-020에서 도입) 재사용
- 매 LLM 호출마다 호출 (SQLite read 4~6건, 비용 미미)
- 출력 예시:

  > 사용자 프로필: 30대 남성, 중급. 활성 루틴: 월·수·금 풀업/푸시업/스쿼트. 최근 5세션 요약: ... 최근 컨디션 평균 7/10. 주간 패턴: 월·수·금 주 3회 패턴 유지 중. 푸시업 마지막 = 5일 전, 풀업 마지막 = 어제. 휴식 streak: 2일. 현재 저녁 7시.

### 능동 인사 (proactive opener)

- 세션 시작 직후 사용자 발화 없이 LLM 1회 호출 (§0 능동 주도 원칙의 1차 실행)
- 부트스트랩 user 메시지:
  > `(세션을 시작했습니다. 사용자에게 짧게 인사하고, 캘린더 패턴과 최근 컨디션을 토대로 오늘의 추천 1건을 제안하세요. 70자 이내.)`
- 응답은 `text` + `actions[propose_set]`을 포함하는 게 기대 동작
- 응답 길이 = 70자 이내 (능동 인사 정책, §"응답 길이 정책" 참조)
- `config.coach.proactive_opener: true` (기본). false로 끄면 능동 인사 OFF (§0 완화 메커니즘 (a))
- **세션 중 능동 제안**: 세트 완료 후 ActionDispatcher가 자동 follow-up LLM 호출 트리거 → 다음 세트 제안 (§0 능동 주도 원칙의 2차 실행)

### 확답 룰 (ConfirmRuleProcessor — Pipecat FrameProcessor)

- LLM이 `propose_set`을 발화하면 `_pending_proposal` 슬롯에 메모리 저장 (DB 영속 X — 세션 메모리)
- 다음 사용자 발화 처리 전 confirm 룰 적용:

| 사용자 발화 키워드 | 동작 |
|---|---|
| `좋아요`, `좋아`, `시작`, `시작하자`, `가자`, `하자`, `그래`, `응`, `네`, `ok`, `OK`, `yes`, `콜` | `_pending_proposal` → `start_counting` 즉시 실행, LLM 호출 생략 (또는 "시작할게요" 짧은 즉답) |
| `아니`, `싫어`, `패스`, `나중에`, `안 할래` | `_pending_proposal` 해제, 일반 LLM 응답 흐름 |
| 매치 없음 | 슬롯 유지, LLM 응답 흐름 (LLM이 컨텍스트 보고 자율적으로 `start_counting` 발화 가능) |

- LLM이 `start_counting`을 직접 발화하면 propose 단계 생략하고 즉시 시작 (사용자가 명시적으로 "푸시업 10회 시작" 입력한 경우)

### 액션 디스패처 (ActionDispatcherProcessor — Pipecat FrameProcessor)

```python
async def dispatch(self, actions: list[CoachAction]):
    for action in actions:
        match action:
            case ProposeSetAction():
                self._pending_proposal = action     # 슬롯 저장
            case StartCountingAction():
                await self.counting_engine.start(action.exercise, action.reps)
            case LogConditionAction():
                await self.condition_repo.create(level=action.fatigue_level, notes=action.notes)
```

### Pipecat 파이프라인 배치

ADR-011 파이프라인 다이어그램의 `[OllamaLLMService + instructor]` 자리에 본 ADR의 `StructuredOllamaService`가 들어가고, 그 뒤에 `ActionDispatcherProcessor`가 actions를 가로채 디스패치한 뒤 `text`만 다음 노드(SentenceAggregator → TTS)로 전달한다.

### 한자 후처리

- v1 known issue: qwen3.5/qwen3가 간혹 한자 단어를 응답에 포함
- `text` 필드에만 `strip_non_korean_cjk(text)` 적용 (v1 자산 재활용)
- action 페이로드(exercise 이름 등)는 그대로 — 미리 정의된 한글 enum이라 영향 없음

### 면책·안전 (홈트레이닝 가정 — 간소화)

홈트레이닝 환경(맨몸운동, 본인 1인)이라 헬스장·중량 운동 대비 응급 시나리오 가능성이 매우 낮다. 따라서 안전 처리는 **합리적 최소 수준**으로 유지하고 과도한 법적 면책·119 자동 호출 등은 도입하지 않는다.

- `SAFETY_SYSTEM_PREFIX` (v1 자산 재활용) — 한국어 강제·통증 무시 거부·운동 강행 권유 금지
- 부상 키워드 (`아파`, `다쳤어`, `삐었어`, `쑤셔`, `결려`, `쥐가 났어` 등 v1 자산 base 20+종)는 `SafetyGuardProcessor`가 LLM 호출 **전에** 인터셉트 → 즉시 카운팅 중단 + "괜찮으세요? 통증이 있으면 잠시 쉬세요. 심하면 전문의와 상담하세요" 정도의 짧은 응답 (150자 이내)
- 응급 키워드 (`숨 안 쉬어져`, `의식 잃을 것 같아` 등)는 즉시 운동 중단 + "괜찮으세요? 무리되시면 119에 연락하세요" 안내. 자동 119 호출·외부 알림은 도입하지 않음 (홈트레이닝 가정 + 법적 부담 회피)
- 면책 고지는 단일 사용자 가정 하 옵션 모달 (PRD v4 §6 — v1 결정 계승)
- 실제 키워드 목록은 phase-5 진입 시 `SafetyGuardCore`에서 v1 자산 base로 확정. 사용자가 추가/제외 의향 있으면 그 시점에 반영

### 응답 길이 정책

응답 종류별 soft limit (시스템 프롬프트로 안내) + hard cap (Pydantic `Field(max_length=500)` 안전망):

| 응답 종류 | 목표 길이 | 톤 가이드 |
|---|---|---|
| 능동 인사 (proactive opener) | **70자** | 1~2문장, 핵심 제안만. "안녕하세요! 5일 만이네요, 가볍게 푸시업 3×10 어떠세요?" |
| 능동 제안 (`propose_set` 동반) | **120자** | 1~2문장, 제안 + 짧은 이유. "최근 컨디션이 좋네요. 스쿼트 15회로 강도 살짝 올려볼까요?" |
| 카운팅·휴식 멘트 (CountingEngine) | **5~15자** | "잘하고 있어요!", "휴식 1분이에요" |
| 일반 응답 (사용자 발화에 대한 응답) | **200~500자** | 평소 톤, 자유 |
| 안전 응답 (부상 키워드 감지) | **150자** | 명확·간결·전문의 안내 |

`ACTIVE_COACH_PROTOCOL`에 위 가이드 명시 + 부트스트랩 메시지에 길이 힌트 포함 ("70자 이내" 등).

### config

```yaml
coach:
  proactive_opener: true               # §0 (a) 완화 메커니즘
  context_recent_sessions: 5
  calendar_pattern_weeks: 4            # 컨텍스트 빌더 — 최근 N주 패턴 분석
  response_length:
    proactive_opener_max: 70
    proactive_proposal_max: 120
    reactive_max: 500
    safety_max: 150
  instructor:
    max_retries: 2
    mode: "json"
```

## 결과

### 긍정
- 사용자 발화로 카운팅 자동 시작 — PRD §5-1 정상화
- 능동 인사·운동 기록 활용·제안→확답→시작 흐름 정상화 — PRD §3-1 P0 완성
- instructor가 JSON schema validation·retry 외주 — v1 자체 파서 부담 제거
- type-safe Pydantic 응답 — IDE 자동완성·정적 분석 가능
- 단일 LLM 호출 유지 — PRD §4-1 지연 목표 보존

### 부정
- Pydantic + instructor + Ollama format=json 3중 layer — 디버깅 시 어디서 schema 위반인지 추적 필요
- `_pending_proposal` 메모리 슬롯 (세션 단위) — 세션 복원 시 사라짐 (P1)
- `context_recent_sessions=5` 시 시스템 메시지 토큰 200~600자 추가 — qwen3:8b는 영향 미미
- instructor retry로 인한 평균 지연 +0~200ms (schema 일관 시 retry 0회)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| Ollama tool calling (multi-turn) | 2~3회 LLM 호출 → 지연 2~3배, PRD §4-1 위반 |
| 컨텍스트 주입만 (룰 추출 직접) | "어제 푸시업 20회 하셨네요" 같은 능동 제안 불가 |
| BAML (시스템 별 schema 생성) | Python 단일 환경엔 over-engineering, 빌드 단계 추가 부담 |
| outlines (constrained decoding) | Ollama 표준 통합 부족, instructor가 더 단순 |
| 자체 JSON parser (v1 ADR-021) | retry·validation 직접 구현, instructor가 같은 일 더 잘함 |

## 후속

- `_pending_proposal` DB 영속 (P1) — 라이브 세션 복원과 함께 처리
- LLM 응답 sentence-streaming + 액션 디스패치 순서 보장 (Pipecat ActionDispatcher가 actions 먼저 처리, text는 sentence 단위 forward)
- Smart Turn 활성 시 (ADR-007) 코치 발화 도중 자연스러운 인터럽트 확인

## References
- [instructor](https://python.useinstructor.com/)
- [instructor + Ollama 통합](https://python.useinstructor.com/integrations/ollama/)
- [Pydantic 2 + Discriminated Unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions)
- [Reliable Structured Output from Local LLMs](https://markaicode.com/ollama-structured-output-pipeline/)
- v1 ADR-021 (단일응답 JSON action 하이브리드 — Accepted but unimplemented)
