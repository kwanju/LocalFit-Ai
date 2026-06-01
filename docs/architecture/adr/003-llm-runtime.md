# ADR-003: LLM 런타임으로 Ollama 채택

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-004 (LLM 모델), ADR-011 (Pipecat), ADR-013 (능동 코치)

## 컨텍스트

로컬 LLM 추론 런타임을 선택해야 한다. v1에서 Ollama가 검증됐다 — 모델 관리(`ollama pull`), warm-up(`keep_alive`), HTTP API(`/api/chat`), `format="json"` 강제, async client 모두 제공.

Pipecat은 `pipecat.services.ollama.OllamaLLMService`를 공식 지원한다. instructor 라이브러리도 Ollama OpenAI-compat 엔드포인트로 직접 결합 가능.

## 결정

- **LLM 런타임 = Ollama 0.5+**
- `keep_alive = 24h` — 메모리 상주로 cold start 회피 (v1에서 4s → 8s 타임아웃 사고 재발 방지)
- `format = "json"` 옵션 적극 사용 (ADR-013 능동 코치 JSON 출력)
- Pipecat `OllamaLLMService` + instructor 결합 — 구조화 출력 + 자동 retry

### 워밍업 정책

- FastAPI lifespan에서 `OllamaLLMService.warmup()` 호출 — 모델 GPU 메모리 로드
- 첫 사용자 요청 전에 완료 (lifespan blocking)
- 실패 시 health endpoint가 `llm: false` 반환

## 결과

### 긍정
- 모델 관리 단순 (`ollama pull qwen3:8b`)
- Pipecat 공식 통합 — 별도 어댑터 작성 불필요
- HTTP/JSON API라 디버깅 쉬움

### 부정
- llama.cpp 직접 사용 대비 약간의 오버헤드 (Ollama 프로세스)
- GPU 메모리 상주 ~6GB (qwen3:8b q4_0) — 24h keep_alive 시 항상 점유

## 대안

| 후보 | 탈락 사유 |
|---|---|
| llama.cpp + 자체 서버 | 모델 관리·warm-up 직접 구현 부담. Ollama가 같은 백엔드(llama.cpp) 사용 |
| vLLM | 단일 사용자엔 over-engineering. 멀티 batch 강점 활용 불가 |
| LM Studio | GUI 위주, HTTP API 표준화 약함 |
| HuggingFace Transformers 직접 | 메모리 효율·warm-up 직접 관리. 생산성 낮음 |
| Ollama (v1과 동일) | 변경 사유 없음 — 유지 ✅ |

## References
- [Ollama GitHub](https://github.com/ollama/ollama)
- [Pipecat OllamaLLMService](https://docs.pipecat.ai/server/services/llm/ollama)
- [Ollama Structured Outputs Guide](https://www.arsturn.com/blog/ollama-structured-output-json-guide)
