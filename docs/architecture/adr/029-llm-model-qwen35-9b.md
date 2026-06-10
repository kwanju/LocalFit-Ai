# ADR-029: LLM 모델 — qwen3:8b → qwen3.5:9b (config 교체)

- **상태**: Proposed (2026-06-10)
- **Supersedes**: ADR-004 (qwen3:8b 단일 모델)
- **관련 ADR**: ADR-003 (Ollama), ADR-013 (능동 코치 JSON 출력), ADR-030 (모델 lifecycle on-demand)

## 컨텍스트

v4 는 tool-use(캘린더·DB·플랜을 LLM 도구로 호출, ADR-022/024/025)를 강화한다. ADR-004 의 qwen3:8b 는 한국어·JSON 출력이 안정적이나, v4 의 function-calling 비중 증가에 맞춰 더 최신·강력한 동급 모델을 재검토할 가치가 있다.

2026-06 기준 조사 결과:
- **Qwen3.5** (2026-02 출시) — dense 0.8B/2B/4B/9B/27B + MoE(35B-A3B 등). 9B dense 가 8B 대비 한국어·tool-use 개선.
- v1 이 실제로 **qwen3.5:9b** 를 듀얼 구성으로 썼던 이력 — 9B 회귀에 검증 근거.
- 모델 두뇌(LLM)와 음성(faster-qwen3-tts)은 이름만 같고 별개 — LLM 교체가 TTS 에 영향 없음.

하드웨어 제약(ADR-030): VRAM 16GB 베이스라인에서 STT+TTS 와 **세션 중 동시 로드**되어야 하므로 모델 크기 상한이 있다(dense 9B ~6-7GB, MoE 35B-A3B ~21GB 는 베이스라인 초과).

## 결정

- **기본 LLM = `qwen3.5:9b`** (Ollama tag, q4_K_M 양자화)
- `config.llm.model: "qwen3.5:9b"` 단일 키 (ADR-004 의 "새 모델 = 별도 ADR + config 한 줄" 정책 계승)
- **config 교체로 하드웨어 적응** (분기 코드 없음, YAGNI):
  - 고사양(VRAM 24GB+) 사용자는 `qwen3.6:35b-a3b`(MoE, ~21GB) 등으로 상향 가능 — 속도(3B active)+품질 이득
  - 저사양은 `qwen3:8b`/`qwen3.5:4b` 등으로 하향
- `think: false` 기본값 계승 (Qwen thinking 모드 비활성화)
- instructor `from_provider("ollama/qwen3.5:9b")`
- `keep_alive` 는 ADR-030(on-demand)에서 재정의 — ADR-004 의 `24h` 는 **무효**

## 결과

### 긍정
- v4 tool-use·한국어 추론 개선 기대 (9B > 8B)
- v1 9B 사용 이력으로 회귀 위험 낮음
- config 한 줄로 16GB~32GB 하드웨어 스펙트럼 흡수 (친구 공유 §6-1 대응, 분기 코드 0)
- TTS 와 독립 — 음성 스택 무변경

### 부정
- 8B→9B 로 VRAM +1GB 내외 (미미, 16GB 베이스라인 내)
- 새 모델 = 프롬프트/JSON 스키마 회귀 검증 필요 (ADR-013 능동 코치 출력 재검증)
- tool-use 정확도가 실측으로 부족하면 재교체 가능성

## 대안

| 후보 | 탈락 사유 |
|---|---|
| qwen3:8b 유지 (ADR-004) | v4 tool-use 비중 증가에 9B 가 유리. 동급이라 전환 비용 낮음 |
| Gemma 4 (Google) | function-calling 기본 지원하나 **한국어 검증 부족**(사용자 대면 필수) + 새 계열 재튜닝 + 멀티모달 오디오 불필요(STT 별도) |
| qwen3.6:35b-a3b MoE 기본 | ~21GB 로 16GB 베이스라인 동시 상주 불가 — config 상향 옵션으로만 |
| qwen3.5:27b dense | 지연·VRAM 과대 — 베이스라인·latency 위험 |

## References
- [Qwen3.5 — Ollama / LM Studio](https://lmstudio.ai/models/qwen3.5)
- [Qwen3.6 35B-A3B VRAM guide](https://willitrunai.com/blog/qwen-3-6-vram-requirements)
- [Best Open Source LLM for Korean 2026](https://www.siliconflow.com/articles/en/best-open-source-llm-for-korean)
- v1 known_constraints — qwen3.5:9b 듀얼 구성 사용 이력
