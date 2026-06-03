# LocalFit AI

로컬 LLM 기반 개인 AI 피트니스 코치. 음성 또는 채팅으로 운동을 주도적으로 이끌어줍니다.

- **인터넷 없이 동작** — Ollama가 GPU에서 qwen3:8b를 로컬 추론
- **4가지 입출력 모드** — 음성↔음성, 채팅↔음성, 채팅↔채팅, 음성↔채팅
- **능동 코치** — 사용자가 먼저 말하길 기다리지 않고 세션 시작 시 오늘의 운동을 제안
- **카운팅 엔진** — 메트로놈/타이머 박자 안내, 세트 완료 후 자동 follow-up
- **운동 캘린더** — 연간 히트맵으로 운동 빈도·강도를 한눈에 확인

---

## 아키텍처

```
브라우저 (React PWA)
    ↕ JSON WebSocket  /ws/voice
FastAPI
    └─ Pipecat Pipeline
          ├─ SileroVAD → faster-whisper STT
          ├─ SafetyGuard → ConfirmRule → StructuredOllama (instructor + qwen3:8b)
          ├─ ActionDispatcher → CountingEngine
          └─ SentenceAggregator → MeloTTS / Qwen3-TTS
    └─ REST API  /api/*
          └─ SQLite (SQLModel)
```

**4계층 분리 (ADR-012)**

```
api → pipecat_services → adapters → 외부 모델
                       ↓
                       core (순수 도메인, 외부 의존 0)
                       ↓
                       db (Repository)
```

---

## 요구 사항

| 항목 | 최소 |
|---|---|
| OS | Windows 10/11 (WSL2 미사용) |
| GPU | NVIDIA RTX (CUDA) — STT·TTS 추론 필수 |
| RAM | 16 GB+ |
| Python | 3.11+ |
| Node.js | 18+ |
| Ollama | 최신 |

---

## 빠른 시작

### 1. 설정 파일 복사

```bash
cp config.example.yaml config.yaml
# config.yaml 열어 GPU 장치, 모델 경로 등 확인
```

### 2. 의존성 설치

```bash
# Python 패키지 (uv)
uv sync

# UI 패키지 (pnpm)
cd ui && pnpm install && cd ..
```

### 3. 모델 다운로드

```bash
# LLM
ollama pull qwen3:8b

# STT·TTS 모델
uv run python scripts/setup-models.py
```

> TTS 기본값은 MeloTTS(경량). Qwen3-TTS 보이스 클론을 쓰려면 `config.yaml`에서 `tts.active: qwen3`으로 변경.

### 4. 개발 서버 실행

```bash
scripts/dev.bat
```

백엔드 `http://127.0.0.1:8000`, 프론트엔드 `http://127.0.0.1:5173` 로 자동으로 열립니다.

---

## 주요 기능

### 4가지 모드

| 모드 | 입력 | 출력 | 주요 용도 |
|---|---|---|---|
| S2S | 음성 | 음성 | 핸즈프리 운동 코칭 |
| C2S | 채팅 | 음성 | 조용한 환경에서 음성 응답 |
| C2C | 채팅 | 채팅 | 소음 환경, 이어폰 없을 때 |
| S2C | 음성 | 채팅 | 마이크는 있지만 스피커 없을 때 |

UI 우상단 토글로 세션 중 실시간 전환 가능.

### 능동 코치

- 세션 시작 시 캘린더 패턴·최근 컨디션 기반 운동 제안 (70자 이내)
- `propose_set` 발화 → 사용자 확답 → `start_counting` 자동 시작
- 세트 완료 후 다음 세트/휴식/종료 자동 follow-up
- 부상 키워드 감지 시 즉시 카운팅 중단 + 안전 안내

### 카운팅 엔진

- 메트로놈 모드: 풀업·푸시업·스쿼트 박자 안내
- 타이머 모드: 플랭크 등 지속 운동
- 화면 큰 숫자 + 박자음 + 격려 멘트 (랜덤 선택)

### 운동 캘린더 (`/calendar`)

