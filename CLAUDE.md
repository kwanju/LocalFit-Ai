# CLAUDE.md — LocalFit AI v3-rewrite 코딩 에이전트 가이드

> 이 파일은 코딩 에이전트(Claude Code, Codex, Cursor, Aider 등)가 작업 전 **반드시** 읽는 진입점이다.
> `AGENTS.md`는 같은 내용을 참조한다.

---

## 0. 프로젝트 한 줄 요약

LocalFit AI는 로컬 LLM 기반 개인 AI 피트니스 코치 데스크탑 앱이다.
**1인 개인 프로젝트**이며, 화면 없이(음성) 또는 소리 없이(채팅) 운동 코칭을 받는 4-모드 입출력이 핵심.

## 0-1. 현재 상태 (2026-06-07 업데이트)

- **v1 (MVP, P0)는 출시 완료 후 `_archive/v1/`에 보존**됨 — 코드는 그대로 base로 재활용.
- **v2 (단일 프로그램 패키징)는 폐기.** pywebview + PyInstaller 빌드·검증 이슈 누적으로 ROI 낮다고 판단. v2 시점 산출물(ADR-020/021, XTTS 어댑터, desktop.py, spec)은 `backup/v2-trial` 브랜치에 보존.
- **v3-rewrite (현재 브랜치)** — v1 base에서 ADR을 백지에서 다시 발행. 19개 ADR + PRD v4 + 새 phase 명세.
- **v3 마무리 단계** — phase 1-8 구현 + 사용자 통합 검증 + 후속 fix 진행 중. v3 master 동결 직전.
- **faster-qwen3-tts 통합 = 완료** (2026-06-08, 커밋 `697801b`). 첫 청크 4818ms→884ms. 후속 버그(카운트 뭉침·드롭, 휴식 침묵, 음색 일관성, 5세트 수정, 플랭크 시간) 수정 완료. 회고는 `docs/_archive/v3/faster-qwen3-tts.md`.
- **다음 작업**:
  - `docs/future/v4-vision.md` — v4 비전 deep interview. (faster-qwen3 끝났으니 진입 가능)
- **회고 자료**: `docs/retrospectives/2026-06-07-v3-lessons.md` — v3 에서 배운 4가지 원칙 + 무한 굴레 패턴 5가지. **다음 프로젝트 시작 전 반드시 읽기**.
- **핵심 변경**:
  - 음성 파이프라인 = **Pipecat 전면 채택** (ADR-011) — 인터럽트·turn 검출 외주
  - TTS = **faster-qwen3-tts 단독** (ADR-006) — MeloTTS 제거(2026-06-08). 폴백 없음. 음색 일관성 do_sample=false + xvec_only.
  - 능동 코치 = **instructor + JSON 구조화 출력** (ADR-013) — 사용자 발화로 카운팅 자동 시작
  - 카운팅 = 다회 세트 + 자동 휴식 + 메트로놈/타이머 (ADR-014, 2026-06-07 확장)
  - 데스크탑 패키징 = 폐기, 브라우저 PWA만 (ADR-010)

## 1. 너의 역할

너는 이 프로젝트의 코드 작성 보조자다. PM 겸 시니어 아키텍트(사용자)가 내린 설계 결정(ADR 19개)과 PRD v4를 충실히 구현하는 것이 임무다. **설계를 임의로 바꾸지 않는다.**

## 2. 첫 작업 전 반드시 읽을 것

순서대로:

1. **`docs/retrospectives/2026-06-07-v3-lessons.md` — v3 에서 배운 실수와 피해야 할 패턴** (먼저 읽고 같은 실수 반복 X)
2. `docs/prd-v4.md` — 제품 요구사항. **단일 진실 소스**
3. `docs/architecture/adr/README.md` — 19개 ADR 인덱스
4. 현재 작업과 **직접 관련된 ADR만** (전부 읽지 말 것 — 컨텍스트 절약)
5. `docs/conventions/coding-style.md` — 코딩 규약 (v1 자산 재활용)
5-1. **`docs/testing-strategy.md` — 시나리오 기반 심층 테스트 전략** (버그를 사용자가 아니라 에이전트가 먼저 잡는 절차. 버그 보고 받으면 여기 §4 루프대로 직접 시나리오 구동·로그검토·박제)
6. 현재 작업의 `docs/agent-tasks/phase-XX-*.md` 작업 명세 (있다면)
7. **v4 시작 시**: `docs/future/v4-vision.md` (deep interview 질문 §6 참조)

> faster-qwen3-tts 통합은 완료(2026-06-08). 회고/실측은 `docs/_archive/v3/faster-qwen3-tts.md`.

v1 시점 ADR이 궁금하면 `_archive/v1/` 참조. v3-rewrite ADR 결정과 충돌하면 **v3가 우선**.

## 3. 절대 하지 말 것 (위반 시 작업 거부 또는 revert)

