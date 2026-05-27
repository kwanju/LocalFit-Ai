# AGENTS.md — LocalFit AI 코딩 에이전트 가이드

> 이 파일은 코딩 에이전트(Claude Code, Codex, Cursor, Aider 등)가 작업 전 **반드시** 읽는 진입점이다.
> Claude Code는 `CLAUDE.md`, Cursor는 `.cursorrules`로도 같은 내용을 참조한다.

---

## 0. 프로젝트 한 줄 요약

LocalFit AI는 로컬 LLM 기반 개인 AI 피트니스 코치 앱이다.
**1인 개인 프로젝트**이며, 화면 없이(음성) 또는 소리 없이(채팅) 운동 코칭을 받는 4-모드 입출력이 핵심이다.

## 1. 너의 역할

너는 이 프로젝트의 코드 작성 보조자다. 시니어 아키텍트가 내린 설계 결정(ADR)과 PRD를 충실히 구현하는 것이 임무다. 설계를 임의로 바꾸지 않는다.

## 2. 첫 작업 전 반드시 읽을 것

순서대로:

1. `docs/prd-v3.2.md` — 제품 요구사항. **단일 진실 소스(Single Source of Truth)**
2. `docs/architecture/adr/README.md` — 16개 아키텍처 결정 인덱스
3. 현재 작업과 직접 관련된 개별 ADR만 (전부 읽지 말 것 — 컨텍스트 절약)
4. `docs/conventions/coding-style.md` — 코딩 규약
5. 현재 작업의 `docs/agent-tasks/phase-XX.md` 작업 명세

작업과 무관한 ADR은 컨텍스트에 넣지 마라. 예: LLM 어댑터 작업에 UI(ADR-009)는 불필요.

## 3. 절대 하지 말 것 (위반 시 작업 거부 또는 revert)

- ❌ PRD에 없는 기능 임의 추가
- ❌ ADR과 충돌하는 결정 임의 변경 (충돌 발견 시 **사용자에게 보고하고 멈춤**)
- ❌ 멀티유저 가정 코드 (`user_id` 파라미터, 인증, 권한 등) — 단일 사용자다 (ADR-002)
- ❌ "혹시 모르니까" 추상화 레이어 추가 — YAGNI
- ❌ 라이브러리를 ADR과 다른 것으로 교체 제안 (사용자 명시 승인 없이)
- ❌ `# TODO: 나중에 구현` placeholder — 함수는 완전히 구현하거나 아예 만들지 마라
- ❌ 폴더 구조 임의 변경 (`src/`, `lib/` 등으로 — 아래 4번 구조 고정)
- ❌ 마이크로서비스, K8s, CI/CD 같은 1인 프로젝트 부적합 패턴

## 4. 폴더 구조 (고정 — 변경 금지)

```
localfit-ai/
├── app/                  # Python 백엔드
│   ├── main.py           # FastAPI 진입점
│   ├── config.py         # config.yaml 로딩
│   ├── api/              # HTTP/WebSocket 엔드포인트만
│   ├── core/             # 도메인 로직 (외부 의존 0)
│   ├── adapters/         # 외부 의존 격리 (llm/stt/tts)
│   ├── db/               # SQLite + SQLModel
│   ├── prompts/          # LLM 프롬프트
│   └── utils/
├── ui/                   # React PWA (별도 컨텍스트)
├── scripts/              # 운영 스크립트 (.bat, setup)
├── tests/                # pytest
└── docs/                 # PRD, ADR, 컨벤션
```

방향성 규칙: `api → core → adapters → 외부`. `core`는 `adapters`를 호출하되, `adapters`는 `core`를 import하지 않는다. `core`는 순수 Python (FastAPI/SQLModel/Ollama import 금지).

## 5. 핵심 기술 결정 요약 (상세는 각 ADR)

| 영역 | 결정 | ADR |
|---|---|---|
| 언어 | Python 3.11+ | 001 |
| LLM 런타임 | Ollama | 003 |
| LLM 모델 | Qwen 3.5 9B + Gemma 4 E4B (config로 전환) | 004 |
| STT | faster-whisper large-v3-turbo | 005 |
| TTS | Kokoro + Qwen3-TTS (config로 전환) | 006 |
| VAD | silero-vad | 012 |
| DB | SQLite + SQLModel | 007 |
| 백엔드 | FastAPI + WebSocket | 008 |
| UI | React + Vite + TS + Tailwind PWA | 009 |
| 패키지 매니저 | uv (Python), pnpm (JS) | 015 |
| 환경 | Windows 네이티브, uv venv (Docker/WSL2 미사용) | 016 |

## 6. 외부 호출 정책 (강제)

- 모든 LLM/STT/TTS 호출은 **어댑터 경유** (직접 `ollama`, `faster_whisper` 호출 금지) — ADR-010
- DB 접근은 **Repository 경유** (단순 단일 SELECT는 예외 허용) — ADR-007
- 모델 이름은 **config.yaml 참조** (하드코딩 금지) — ADR-004/005/006
- 외부 통신은 `127.0.0.1`로 제한 (P0) — ADR-002

## 7. 코딩 컨벤션 (요약, 상세는 coding-style.md)

- 타입 힌트 필수, 함수 50줄 이내 권장
- f-string 사용, 매직 넘버 금지 (config/상수)
- 사용자 대면 메시지 = 한국어, 시스템 로그 = 영어
- 예외는 잡되 무시 금지 (`logger.error` 필수)
- FastAPI 엔드포인트는 `async def`
- 카운팅 박자는 `time.monotonic()` 기반 (sleep 누적 금지)

## 8. 의존성 추가 정책

새 의존성 추가 시 **사용자 확인 필수**. 추가 요청 시 이유 + 대안 검토 결과를 함께 제시. uv/pnpm으로만 추가.

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

## 11. Git 정책

- 한 작업 = 한 커밋 (또는 작업별 브랜치 → 검토 후 머지)
- Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- ADR 변경은 별도 커밋 (`docs(adr): ...`)
