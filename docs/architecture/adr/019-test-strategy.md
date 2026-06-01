# ADR-019: 테스트 전략 — pytest + Pipecat MockTransport + 어댑터 mock

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-011 (Pipecat), ADR-012 (어댑터)

## 컨텍스트

v1은 pytest 136 passed (비-GPU 스위트)로 검증됐다. v3는 Pipecat 전면 채택과 instructor 도입으로 테스트 표면이 일부 변경된다.

## 결정

### 테스트 프레임워크 = pytest 8+ (+ pytest-asyncio + pytest-mock)

### 계층별 테스트 패턴

| 계층 | 테스트 방식 | 도구 |
|---|---|---|
| Domain Core | 순수 단위 테스트 (외부 의존 0) | pytest |
| Domain Adapter | mock 의존성 + 실제 호출 통합 (GPU mark) | pytest + responses (HTTP) |
| Pipecat Service | mock client 주입 + frame in/out 검증 | pytest + Pipecat 테스트 헬퍼 |
| Pipecat Pipeline | MockTransport로 frame 시퀀스 검증 | pytest + Pipecat MockTransport |
| FastAPI 엔드포인트 | TestClient | pytest + httpx.AsyncClient |
| WebSocket | Pipecat 파이프라인 end-to-end with mock | pytest |

### GPU 의존 테스트 분리

- `pytest.mark.gpu` — RTX 5090 같은 GPU 환경에서만 실행
- 기본 `pytest` 실행은 비-GPU만 (CI 친화)
- GPU 테스트는 `pytest -m gpu` 명시

### 어댑터 mock 대체성 (ADR-012 정신 계승)

도메인 어댑터(`ollama_client`, `faster_whisper_client`, `qwen3_client`)는 mock 가능 인터페이스 유지:

```python
# tests/conftest.py
@pytest.fixture
def mock_llm_client():
    client = Mock(spec=OllamaClient)
    client.generate_structured = AsyncMock(return_value=CoachResponse(text="좋아요", actions=[]))
    return client
```

### Pipecat MockTransport 활용

```python
from pipecat.transports.network.mock import MockTransport

async def test_pipeline_dispatches_start_counting():
    transport = MockTransport()
    pipeline = build_pipeline(
        llm=StructuredOllamaService(mock_llm_client),
        stt=mock_stt_service,
        tts=mock_tts_service,
        transport=transport,
    )
    # send mock user text frame
    await transport.push_user_text("푸시업 10회 시작")
    # assert action dispatched
    assert counting_engine.start.called_with("푸시업", 10)
```

### PRD §7-1 자동 검증 항목 (v3 계승)

1. 4-모드 동작 — 각 모드별 텍스트/오디오 frame 라운드트립 테스트
2. 카운팅 박자 정확도 ±10% — `time.monotonic()` 기반 단위 테스트 (v1 자산 재활용)
3. 일정 변경 5종 — LLM mock으로 `propose_set` 응답 시나리오 테스트
4. 부상 키워드 즉시 중단 — `SafetyGuardProcessor` 단위 테스트 + 통합
5. LLM 지연 4초 fallback — `OllamaClient.generate_structured` timeout mock + 카운팅 연속 검증

### 수동 검증 (사용자)

- 실제 마이크 캡처 음질
- TTS 자연스러움
- LLM 응답 한국어 일관성
- 능동 코치 제안 적절성
- end-to-end 지연 (RTX 5090 환경)

자동화 어려운 부분은 `docs/qa-checklist-v4.md`에 명시.

### 커버리지 목표

- Domain Core: 90%+
- Domain Adapter: 70%+ (외부 호출 mock)
- Pipecat Service: 60%+ (frame 시나리오 중심)
- 통합·UI: 정량 목표 없음 (수동 위주)

### CI 정책

- MVP는 CI 미설치 (단일 사용자 1인 프로젝트, GitHub Actions 무료 한도 충분히 활용 가능하나 P1)
- 로컬 pre-commit hook으로 ruff + pytest --no-gpu 실행 권장

## 결과

### 긍정
- v1 pytest 자산 재활용 — 학습 곡선 0
- Pipecat MockTransport로 파이프라인 end-to-end 시나리오 테스트 가능
- mock 대체성으로 GPU 없이도 대부분 테스트 가능

### 부정
- Pipecat MockTransport API 안정성 미검증 (Pipecat 0.x)
- instructor retry 시나리오는 LLM 응답 mock으로만 검증 가능 — 실제 LLM 동작 검증은 수동

## 대안

| 후보 | 탈락 사유 |
|---|---|
| pytest 대신 unittest | pytest 표준, fixture 풍부 |
| 통합 테스트만 (단위 테스트 생략) | 회귀 디버깅 비용 큼 |
| Hypothesis (property-based) | 도입 가치 있으나 P1 (학습 비용) |

## References
- [pytest 8](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Pipecat 테스트 가이드](https://docs.pipecat.ai/server/utilities/testing)
- v1 `tests/` — 136 passed 자산
