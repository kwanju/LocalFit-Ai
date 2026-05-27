# LocalFit AI

로컬 LLM 기반 개인 AI 피트니스 코치. 음성 또는 채팅으로 운동 코칭을 받습니다.

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

## 입출력 모드

| 모드 | 입력 | 출력 | 주요 환경 |
|------|------|------|-----------|
| S2S  | 음성 | 음성 | 홈짐 핸즈프리 |
| S2T  | 음성 | 채팅 | 소음 환경 |
| T2S  | 채팅 | 음성 | 마이크 없을 때 |
| T2T  | 채팅 | 채팅 | 조용한 환경 |

## 테스트

```powershell
uv run pytest                        # 전체 (GPU 제외)
uv run pytest -m "not gpu"           # GPU 없는 환경
uv run pytest tests/unit/            # 단위 테스트만
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

- [PRD v3.2](docs/prd-v3.2.md)
- [아키텍처 결정 기록](docs/architecture/adr/README.md)
- [코딩 컨벤션](docs/conventions/coding-style.md)
