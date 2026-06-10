# Architecture Decision Records (ADR) — v3

LocalFit AI **v3-rewrite** 아키텍처 결정 이력. v1 출시 후 v2 패키징(pywebview + PyInstaller) 진행 중 누적된 빌드·검증 이슈와 능동 코치/카운팅 트리거 미구현을 계기로, v1 출시본을 base로 **전체 ADR을 백지에서 다시 발행**한다.

v1 시점 ADR 16개와 v2 시점 ADR 020/021은 `_archive/v1/`에 보존된다(history 보존, 참고용).

## 형식

각 ADR은 다음 섹션을 포함한다.

- **Status**: Proposed / Accepted / Deferred / Superseded / Deprecated
- **Context**: 결정이 필요한 배경
- **Decision**: 채택된 결정
- **Consequences**: 결과 (긍정·부정 모두)
- **Alternatives**: 검토했으나 탈락한 대안과 이유
- **References**: 오픈소스 프로젝트·논문·블로그 출처

## 변경 정책

- 한 번 Accepted된 ADR은 **수정하지 않는다**. 결정을 바꾸려면 새 번호로 ADR을 발행하고, 이전 ADR의 Status를 `Superseded by ADR-XXX`로 갱신한다.
- v1 자산은 `_archive/v1/`에 frozen 상태로 보존한다 — 결정 회고·근거 추적용. 새 결정은 v3 시리즈에서만 한다.

## 원칙 (v3-rewrite 진입 시)

- **바퀴 재발명 금지** — 활성 유지보수 중인 오픈소스 프레임워크/라이브러리를 우선 채택. 자체 구현은 도메인 로직(SafetyGuard·CountingEngine·SessionOrchestrator)에 한정.
- **단일 사용자 가정 유지** — 멀티유저·인증·권한 코드 작성 금지 (ADR-002).
- **데스크탑 패키징 미시도** — v2의 pywebview + PyInstaller 실험은 폐기. 브라우저 PWA를 그대로 사용 (ADR-010).
- **지연 목표 보존** — PRD v4 §4-1 (S2S 2~3s, C2C 0.8~1.5s)을 모든 결정의 임계 가정으로 둔다.

## 인덱스

| # | 제목 | 상태 |
|---|---|---|
| [001](001-main-language.md) | 메인 언어로 Python 채택 | Accepted |
| [002](002-mvp-topology.md) | 토폴로지 — 데스크탑 단독, 127.0.0.1 | Accepted |
| [003](003-llm-runtime.md) | LLM 런타임 — Ollama | Accepted |
| [004](004-llm-models.md) | LLM 모델 — qwen3:8b 단일 모델 | Superseded by 029 |
| [005](005-stt.md) | STT — faster-whisper large-v3-turbo + 16kHz 강제 | Accepted |
| [006](006-tts.md) | TTS — Qwen3-TTS + SDPA 어텐션 + sentence-streaming | Accepted |
| [007](007-vad-turn-detection.md) | VAD + Turn Detection — silero-vad + Pipecat Smart Turn | Accepted |
| [008](008-db-orm.md) | DB — SQLite + SQLModel | Accepted |
| [009](009-backend-transport.md) | 백엔드 — FastAPI + Pipecat FastAPIWebsocketTransport | Accepted |
| [010](010-ui-framework.md) | UI — React + Vite PWA (브라우저, 데스크탑 패키징 없음) | Accepted |
| [011](011-voice-pipeline-pipecat.md) | **음성 파이프라인 — Pipecat 전면 채택** | Accepted |
| [012](012-domain-adapter-contract.md) | Pipecat 위 도메인 어댑터·서비스 계약 | Accepted |
| [013](013-active-coach.md) | **능동 코치 — instructor + JSON 구조화 출력 + 액션 디스패치** | Accepted |
| [014](014-counting-engine.md) | 카운팅 엔진 — 메트로놈/타이머 + LLM 트리거 | Accepted |
| [015](015-model-concurrency.md) | 모델 동시 상주 — Ollama keep_alive 24h + GPU 메모리 예산 | Accepted |
| [016](016-model-download.md) | 모델 다운로드 — 첫 실행 setup 스크립트 + HF/Ollama 캐시 | Accepted |
| [017](017-package-manager.md) | 패키지 매니저 — uv + pnpm | Accepted |
| [018](018-logging-observability.md) | 로깅·관측성 — loguru + 파일 + 지연 메트릭 | Accepted |
| [019](019-test-strategy.md) | 테스트 전략 — pytest + Pipecat MockTransport + 어댑터 mock | Accepted |
| [020](020-workout-calendar.md) | **운동 캘린더 시각화 — react-activity-calendar + 강도 히트맵** | Accepted |

