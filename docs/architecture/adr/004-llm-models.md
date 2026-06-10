# ADR-004: LLM 모델 — qwen3:8b 단일 모델

- **상태**: Superseded by ADR-029 (2026-06-10) — 원 Accepted 2026-05-31. v4 는 qwen3.5:9b 사용.
- **관련 ADR**: ADR-003 (Ollama), ADR-013 (능동 코치 JSON 출력), ADR-029 (qwen3.5:9b 후속)

## 컨텍스트

v1은 듀얼 모델(Qwen 3.5 9B + Gemma 4 E4B) 전환형으로 설계했으나 실사용에서 단일 모델로 충분함이 드러났다. 또한 ADR-013(능동 코치)에서 `format="json"` 안정성이 핵심인데, 두 모델의 JSON 일관성을 모두 검증·유지하는 비용이 크다.

2026년 5월 기준 한국어 코칭 + JSON 구조화 출력 + 8B 클래스 모델 후보:

| 모델 | VRAM(q4) | JSON format 지원 | 한국어 | 비고 |
|---|---|---|---|---|
| qwen3:8b | ~5GB | ✅ Ollama format=json 안정 | ✅ 우수 | Qwen 팀 최신, instructor 검증 |
| qwen3:14b | ~9GB | ✅ | ✅ 우수 | 8b 대비 품질 +α, 지연 +α |
| gemma3:e4b | ~3GB | △ (간헐적 schema drift) | ○ | 가벼움, JSON 신뢰도 8b 미만 |
| llama3.3:8b | ~5GB | ✅ | △ 보통 | 한국어 약함 |

## 결정

- **단일 모델 = `qwen3:8b`** (Ollama tag, q4_K_M 양자화)
- 모델 전환형 코드(`config.llm.active`) 폐기 — 단일 모델 직접 참조
- `config.llm.model: "qwen3:8b"` 단일 키
- `keep_alive: "24h"` (ADR-003)
- `think: false` 기본값 — Qwen3 thinking 모드 비활성화 (v1 known_constraint 계승)
- Pipecat `OllamaLLMService(model="qwen3:8b")` + instructor `from_provider("ollama/qwen3:8b")`

### 모델 전환 정책

- 새 모델 도입 시: 별도 ADR로 결정 후 `config.llm.model` 한 줄 변경
- 8B vs 14B 트레이드오프(품질 vs 지연)는 사용자 검증 후 별도 ADR로 결정

## 결과

### 긍정
- 모델 전환 코드 폐기로 어댑터 단순화
- JSON 출력 신뢰도 일관 — ADR-013 능동 코치 핵심 가정 보존
- Pipecat·instructor 통합 단순 (모델 1개만 등록)

### 부정
- 향후 모델 변경 시 검증·튜닝 부담 (단일 모델이라 회귀 시 즉시 영향)
- gemma3 같은 작은 모델 fallback 없음 — VRAM 부족 환경(8GB 이하)은 별도 모델 ADR로 분리

## 대안

| 후보 | 탈락 사유 |
|---|---|
| qwen3:8b + gemma3:e4b 듀얼 (v1) | JSON 신뢰도 차이로 능동 코치 검증 비용 2배. 실사용 가치 검증 안 됨 |
| qwen3:14b 단독 | 지연 1.5~2배 — PRD v4 §4-1 목표(S2S 2~3s) 위험 |
| qwen3:4b 단독 | 능동 코치 JSON·context 이해 부족 위험 |

## References
- [Qwen3 Ollama Tags](https://ollama.com/library/qwen3)
- [Instructor Ollama Integration](https://python.useinstructor.com/integrations/ollama/)
- v1 known_constraints — Qwen thinking 모드 비활성화 정책 계승
