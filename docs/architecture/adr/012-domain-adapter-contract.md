# ADR-012: Pipecat 위 도메인 어댑터·서비스 계약

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-005 (STT), ADR-006 (TTS), ADR-011 (Pipecat), ADR-013 (능동 코치), ADR-014 (카운팅)
- **Supersedes (실효)**: `_archive/v1/010-adapter-interfaces.md` (v1 자체 Protocol)

## 컨텍스트

v1은 자체 어댑터 Protocol을 정의했다 — `LLMAdapter`, `STTAdapter`, `TTSAdapter`. 단순 인터페이스(`generate(request)`, `transcribe(audio)`, `synthesize(text)`)로 mock 대체성 보존. ADR-011에서 Pipecat 전면 채택하면 이 Protocol은 의미를 잃는다 — Pipecat의 `FrameProcessor`/`Service` 계층이 같은 역할을 한다.

다만 **도메인 로직은 Pipecat에 종속되면 안 된다**. SafetyGuard·CountingEngine·IntentClassifier·`CoachContextBuilder` 같은 핵심 로직은 Pipecat 의존성 없이 순수 Python으로 작성한다(기존 `app/core/` 정신 계승). Pipecat은 어디까지나 **음성 I/O 파이프라인 오케스트레이터**이고, **도메인 로직은 분리** 유지한다.

## 결정

### 4계층 분리

```
1. Pipecat Service     ← 음성 파이프라인의 노드 (STT/LLM/TTS)
   ↓ wraps
2. Domain Adapter      ← 우리 모델 호출 래퍼 (faster-whisper, Qwen3-TTS 직접)
   ↓ uses
3. Domain Core         ← 순수 도메인 로직 (Safety, Intent, Counting, CoachContext)
   ↓ persists
4. Repository          ← DB 접근 (ADR-008)
```

- **Pipecat Service** = `pipecat.services.*.base` 상속. frame 변환만 책임. 무거운 추론은 Domain Adapter 위임.
- **Domain Adapter** = `app/adapters/{llm,stt,tts}/*.py`. 실제 모델 호출. Pipecat 의존성 0.
- **Domain Core** = `app/core/*.py`. 순수 Python. Pipecat·FastAPI·SQLModel 의존성 0.
- **Repository** = `app/db/repositories.py`. DB 접근.

### 폴더 구조

```
app/
├── adapters/                       # ← Pipecat 의존성 0
│   ├── llm/
│   │   └── ollama_client.py        # Ollama HTTP 호출 + instructor binding
│   ├── stt/
│   │   ├── faster_whisper_client.py # faster-whisper 직접 호출
│   │   └── resample.py             # librosa 16kHz 강제
│   └── tts/
│       ├── qwen3_client.py         # transformers Qwen3-TTS + SDPA
│       └── melotts_client.py       # fallback
├── pipecat_services/               # ← Pipecat 통합 레이어
│   ├── ollama_service.py           # OllamaLLMService 래핑 + instructor
│   ├── whisper_service.py          # WhisperSTTService 래핑 또는 자체
│   ├── qwen3_tts_service.py        # TTSService 상속, qwen3_client 사용
│   └── processors/
│       ├── safety_guard.py         # FrameProcessor 상속, SafetyGuardCore 호출
│       ├── confirm_rule.py         # FrameProcessor, _pending_proposal 슬롯
│       ├── action_dispatcher.py    # FrameProcessor, LLM action 디스패치
│       └── counting_inject.py      # FrameProcessor, 카운팅 박자 frame 주입
├── core/                           # ← Pipecat 의존성 0
│   ├── safety.py                   # SafetyGuardCore — 부상 키워드 분류
│   ├── coach_context.py            # CoachContextBuilder — 프로필+세션+루틴 요약
│   ├── coach_response.py           # CoachResponse Pydantic 모델
│   ├── counting.py                 # CountingEngine — 메트로놈/타이머 상태머신
│   └── session_state.py            # WorkoutSessionState — 진행 중 세션 메모리 상태
├── api/                            # ← FastAPI 엔드포인트
│   ├── main.py
│   ├── health.py
│   ├── session.py
│   ├── routine.py
│   ├── onboarding.py
│   └── ws_voice.py                 # Pipecat 파이프라인 마운트
└── db/
    ├── models.py                   # SQLModel
    └── repositories.py
```

### 의존 방향 규칙 (강제)

```
api → pipecat_services → adapters → (외부: Ollama/faster-whisper/transformers)
                       ↓
                       core (순수 도메인)
                       ↓
                       db
```

