# ADR-017: 패키지 매니저 — uv + pnpm

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-001 (Python), ADR-010 (UI)

## 컨텍스트

v1에서 uv (Python) + pnpm (JS) 조합이 검증됐다. v3 변경 사유 없음.

## 결정

- **Python = uv 0.5+** (`pyproject.toml` + `uv.lock`)
- **JS = pnpm 11+** (`ui/package.json` + `ui/pnpm-lock.yaml`, workspace)
- **Python 의존성 추가**: `uv add <pkg>` — 사용자 확인 필수 (CLAUDE.md §의존성 정책)
- **JS 의존성 추가**: `pnpm add -F ui <pkg>` — 동일
- **lock 파일 commit**: `uv.lock`, `pnpm-lock.yaml` 모두 git 추적
- **torch + cu128 인덱스 핀**: `[tool.uv.sources]`에 `pytorch-cu128` 인덱스 명시 (RTX 5090 sm_120 호환, v1 검증)

### 주요 의존성 (v3 신규/변경)

```toml
# pyproject.toml (요약)
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlmodel>=0.0.20",
    "pydantic>=2.9",
    "loguru>=0.7",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "ollama>=0.4",
    "pipecat-ai[silero,whisper]>=1.3.0",    # ★ 신규 (1.x 안정 단계)
    "instructor>=1.6",                         # ★ 신규
    "openai>=1.50",                            # instructor 의존 (Ollama OpenAI-compat)
]

[project.optional-dependencies]
gpu = [
    "torch>=2.4",
    "torchaudio>=2.4",
    "faster-whisper>=1.2",
    "transformers>=4.45",
    "librosa>=0.10",
    "soundfile>=0.12",
]

[tool.uv.sources]
torch = { index = "pytorch-cu128" }
torchaudio = { index = "pytorch-cu128" }

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

### v1 대비 제거 의존성

- `coqui-tts` (XTTS v2 폐기 — ADR-006)
- `torchcodec` (XTTS 합본 부담)
- `pywebview`, `pyinstaller` (v2 패키징 폐기 — ADR-002, ADR-010)

## 결과

### 긍정
- v1 검증 조합 유지 — 학습 곡선 0
- uv 빠른 설치 + lock 결정성
- pnpm workspace로 ui/ 분리 깔끔
- torch cu128 핀 — RTX 5090 호환

### 부정
- pipecat-ai 의존성 추가 — 설치 시 30+ 어댑터 옵션 dependencies 폭발 가능 (`[silero,whisper]` extras로 한정)
- instructor 의존성 추가 — openai SDK가 함께 따라옴 (Ollama OpenAI-compat 사용)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| pip + virtualenv | uv 대비 느림, lock 부재 |
| poetry | uv가 더 빠르고 표준 PEP 621 (pyproject.toml) |
| npm/yarn | pnpm이 디스크 효율·workspace 깔끔 |

## References
- [uv](https://docs.astral.sh/uv/)
- [pnpm workspace](https://pnpm.io/workspaces)
- v1 known_constraints — RTX 5090 cu128 핀 정책 계승
