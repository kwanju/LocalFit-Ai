# Task: Phase 2A — LLM 어댑터

## 배경 자료
- `AGENTS.md`
- `docs/architecture/adr/003-llm-runtime.md`
- `docs/architecture/adr/004-llm-models.md`
- `docs/architecture/adr/010-adapter-interfaces.md`
- `docs/architecture/adr/011-model-concurrency.md`

## 작업 범위
1. `app/adapters/llm/protocol.py` — LLMAdapter Protocol + LLMMessage, LLMRequest dataclass (ADR-010 명세 그대로)
2. `app/adapters/llm/ollama.py` — OllamaAdapter (Qwen 3.5 / Gemma 4 둘 다 모델명 파라미터로 처리)
3. `app/adapters/llm/__init__.py` — config 기반 어댑터 반환 (active_model 사용)
4. `tests/integration/test_llm_ollama.py` — @pytest.mark.ollama, 한국어 응답 검증
5. CLI smoke test: `python -m app.adapters.llm.ollama "안녕"` 동작

## 제약
- `ollama` 파이썬 패키지 사용 (직접 HTTP 금지)
- 모델 이름 하드코딩 금지 — config.yaml의 llm.active_model
- keep_alive 동적 override 지원 (LLMRequest.keep_alive)
- generate() + stream() + health() 모두 구현
- 타임아웃 적용 (coding-style.md 3번)

## 비범위
- Intent Classifier (Phase 3B에서 이 어댑터 사용)
- 프롬프트 템플릿 (Phase 3)

## 완료 기준
- pytest 통과 (Ollama 없으면 skip)
- CLI 한국어 응답 확인
- Protocol 시그니처 100% 일치

## 자가 보고
AGENTS.md 9번. checklist A·D·E·F·H 확인.
