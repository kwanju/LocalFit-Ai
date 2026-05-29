# LocalFit AI

로컬 LLM 기반 개인 AI 피트니스 코치. 음성 또는 채팅으로 운동 코칭을 받습니다.

> **상태**: MVP(P0) 구현 완료 — Phase 1~6 종료. 자동 검증(PRD 7-1 5종) 통과, 비-GPU 스위트 136 passed. 출시 전 실음성·청취 등 수동 검증만 잔여 — [QA 체크리스트](docs/qa-checklist.md) 참조.

## 요구 사항

- Windows 10/11 (ADR-016)
- Python 3.11+
- NVIDIA GPU (RTX 5090 권장, CUDA 12.8+)
- [uv](https://docs.astral.sh/uv/) 패키지 매니저
- [Ollama](https://ollama.com/) (LLM 런타임)
- [Node.js](https://nodejs.org/) + [pnpm](https://pnpm.io/) (UI 개발 시)

## 셋업

### 1. 저장소 클론 후 설정 파일 복사

```powershell
cp config.example.yaml config.yaml
# config.yaml을 열어 필요한 값 수정
```

### 2. Python 가상환경 및 의존성 설치

```powershell
uv sync --extra llm --extra stt --extra tts --extra vad
```

### 3. Ollama 모델 다운로드

```powershell
ollama pull qwen3.5:9b
ollama pull gemma4:e4b
```

### 4. 백엔드 실행

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. UI 실행 (개발)

```powershell
cd ui
pnpm install
pnpm dev
```

> 백엔드와 UI를 한 번에 띄우려면 `scripts\dev.bat`을 사용하세요.

## 입출력 모드

모드 명명: 입력·출력 채널을 `S`(음성)·`C`(채팅)로 표기 (PRD 2-1).

| 모드 | 입력 → 출력 | 주요 환경 |
|------|------------|-----------|
| S2S    | 음성 → 음성 | 집·홈짐 핸즈프리 |
| C2S ★ | 채팅 → 음성 | 헬스장 (폰 입력 + 이어폰 코칭) |
| C2C    | 채팅 → 채팅 | 심야·도서관 등 완전 무음 |
| S2C    | 음성 → 채팅 | 조용히 답만 보고 싶을 때 |

## 테스트

```powershell
uv run pytest -m "not gpu and not ollama"   # 자동 검증 스위트 (GPU·Ollama 불필요, 136 passed)
uv run pytest tests/unit/                    # 단위 테스트만
uv run pytest                                # 전체 (GPU + Ollama 서버 필요)
```

## 프로젝트 구조

```
localfit-ai/
├── app/
│   ├── main.py          # FastAPI 진입점
│   ├── config.py        # config.yaml 로딩
│   ├── api/             # HTTP/WebSocket 엔드포인트
│   ├── core/            # 도메인 로직 (외부 의존 0)
│   ├── adapters/        # LLM·STT·TTS 어댑터
│   ├── db/              # SQLite + SQLModel
│   ├── prompts/         # LLM 프롬프트 템플릿
│   └── utils/
├── ui/                  # React PWA
├── scripts/             # 운영 스크립트 (.bat)
├── tests/
└── docs/                # PRD, ADR, 컨벤션
```

## 문서

- [PRD v3.2](docs/prd-v3.2.md) — 단일 진실 소스
- [아키텍처 결정 기록 (ADR)](docs/architecture/adr/README.md)
- [코딩 컨벤션](docs/conventions/coding-style.md)
- [셋업 런북](SETUP-RUNBOOK.md)
- [QA 체크리스트 (출시 검증)](docs/qa-checklist.md)