- ❌ PRD v4에 없는 기능 임의 추가
- ❌ ADR과 충돌하는 결정 임의 변경 (충돌 발견 시 **사용자에게 보고하고 멈춤**)
- ❌ 멀티유저 가정 코드 (`user_id` 파라미터, 인증, 권한 등) — 단일 사용자다 (ADR-002)
- ❌ "혹시 모르니까" 추상화 레이어 추가 — YAGNI
- ❌ 라이브러리를 ADR과 다른 것으로 교체 제안 (사용자 명시 승인 없이)
- ❌ `# TODO: 나중에 구현` placeholder — 함수는 완전히 구현하거나 아예 만들지 마라
- ❌ 폴더 구조 임의 변경 (`src/`, `lib/` 등으로 — 아래 4번 구조 고정)
- ❌ 마이크로서비스, K8s, CI/CD 같은 1인 프로젝트 부적합 패턴
- ❌ 데스크탑 패키징(pywebview, PyInstaller, Electron, Tauri) 재시도 — ADR-010에서 폐기
- ❌ **자체 음성 파이프라인 작성** — Pipecat 사용 (ADR-011). v1 자체 `/ws/coach` 패턴 재도입 금지
- ❌ Domain Core에 Pipecat·FastAPI·SQLModel·transformers import — ADR-012 위반
- ❌ XTTS v2 / Kokoro 재도입 — ADR-006에서 폐기 (Qwen3-TTS만 사용)

## 4. 폴더 구조 (고정 — 변경 금지)

```
localfit-ai/
├── app/                        # Python 백엔드
│   ├── main.py                 # FastAPI 진입점 + lifespan
│   ├── config.py               # config.yaml 로딩
│   ├── api/                    # HTTP 엔드포인트 + ws_voice (Pipecat 마운트)
│   ├── core/                   # 순수 도메인 (외부 의존 0 — Pipecat/FastAPI/SQLModel 모두 X)
│   ├── adapters/               # 도메인 어댑터 (모델 직접 호출, Pipecat 의존성 0)
│   │   ├── llm/                # OllamaClient (instructor binding 포함)
│   │   ├── stt/                # FasterWhisperClient + 16kHz 리샘플러
│   │   └── tts/                # Qwen3TTSClient (SDPA + 보이스 클로닝)
│   ├── pipecat_services/       # Pipecat 통합 레이어
│   │   ├── ollama_service.py   # StructuredOllamaService
│   │   ├── whisper_service.py
│   │   ├── qwen3_tts_service.py
│   │   └── processors/         # FrameProcessor 상속 (SafetyGuard, ConfirmRule, ActionDispatcher, CountingInject)
│   ├── db/                     # SQLite + SQLModel + Repository
│   ├── prompts/                # LLM 시스템 프롬프트
│   └── utils/
├── ui/                         # React PWA (별도 컨텍스트)
├── scripts/                    # setup-models.bat, dev.bat
├── tests/                      # pytest
└── docs/                       # PRD, ADR, conventions, agent-tasks
```

### 의존 방향 규칙 (ADR-012 강제)

```
api → pipecat_services → adapters → 외부 모델
                       ↓
                       core (순수 도메인)
                       ↓
                       db (Repository)
```

- `core`는 다른 어떤 것도 import 금지 (FastAPI·Pipecat·SQLModel·transformers 모두 X)
- `adapters`는 `core` import 금지 (역참조 방지)
- `pipecat_services`는 `adapters` + `core` 모두 import 가능
- `api`는 모든 계층 import 가능, 단 직접 모델 호출은 금지 (`pipecat_services` 경유)

## 5. 핵심 기술 결정 요약 (상세는 각 ADR)

| 영역 | 결정 | ADR |
|---|---|---|
| 언어 | Python 3.11+ | 001 |
| LLM 런타임 | Ollama | 003 |
| LLM 모델 | qwen3:8b 단일 | 004 |
| STT | faster-whisper large-v3-turbo, 16kHz 강제 | 005 |
| TTS | Qwen3-TTS + SDPA + sentence-streaming | **006** |
| VAD/Turn | silero-vad (+ Smart Turn P1) | 007 |
| DB | SQLite + SQLModel | 008 |
| 백엔드 | FastAPI + Pipecat FastAPIWebsocketTransport | 009 |
| UI | React + Vite PWA, 데스크탑 패키징 X | 010 |
| **음성 파이프라인** | **Pipecat 전면 채택** | **011** |
| 어댑터 계층 | Domain Adapter + Pipecat Service 분리 | 012 |
| **능동 코치** | **instructor + JSON 구조화 + 액션 디스패치** | **013** |
| 카운팅 | 메트로놈/타이머 + LLM 트리거 | 014 |
| 패키지 매니저 | uv + pnpm | 017 |
| 환경 | Windows 네이티브, uv venv | (v1 계승) |

## 6. 외부 호출 정책 (강제)