- `core`는 다른 어떤 것도 import 금지 (FastAPI·Pipecat·SQLModel·transformers 모두 X)
- `adapters`는 `core` import 금지 (역참조 방지)
- `pipecat_services`는 `adapters` + `core` 모두 import 가능
- `api`는 모든 계층 import 가능, 단 직접 모델 호출은 금지 (`pipecat_services` 경유)

### Pipecat Service 작성 패턴

```python
# app/pipecat_services/qwen3_tts_service.py
from pipecat.services.tts.base import TTSService
from pipecat.frames.frames import TTSAudioRawFrame
from app.adapters.tts.qwen3_client import Qwen3TTSClient   # 도메인 어댑터

class Qwen3TTSService(TTSService):
    def __init__(self, client: Qwen3TTSClient):
        super().__init__(sample_rate=24000)
        self._client = client   # Pipecat 의존성 없는 순수 어댑터 주입

    async def run_tts(self, text: str):
        async for chunk in self._client.stream(text):    # 어댑터가 streaming
            yield TTSAudioRawFrame(audio=chunk, sample_rate=24000, num_channels=1)
```

이렇게 분리하면 **도메인 어댑터는 Pipecat 없이도 단위 테스트 가능**, **Pipecat Service는 mock 클라이언트로 단위 테스트 가능** (ADR-019 테스트 전략).

### Domain Core 작성 패턴

```python
# app/core/coach_context.py
@dataclass
class CoachContextBuilder:
    profile_repo: UserProfileRepository
    session_repo: SessionRepository
    set_repo: SetLogRepository
    condition_repo: ConditionRepository
    routine_repo: RoutineRepository

    async def build(self, *, recent_sessions: int = 5) -> str:
        """프로필 + 최근 N회 세션 + 활성 루틴 + 최근 컨디션을 600자 이내 자연어 한 덩어리로."""
        ...
```

- Pipecat·FastAPI·instructor 모두 import 안 함
- 입력은 Repository (인터페이스), 출력은 str
- Pipecat Service에서 `await builder.build()`로 호출

### LLM 호출 — instructor 결합 (ADR-013 참조)

`OllamaLLMService`는 Pipecat 기본 어댑터를 그대로 쓰되, **JSON 구조화 출력**은 instructor를 함께 사용한다:

```python
# app/pipecat_services/ollama_service.py
import instructor
from openai import AsyncOpenAI
from app.core.coach_response import CoachResponse

class StructuredOllamaService(OllamaLLMService):
    def __init__(self, model: str):
        super().__init__(model=model, base_url="http://localhost:11434/v1")
        self._instructor = instructor.from_openai(
            AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )

    async def generate_structured(self, messages: list[dict]) -> CoachResponse:
        return await self._instructor.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_model=CoachResponse,
            max_retries=2,
        )
```

상세는 ADR-013.

## 결과

### 긍정
- 도메인 로직(core)이 Pipecat에 종속되지 않음 — 프레임워크 바꿔도 core 변경 0
- Pipecat Service는 얇은 어댑터 — Pipecat 업그레이드 영향 표면 최소
- 도메인 어댑터는 mock으로 단위 테스트 가능 (ADR-019)
- 4계층 분리가 명확 — 어디에 무엇을 넣을지 의사결정 단순

### 부정
- 계층이 많아 보일 수 있음 (4계층). 단순 case에서는 over-engineering 느낌
- Pipecat Service ↔ Domain Adapter 사이 글루 코드 작성 부담 (얇지만 0은 아님)
- `pipecat_services/` 와 `adapters/` 의 책임 경계가 처음엔 모호할 수 있음 — 본 ADR이 가이드

## 대안

| 후보 | 탈락 사유 |
|---|---|
| Pipecat Service에 모델 로딩·추론 직접 작성 | core/adapters 분리 정신 위배, 테스트 어려움 |
| v1 자체 Protocol 유지 + Pipecat 위에 어댑터로 wrap | Pipecat 채택 동기(인터럽트 견고성 등) 일부 무화 |
| 3계층(Service = Adapter + Service 통합) | mock 대체성·테스트 용이성 손해 |

## References
- [Pipecat Service 작성 가이드](https://docs.pipecat.ai/server/services/llm/overview)
- [Pipecat FrameProcessor 가이드](https://docs.pipecat.ai/server/frameworks/frame-processor)
- [instructor Mode.JSON](https://python.useinstructor.com/concepts/patching/)
- v1 ADR-010 (자체 Protocol) — `_archive/v1/010-adapter-interfaces.md`
