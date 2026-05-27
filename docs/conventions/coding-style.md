# 코딩 컨벤션 — LocalFit AI

AGENTS.md의 코딩 규약 상세본. 에이전트와 사람 모두 이 문서를 기준으로 한다.

## 1. Python 일반

### 버전·스타일
- Python 3.11+ (match문, `X | Y` 타입 표기 사용 가능)
- PEP 8 준수, 들여쓰기 4 spaces
- 한 줄 최대 100자 (검은색 포매터 기본값과 다름 — 가독성 우선)
- 포매터: `ruff format`, 린터: `ruff check`

### 타입 힌트
- 모든 함수 시그니처에 타입 힌트 필수
- `Optional[X]` 대신 `X | None` 사용
- 컬렉션은 `list[str]`, `dict[str, int]` (소문자 내장 제네릭)
- 복잡한 구조는 `dataclass` 또는 Pydantic 모델로

### 네이밍
- 함수·변수: `snake_case`
- 클래스: `PascalCase`
- 상수: `UPPER_SNAKE_CASE`
- 비공개: `_leading_underscore`
- 어댑터 구현체: `{Name}Adapter` (예: `OllamaAdapter`, `KokoroAdapter`)

### 임포트 순서
```python
# 1. 표준 라이브러리
import asyncio
from datetime import datetime

# 2. 서드파티
from fastapi import FastAPI
from sqlmodel import Session

# 3. 로컬
from app.core.orchestrator import SessionOrchestrator
from app.adapters.llm import get_llm_adapter
```

## 2. 비동기

- I/O 바운드(네트워크, 파일, DB)는 async
- CPU 바운드(모델 추론)는 `asyncio.to_thread()` 또는 외부 프로세스(Ollama)
- FastAPI 엔드포인트는 `async def`
- 블로킹 라이브러리(faster-whisper 등)를 async 함수에서 호출할 땐 `await asyncio.to_thread(...)`

```python
async def transcribe(self, audio: bytes) -> STTResult:
    # faster-whisper는 동기 → to_thread로 감쌈
    segments = await asyncio.to_thread(self._model.transcribe, audio)
    ...
```

## 3. 에러 처리

### 원칙
- 빈 `except: pass` 절대 금지
- 예외를 잡으면 반드시 로깅
- 사용자 대면 에러는 한국어, 시스템 로그는 영어

```python
try:
    result = await self.llm.generate(request)
except OllamaConnectionError as e:
    logger.error(f"LLM generation failed: {e}")  # 영어 로그
    raise CoachingUnavailableError("코치 연결에 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")  # 한국어
```

### 타임아웃
- 모든 외부 호출(LLM/STT/TTS/DB)에 타임아웃
- LLM 4초 초과 시 폴백 (PRD 3-1)

```python
try:
    response = await asyncio.wait_for(self.llm.generate(req), timeout=4.0)
except asyncio.TimeoutError:
    logger.warning("LLM timeout, falling back")
    return self._fallback_response()
```

## 4. 한국어/영어 사용 기준

| 위치 | 언어 |
|---|---|
| 사용자 대면 메시지 (TTS 멘트, 채팅 응답, 에러) | 한국어 |
| 코드 주석 | 한국어 또는 영어 (일관성 유지) |
| 로그 메시지 | 영어 |
| 변수·함수명 | 영어 |
| 커밋 메시지 | 영어 (Conventional Commits) |
| 한국어 메시지 상수 | `app/prompts/` 또는 별도 메시지 모듈로 분리 |

한국어 사용자 메시지는 코드에 흩뿌리지 말고 상수로 모은다:

```python
# app/messages.py
MSG_INJURY_EMERGENCY = "즉시 멈추고 119에 연락하세요."
MSG_LLM_TIMEOUT = "잠시 후 답해드릴게요."
```

## 5. 설정·상수

- 매직 넘버 금지. `config.yaml` 또는 상수로
- 기본 사용자 ID: `app/config.py`의 `DEFAULT_USER_ID = 1` (멀티유저 마이그레이션 대비)
- 모델 이름, 박자 간격, 타임아웃 등은 모두 config

```python
# 나쁜 예
await asyncio.sleep(2.0)  # 박자 간격?

# 좋은 예
await asyncio.sleep(self.config.counting.beat_interval_sec)
```

## 6. 함수·클래스 설계

- 한 함수당 50줄 이내 권장 (초과 시 추출)
- 한 파일에 한 책임
- core 모듈은 순수 함수 우선 (테스트 용이)
- 어댑터는 ADR-010 Protocol 시그니처 100% 준수

## 7. 카운팅 박자 (특수 주의)

박자 스케줄러는 `time.sleep` 누적 방식 금지. `time.monotonic()` 기준 절대 시각으로:

```python
# 나쁜 예 (드리프트 발생)
while running:
    beat()
    time.sleep(2.0)  # 처리 시간만큼 누적 오차

# 좋은 예 (절대 시각)
next_beat = time.monotonic()
while running:
    beat()
    next_beat += interval
    await asyncio.sleep(max(0, next_beat - time.monotonic()))
```

## 8. 어댑터 교체 패턴 (LLM/TTS 듀얼)

dict 매핑으로 단순하게. 팩토리 클래스 과용 금지:

```python
# app/adapters/tts/__init__.py
_REGISTRY = {"kokoro": KokoroAdapter, "qwen3": Qwen3TTSAdapter}

def get_tts_adapter(config) -> TTSAdapter:
    name = config.tts.active
    if name not in _REGISTRY:
        raise ValueError(f"Unknown TTS adapter: {name}")
    return _REGISTRY[name]()
```

## 9. TypeScript (UI)

- strict 모드
- 함수형 컴포넌트 + Hooks
- `any` 금지 (`unknown` 후 narrowing)
- 컴포넌트는 PascalCase, 파일명도 PascalCase
- API 호출은 `ui/src/api/`에 집중 (컴포넌트에서 직접 fetch 금지)
- Tailwind 클래스 우선, 커스텀 CSS 최소화