- 모든 LLM/STT/TTS 호출은 **Pipecat Service 또는 Domain Adapter 경유** (직접 `ollama`, `faster_whisper`, `transformers` import 금지 in api/core)
- DB 접근은 **Repository 경유** (단순 단일 SELECT는 예외 허용) — ADR-008
- 모델 이름은 **config.yaml 참조** (하드코딩 금지) — ADR-004/005/006
- 외부 통신은 `127.0.0.1`로 제한 (P0) — ADR-002

## 7. 코딩 컨벤션 (요약, 상세는 `docs/conventions/coding-style.md`)

- 타입 힌트 필수, 함수 50줄 이내 권장
- f-string 사용, 매직 넘버 금지 (config/상수)
- 사용자 대면 메시지 = **한국어**, 시스템 로그 = **영어**
- 예외는 잡되 무시 금지 (`logger.error` 필수) — ADR-018
- FastAPI 엔드포인트는 `async def`
- 카운팅 박자는 `time.monotonic()` 기반 (sleep 누적 금지)
- 로깅 = loguru (표준 logging 직접 사용 금지)

## 8. 의존성 추가 정책

새 의존성 추가 시 **사용자 확인 필수**. 추가 요청 시 이유 + 대안 검토 결과를 함께 제시. uv/pnpm으로만 추가.

v3에서 신규 의존성:
- `pipecat-ai[silero,whisper]` — ADR-011
- `instructor` — ADR-013
- `openai` (instructor 의존, Ollama OpenAI-compat) — ADR-013
- `loguru` — ADR-018
- `faster-qwen3-tts` — ADR-006 (Qwen3-TTS faster 백엔드, 2026-06-07)
- UI dev: `vitest`, `jsdom`, `@testing-library/react|dom|jest-dom` — UI 로직 테스트 (`cd ui && pnpm test`). UI↔백엔드 경계 버그 회귀 방어 (2026-06-08, `docs/testing-strategy.md`)

v1 대비 제거:
- `coqui-tts`, `torchcodec` (XTTS 폐기)
- `pywebview`, `pyinstaller` (v2 폐기)

## 9. 매 작업 완료 시 보고 형식

```markdown
## 작업 완료 보고
### 변경 파일
- (파일 목록 + 신규/수정)
### ADR 준수
- ADR-XXX: ✅/❌ + 근거
### 테스트 실행
- pytest 결과 + smoke test 결과
### 사용자 확인 필요 사항
- (있으면)
### 자가 체크리스트 (code-review-checklist.md 기준)
- A~H 각 항목 ✅/❌/N/A
```

## 10. 모르겠으면

- 추측하지 말고 **사용자에게 질문**
- ADR과 PRD에 답이 없으면 결정을 **사용자에게 미루기**
- ADR끼리 충돌하거나 PRD와 ADR이 충돌하면 **즉시 멈추고 보고**
- v1 자산을 그대로 가져올지 v3 결정에 맞게 재작성할지 모호하면 **v3 ADR 결정 우선**

## 11. Git 정책

- 현재 브랜치: `v3-rewrite` (v1 출시본 `4231564` base)
- 백업 브랜치: `backup/v2-trial` (v2 진행 commit 20개 보존, 절대 force-delete 금지)
- 한 작업 = 한 커밋 (또는 작업별 브랜치 → 검토 후 머지)
- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- ADR 변경은 별도 커밋 (`docs(adr): ...`)
- 사용자 명시 승인 없이 master에 push 금지

## 12. v1 자산 재활용 정책

v1 base에는 다음이 그대로 있다 — 재활용 우선, 폐기는 ADR 결정에 따를 때만:

| 영역 | 재활용? |
|---|---|
| `app/core/counting.py` (CountingEngine) | ✅ 그대로 (ADR-014) |
| `app/core/safety.py` (SafetyGuard 키워드) | ✅ 그대로 + 강화 (ADR-013) |
| `app/core/intent.py` (한자 후처리 `strip_non_korean_cjk`) | ✅ 그대로 (ADR-013) |
| `app/db/*` (SQLModel + Repository) | ✅ 그대로 (ADR-008) |
| `app/api/*` (REST 엔드포인트) | ✅ 그대로 (ADR-009) |
| `app/api/ws_coach.py` (자체 WebSocket 핸들러) | ❌ 폐기 → `ws_voice.py` (ADR-009/011) |
| `app/core/orchestrator.py` (audio chunk·VAD·sentence 처리) | ❌ 폐기 (ADR-011, Pipecat가 처리) |
| `app/adapters/{llm,stt,tts}/protocol.py` (v1 자체 Protocol) | ❌ 폐기 → Pipecat Service + Domain Adapter (ADR-012) |
| `ui/*` (React PWA) | ✅ 거의 그대로, WS 메시지 포맷만 Pipecat에 맞게 조정 (ADR-010) |
| `tests/*` | 부분 재활용 (CountingEngine·Repository·SafetyGuard 테스트는 그대로) |

자세한 마이그레이션은 `docs/agent-tasks/phase-1-base-prep.md` 참조.
