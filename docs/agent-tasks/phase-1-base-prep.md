# Phase 1 — v1 base 정리 + 의존성 추가 + 폴더 구조 재배치

## 목적

v1 출시본을 base로, ADR-012 의존 방향과 폴더 구조에 맞게 재배치하고 v3 신규 의존성을 추가한다.

## 사전 조건

- 브랜치 `v3-rewrite` 체크아웃 상태
- `git status` clean (untracked 파일은 `.claude/`, `xtts_dev_smoke.wav` 정도만)

## 관련 ADR

- ADR-012 (Domain Adapter + Pipecat Service 분리)
- ADR-017 (uv + pnpm)

## 작업 항목

### 1-1. 의존성 추가 (사용자 확인 후)

```bash
uv add "pipecat-ai[silero,whisper]>=1.3.0"
uv add "instructor>=1.6"
uv add "openai>=1.50"               # instructor가 Ollama OpenAI-compat 사용
uv add "loguru>=0.7"
```

phase-1 진입 시점에 Pipecat PyPI 최신 stable 확인 후 정확한 버전 확정. 1.3.0 이상이면 API 안정성 확보.

검증: `uv sync --all-extras` → 성공 + `uv tree | grep pipecat` 출력 확인.

### 1-2. 폴더 구조 재배치

신규 폴더 생성:
- `app/pipecat_services/`
- `app/pipecat_services/processors/`

v1 자체 Protocol 폐기:
- `app/adapters/llm/protocol.py` → 삭제 또는 비움
- `app/adapters/stt/protocol.py` → 삭제 또는 비움
- `app/adapters/tts/protocol.py` → 삭제 또는 비움

v1 adapter 클래스 이름 변경 (도메인 어댑터 명명 규칙):
- `app/adapters/llm/ollama.py` → `ollama_client.py`, 클래스 `OllamaAdapter` → `OllamaClient`
- `app/adapters/stt/faster_whisper.py` → `faster_whisper_client.py`, 클래스 `FasterWhisperAdapter` → `FasterWhisperClient`
- `app/adapters/tts/qwen3.py` → `qwen3_client.py`, 클래스 `Qwen3TTSAdapter` → `Qwen3TTSClient`

import 경로 갱신 (전체).

### 1-3. v1 자체 파이프라인 코드 보존 + 폐기 표시

- `app/api/ws_coach.py` — 헤더에 `# DEPRECATED — Phase 2에서 ws_voice.py로 대체` 주석 추가, 코드 그대로 두되 라우터에서 분리(또는 import만 안 함)
- `app/core/orchestrator.py` — 동일하게 폐기 표시. CountingEngine·SafetyGuard·CoachContext가 사용하는 일부 함수만 남기고 audio·VAD·sentence 처리 부분은 phase-2 진입 전 제거

### 1-4. 로깅 — loguru 도입

- `app/utils/logging.py` 신규 — loguru 설정 (ADR-018)
- `app/main.py` lifespan 진입 시 `setup_logging()` 호출
- 기존 `logging.getLogger(...)` 사용처는 `from loguru import logger`로 치환 (단 Pipecat 내부 logging은 intercept handler로)

### 1-5. config.yaml 갱신

v1 config를 base로 다음 변경:
- `llm.active`, `llm.qwen3`, `llm.gemma3` 제거 → `llm.model: "qwen3:8b"` 단일
- `tts.active: "qwen3"`, `tts.qwen3.attn_implementation: "sdpa"`, `tts.qwen3.device_map: "cuda:0"`, `tts.qwen3.streaming: true` 추가
- `tts.xtts` 섹션 제거 (v2 자산)
- `vad` 섹션 ADR-007 형식으로 갱신
- `coach.proactive_opener: true`, `coach.instructor.max_retries: 2` 추가

### 1-6. v1 테스트 정리

- `tests/test_orchestrator*.py` 중 audio chunk·VAD 직접 테스트는 phase-2에서 Pipecat MockTransport로 재작성 → 일단 skip 마크 + TODO
- `tests/test_counting*.py` — 그대로 유지 (CountingEngine 재활용)
- `tests/test_safety*.py`, `tests/test_intent*.py` — 그대로
- `tests/test_repositories*.py` — 그대로

## Definition of Done

- [ ] `uv sync --all-extras` 성공
- [ ] `uv tree`에 pipecat-ai · instructor · loguru 표시
- [ ] 폴더 구조 ADR-012와 일치 (`app/adapters/`·`app/pipecat_services/`·`app/core/`)
- [ ] `app/core/`에 Pipecat·FastAPI·SQLModel·transformers import 0건 (grep 검증)
- [ ] `app/adapters/`에 `app/core/` import 0건 (grep 검증)
- [ ] ruff 통과
- [ ] pytest 비-GPU 스위트 — CountingEngine·Repository·SafetyGuard 테스트 통과 (orchestrator 관련은 skip OK)
- [ ] git commit `chore(phase-1): v1 base 재배치 + Pipecat·instructor·loguru 의존성 추가`

## 소요 추정

반나절~1일.

## 다음 phase

[Phase 2 — Pipecat 셸](phase-2-pipecat-shell.md)