## v4 시리즈 인덱스 (진행 중 — 2026-06-10~)

v4 방향은 `docs/future/v4-vision.md` §0-2 deep interview 결과로 확정. v4 ADR 은 v3 와 충돌 시 **v4 가 우선**(v3 master 동결). native 의존 ADR(027/030/031)은 **Phase v4-0 Tauri 탐사**(`docs/agent-tasks/v4/phase-0-tauri-spike.md`) 통과 후 Accepted.

| # | 제목 | 상태 | supersedes |
|---|---|---|---|
| 021 | v4 진입 — 비전·스코프·마이그레이션 + UX 3모드(S2C 제거) | Proposed | — |
| 022 | Google Calendar 연동 (OAuth2 Desktop, 외부 API) | Proposed | — |
| 023 | 컨디션 트래킹 — 자가보고 체크인 (외부 건강 API 없음) | Proposed | — |
| 024 | 운동 플랜 — 주간 목표 + 조정은 확인 | Proposed | — |
| 025 | 영속 메모리 — SQLite 구조화+자유텍스트, 부상/제약 전량 주입 | Proposed | — |
| 026 | 운동 종목 — v3 4종 고정 유지 | Deferred | — |
| 027 | 능동 알림 + 백그라운드 스케줄러 (native) | Proposed (탐사 의존) | — |
| 028 | 첫 세션 대화형 체력검증 | Proposed | — |
| 029 | LLM 모델 — qwen3.5:9b (config 교체) | **Accepted** (2026-06-10) | 004 |
| 030 | 모델 lifecycle — on-demand 로드/언로드 | Proposed (탐사 의존) | 015 |
| 031 | UI 플랫폼 — native 데스크탑(Tauri) | Proposed (탐사 의존) | 010 |

> 표기: native 의존 ADR 은 탐사 go 전까지 Proposed. 탐사 no-go 시 027/030/031 은 폐기/수정되고 010/015 가 유지된다.

## v1과 비교한 주요 변경

| 영역 | v1 | v3 |
|---|---|---|
| 음성 파이프라인 | 자체 작성 (FastAPI WebSocket + 직접 어댑터) | **Pipecat 전면 채택** (ADR-011) |
| 어댑터 계약 | 자체 Protocol (ADR-010 v1) | Pipecat FrameProcessor 상속 (ADR-012) |
| TTS | Qwen3-TTS / XTTS v2 시도(50s 지연 → CPML 라이선스) | **Qwen3-TTS + SDPA + sentence-streaming** (ADR-006) |
| 능동 코치 | 자체 JSON parser (ADR-021 v1) | instructor + Pydantic 검증 + retry (ADR-013) |
| 카운팅 트리거 | 미구현 (UI 버튼만) | LLM action `start_counting` 자동 디스패치 (ADR-014) |
| 패키징 | v2 pywebview + PyInstaller 시도 → 폐기 | 브라우저 PWA만 (ADR-010) |
| LLM 모델 | qwen3.5:9b + gemma3:e4b 듀얼 | qwen3:8b 단일 (ADR-004) |
| Turn Detection | silero VAD silence | silero + Pipecat Smart Turn (intonation) (ADR-007) |
| 운동 기록 시각화 | 없음 | 캘린더 히트맵 + 능동 코치 활용 (ADR-020) |

> ⚠️ ADR-020은 v2 시점에도 같은 번호로 "데스크탑 패키징" 결정이 있었으나, v2 폐기와 함께 `_archive/v1/020-desktop-packaging.md`로 보존됐다. v3-rewrite의 ADR-020은 "운동 캘린더"로 새 결정.

## 관련 문서

- `docs/architecture/adr/_archive/v1/` — v1 시점 ADR 16개 + v2 시점 020/021 보존
- `docs/_archive/v1/prd-v3.2.md` — v1 PRD (참고용)
- `docs/prd-v4.md` — v3-rewrite PRD
- `docs/conventions/` — coding-style·testing·code-review-checklist (v1과 공유)
- `docs/agent-tasks/` — v3 phase 작업 명세
- `CLAUDE.md` / `AGENTS.md` — 코딩 에이전트 진입점 (v3-rewrite 신규)
