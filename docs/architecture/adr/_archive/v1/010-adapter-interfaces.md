# ADR-010: 핵심 어댑터 인터페이스 명세

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-003 (Ollama), ADR-005 (faster-whisper), ADR-006 (Kokoro)

## 컨텍스트

PRD 4-1의 "STT/TTS는 독립 모듈, LLM 어댑터 레이어 필수"를 코드 수준에서 보장해야 한다. 모델 교체(Kokoro→Coqui, Qwen→Llama)가 어댑터 교체로 끝나야 한다.

YAGNI 원칙에 따라 어댑터는 **꼭 필요한 3종만** (LLM, STT, TTS) 정의한다. VAD, Intent Classifier, Counting Engine은 현재 후보 1개씩이라 추상화하지 않는다.

## 결정

다음 인터페이스를 Python `Protocol`로 정의한다 (ABC보다 가벼움, duck typing 호환).

### LLM 어댑터

```python
# app/adapters/llm/protocol.py
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    temperature: float = 0.7
    max_tokens: int = 512
    keep_alive: str = "1h"

class LLMAdapter(Protocol):
    async def generate(self, request: LLMRequest) -> str: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]: ...
    async def health(self) -> bool: ...
```

### STT 어댑터

```python
# app/adapters/stt/protocol.py
@dataclass
class STTResult:
    text: str
    language: str
    duration_ms: int

class STTAdapter(Protocol):
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> STTResult: ...
    async def health(self) -> bool: ...
```

### TTS 어댑터

```python
# app/adapters/tts/protocol.py
@dataclass
class TTSRequest:
    text: str
    voice: str = "default"
    speed: float = 1.0

class TTSAdapter(Protocol):
    async def synthesize(self, request: TTSRequest) -> bytes: ...  # WAV bytes
    async def stream(self, request: TTSRequest) -> AsyncIterator[bytes]: ...
    async def health(self) -> bool: ...
```

## 결과

### 긍정
- 모델 교체 시 어댑터 구현체만 교체 (1일 이내)
- 테스트 시 Mock 어댑터로 대체 가능
- Protocol 사용으로 상속 강제 없음 — 유연성 ↑

### 부정
- `stream()` 미사용 가능성 — MVP에선 `generate()` 위주, stream은 P1에서 활용

## 대안

| 후보 | 탈락 사유 |
|---|---|
| ABC (abstractmethod) | 상속 강제, 엄격. Protocol이 더 모던하며 가벼움 |
| 모든 컴포넌트에 어댑터 (VAD, Intent까지) | YAGNI 위반. 후보 모델 1개일 땐 직접 구현 |
| 함수 시그니처 기반 duck typing (Protocol 없음) | 타입 안정성 ↓, IDE 자동완성 ↓ |