- GitHub 잔디 스타일 연간 히트맵 — 운동 볼륨 기반 level 0~4 강도 색상
- 날짜 클릭 → 세션 상세 모달 (시작/종료 시각, 운동·세트·렙, 컨디션)
- 최근 7일 이내 데이터만 있으면 1주일 strip 뷰 자동 전환
- 캘린더 패턴이 능동 코치 컨텍스트에 자동 주입 ("지난주처럼 푸시업 어떠세요?")

---

## 설정 주요 항목

```yaml
# config.yaml (config.example.yaml에서 복사)

llm:
  model: "qwen3:8b"          # Ollama 모델 이름
  timeout_sec: 8.0

stt:
  model: "large-v3-turbo"    # faster-whisper 모델
  device: "cuda"             # cuda | cpu

tts:
  active: "melo"             # melo(기본) | qwen3(보이스 클론)
  melo:
    device: "cuda:0"

vad:
  threshold: 0.5             # 음성 감지 임계값 (0~1)
  min_silence_ms: 400        # 발화 종료 판정 침묵 구간

coach:
  proactive_opener: true     # 세션 시작 시 코치 능동 인사
  calendar_pattern_weeks: 4  # 캘린더 패턴 분석 기간(주)
```

전체 옵션은 [`config.example.yaml`](config.example.yaml) 참조.

---

## 개발

```bash
# 백엔드만
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# UI만
cd ui && pnpm dev

# 린트 / 포맷
uv run ruff check app/
uv run ruff format app/

# UI 타입 체크 + 빌드
cd ui && pnpm typecheck && pnpm build
```

### 폴더 구조

```
localfit-ai/
├── app/
│   ├── api/              # FastAPI 엔드포인트 + WebSocket
│   ├── core/             # 순수 도메인 로직 (외부 의존 0)
│   ├── adapters/         # 모델 호출 래퍼 (Pipecat 의존 0)
│   ├── pipecat_services/ # Pipecat 통합 레이어
│   ├── db/               # SQLite + SQLModel + Repository
│   └── prompts/          # LLM 시스템 프롬프트
├── ui/                   # React 18 + Vite + Tailwind PWA
├── tests/                # pytest (unit + integration)
├── docs/                 # PRD v4, ADR 20개, 컨벤션
└── config.example.yaml
```

---

## 테스트

```bash
# 비-GPU 자동 테스트 전체 (~288 passed)
uv run pytest -m "not gpu and not ollama and not integration" -q

# 캘린더·컨텍스트 단위 테스트
uv run pytest tests/test_calendar_metrics.py tests/test_coach_context_calendar.py -v

# GPU 필요 테스트 (RTX 환경)
uv run pytest -m gpu -v
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| LLM 런타임 | Ollama + qwen3:8b |
| STT | faster-whisper large-v3-turbo + 16kHz 강제 리샘플 |
| TTS | MeloTTS (기본) / Qwen3-TTS SDPA (보이스 클론) |
| VAD / Turn | silero-vad (Pipecat 통합) |
| 음성 파이프라인 | Pipecat FastAPIWebsocketTransport |
| 구조화 출력 | instructor + Pydantic (JSON schema validation + auto-retry) |
| 백엔드 | FastAPI + uvicorn |
| DB | SQLite + SQLModel (Repository 패턴) |
| UI 프레임워크 | React 18 + Vite + Tailwind CSS |
| 운동 캘린더 | react-activity-calendar |
| Python 패키지 | uv |
| UI 패키지 | pnpm |

---

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/prd-v4.md`](docs/prd-v4.md) | 제품 요구사항 (단일 진실 소스) |
| [`docs/architecture/adr/README.md`](docs/architecture/adr/README.md) | ADR 20개 인덱스 |
| [`docs/conventions/coding-style.md`](docs/conventions/coding-style.md) | 코딩 규약 |
| [`docs/qa-checklist-v4.md`](docs/qa-checklist-v4.md) | QA 체크리스트 |
| [`SETUP-RUNBOOK.md`](SETUP-RUNBOOK.md) | 초기 환경 세팅 A→Z 가이드 |
