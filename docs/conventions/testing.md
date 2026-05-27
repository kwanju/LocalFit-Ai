# 테스트 컨벤션 — LocalFit AI

## 1. 구조

```
tests/
├── conftest.py           # 공통 픽스처, Mock 어댑터
├── unit/                 # 외부 의존 없는 순수 로직
│   ├── test_safety.py    # Safety Guard (LLM 호출 없음)
│   ├── test_counting.py  # 박자 스케줄러
│   └── test_intent.py    # Mock LLM 사용
└── integration/          # 실제 외부 의존
    ├── test_llm_ollama.py    # 실제 Ollama (@pytest.mark.gpu)
    └── test_orchestrator.py  # Mock 어댑터로 흐름 검증
```

## 2. 마킹

외부 의존(GPU, Ollama, 모델)이 있는 테스트는 마킹하여 환경 없을 때 skip:

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "gpu: requires CUDA GPU",
    "ollama: requires running Ollama daemon",
    "slow: slow tests (model loading)",
]
```

```python
@pytest.mark.ollama
@pytest.mark.gpu
async def test_llm_korean_response():
    adapter = OllamaAdapter(config)
    if not await adapter.health():
        pytest.skip("Ollama not available")
    result = await adapter.generate(LLMRequest(messages=[
        LLMMessage(role="user", content="오늘 컨디션 안 좋은데 운동 강도 조정해줘")
    ]))
    assert len(result) > 0
    assert any(c for c in result if '\uac00' <= c <= '\ud7a3')  # 한글 포함 확인
```

실행:
```bash
uv run pytest                      # 전체 (GPU 없으면 자동 skip)
uv run pytest -m "not gpu"         # GPU 테스트 제외
uv run pytest tests/unit           # 단위 테스트만 (빠름)
```

## 3. Mock 어댑터 패턴

ADR-010 Protocol을 준수하는 Mock을 conftest.py에 둔다. core 로직 테스트 시 사용:

```python
# tests/conftest.py
import pytest
from app.adapters.llm.protocol import LLMAdapter, LLMRequest

class MockLLMAdapter:
    """LLMAdapter Protocol 준수 Mock."""
    def __init__(self, canned_response: str = "테스트 응답"):
        self.canned = canned_response
        self.calls = []

    async def generate(self, request: LLMRequest) -> str:
        self.calls.append(request)
        return self.canned

    async def stream(self, request: LLMRequest):
        for ch in self.canned:
            yield ch

    async def health(self) -> bool:
        return True

@pytest.fixture
def mock_llm():
    return MockLLMAdapter()
```

## 4. 한국어 테스트 데이터

부상 키워드, 의도 분류, 컨디션 입력 등은 실제 한국어로 테스트:

```python
INJURY_KEYWORDS_TEST = [
    ("무릎이 아파요", "중간"),
    ("어깨가 쑤셔", "중간"),
    ("숨이 안 쉬어져", "응급"),
    ("좀 뻐근하네", "낮음"),
]

@pytest.mark.parametrize("text,expected_level", INJURY_KEYWORDS_TEST)
def test_injury_detection(text, expected_level):
    guard = SafetyGuard()
    assert guard.assess(text).level == expected_level
```

## 5. 우선순위 (P0)

전부 테스트하려 하지 마라. 1인 프로젝트에서 테스트는 다음 우선순위:

1. **Safety Guard** — 부상 감지는 안전 직결. 최우선. 커버리지 높게
2. **Counting Engine** — 박자 정확도 ±10% (PRD 7-1)
3. **Intent Classifier** — 5종 분류 정확도
4. **Orchestrator 흐름** — Mock 어댑터로 모드별 라우팅
5. 어댑터 — smoke test 수준 (실제 모델 1회 호출)

UI 테스트는 P0에서 생략 가능 (수동 확인). P1에서 검토.

## 6. 커버리지 목표

- core 모듈 (safety, counting, intent): 80%+
- 어댑터: smoke test (정상 호출 1개)
- API: 주요 엔드포인트 1개씩
- 전체 강박 금지 — 안전·핵심 로직 집중
