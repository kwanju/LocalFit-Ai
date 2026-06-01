# ADR-016: 모델 다운로드 — 첫 실행 setup 스크립트 + HF/Ollama 캐시

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-003 (Ollama), ADR-005 (STT), ADR-006 (TTS), ADR-017 (uv)

## 컨텍스트

세 모델은 각각 다른 곳에서 다운로드된다:

| 모델 | 다운로드 위치 | 크기 |
|---|---|---|
| qwen3:8b | Ollama 레지스트리 (`~/.ollama/models`) | ~5GB |
| faster-whisper large-v3-turbo | HF Hub (`~/.cache/huggingface/hub`) | ~1.6GB |
| Qwen3-TTS-1.7B | HF Hub | ~3.4GB |
| **합계** | | **~10GB** |

첫 실행 시 자동 다운로드되면 사용자가 "어떤 게 진행 중인지 모르겠음" → setup 스크립트로 명시적 처리.

## 결정

### setup 스크립트 = `scripts/setup-models.bat` (Windows)

```bat
@echo off
echo [1/3] Downloading qwen3:8b via Ollama...
ollama pull qwen3:8b

echo [2/3] Downloading faster-whisper large-v3-turbo via HF...
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cuda', compute_type='float16')"

echo [3/3] Downloading Qwen3-TTS via HF...
uv run python -c "from transformers import AutoModel; AutoModel.from_pretrained('Qwen/Qwen3-TTS-12Hz-1.7B-Base', attn_implementation='sdpa', device_map='cuda:0')"

echo Done. Total ~10GB.
```

### 캐시 위치

- Ollama: `~/.ollama/models` (Windows: `%USERPROFILE%\.ollama\models`)
- HF: `~/.cache/huggingface/hub` (또는 `HF_HOME` 환경변수로 override)
- 캐시 공유 — Ollama·HF 모두 표준 위치 사용. 이전 작업의 캐시 재활용 가능

### 첫 실행 자동 다운로드

- FastAPI startup 시 `setup-models.bat` 실행 안 함 (사용자가 수동 실행)
- 만약 모델이 없으면 `/health`가 503 + 안내 메시지 ("scripts/setup-models.bat 실행 필요")
- 단, faster-whisper / Qwen3-TTS는 transformers가 자동 다운로드 가능 — 첫 호출 시 다운로드 (느리지만 동작)

### 오프라인 가정

- 모델 다운로드 = 1회 셋업 (네트워크 필요)
- 이후 추론 = 완전 오프라인 (PRD v4 P0 가정)

## 결과

### 긍정
- 사용자가 다운로드 진행 상황을 명시적으로 봄
- 캐시 표준 위치 — 재설치·이전 시 재활용
- 첫 호출 자동 fallback도 동작 — setup 안 해도 결국 작동

### 부정
- 사용자가 setup 스크립트를 모르고 첫 실행 시 멍하니 기다림 (자동 다운로드 fallback 시 분 단위 지연)
- 모델 업데이트(예: qwen3:8b → qwen3:8.1b) 시 수동 재실행 필요

## 대안

| 후보 | 탈락 사유 |
|---|---|
| 첫 실행 자동 다운로드 + 진행률 UI | 사용자가 backend ↔ frontend 동시 띄워야 함, MVP 복잡도 |
| 모델을 git LFS로 번들 | 10GB 저장소 — git 운영 부적합 |
| HF Hub 미러 (자체 서버) | 단일 사용자엔 over-engineering |

## References
- [Ollama pull](https://github.com/ollama/ollama/blob/main/docs/api.md#pull-a-model)
- [HF cache 가이드](https://huggingface.co/docs/huggingface_hub/guides/manage-cache)
- [faster-whisper 모델 변환·캐시](https://github.com/SYSTRAN/faster-whisper#model-conversion)
