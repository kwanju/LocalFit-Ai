# LocalFit AI — PRD v4 (v3-rewrite)

> **개인 AI 피트니스 코치**
> Product Requirements Document · v4
> 2026-05-31 · 로컬 LLM · 4-모드 입출력 · 맨몸운동 코칭

---

> **v4 변경 요약**
> 본 문서는 v3.2(아키텍처 반영본)를 base로, v1 출시 후 v2 패키징 실험 폐기·능동 코치 미구현·TTS 50초 지연 이슈를 회고하여 **v3-rewrite** 시점에 새로 발행됐다.
>
> **주요 변경**
> - 음성 파이프라인 = **Pipecat 전면 채택** (인터럽트·turn 검출·sentence aggregation 외주)
> - TTS = Qwen3-TTS 복귀 + **SDPA 어텐션 + sentence-streaming**으로 지연 해결 (XTTS 폐기)
> - 능동 코치 = instructor + JSON 구조화 출력으로 **구현 완수** (v1 미구현 해소)
> - 카운팅 = 메트로놈/타이머 유지 + LLM 액션 트리거 (사용자 발화로 시작)
> - LLM = qwen3:8b 단일 (듀얼 폐기)
> - 데스크탑 패키징 = 폐기 → 브라우저 PWA만 유지
>
> v3.2와 제품 요구사항(4-모드, 카운팅, 안전 정책)은 동일. 기술 결정만 갱신.

---

# PART 1 — CORE PRD

## 1. 제품 개요

LocalFit AI는 로컬 LLM으로 동작하는 개인 AI 피트니스 코치다. 사용자의 환경(집·헬스장·새벽 등)에 맞춰 입력과 출력 모드를 자유롭게 조합할 수 있고, AI 코치가 운동 카운팅, 대화 기반 일정 조정, 안전 모니터링, 능동 제안을 수행한다.

### 1-1. 제품 한 줄 정의

> *"화면을 안 봐도 운동할 수 있고, 말을 못 해도 코칭받을 수 있는, **능동적으로 제안하는** 오프라인 AI 트레이너."*

### 1-2. 핵심 가정 (v4 갱신)

- 로컬 LLM (Ollama + qwen3:8b 단일)으로 충분한 코칭 품질 + JSON 구조화 출력이 나온다 `[ADR-003, 004, 013]`
- faster-whisper(large-v3-turbo) STT + Qwen3-TTS(SDPA+streaming) TTS로 PRD §4-1 지연 목표 충족 `[ADR-005, 006]`
- 음성 파이프라인은 Pipecat이 인터럽트·turn 검출·sentence aggregation을 안정적으로 처리 `[ADR-011]`
- 사용자 본인 1인 사용 (멀티유저 코드 미작성) `[ADR-002]`
- 부상 발화는 LLM 응답 외에 규칙 기반으로 즉시 처리 (Safety Guard 인터셉터)
- RTX 5090(32GB) + 64GB RAM 환경에서 모델 동시 상주 가능 `[ADR-015]`

### 1-3. MVP 범위 및 배포 전략

| 구분 | MVP (P0) | 확장 (P1+) |
|---|---|---|
| 토폴로지 | 데스크탑 단독, 백엔드 `127.0.0.1` | 폰 PWA + Tailscale |
| UI 접근 | 데스크탑 브라우저 (PWA) | 폰 브라우저 동시 |
| 환경 | Windows 네이티브 + NVIDIA, uv venv | (동일) |
| 패키징 | 브라우저 PWA만 (데스크탑 셸 폐기) | (P1에서 재검토) |
| 사용자 | 본인 1인 | 각자 자기 인스턴스 |

---

## 2. 입출력 모드 매트릭스 ★ 핵심

사용자 환경에 따라 입력 채널(음성·채팅)과 출력 채널(음성·채팅)을 자유 조합한다. 구현상 STT/TTS 노드의 on/off 조합이 곧 모드 `[ADR-009]`.

### 2-1. 4가지 모드

| 모드 | 입력 → 출력 | 주요 사용 환경 | 활용 예시 |
|---|---|---|---|
| S2S | 음성 → 음성 | 집·홈짐 | 핸즈프리. 화면 없이 코치와 대화 |
| C2S ★ | 채팅 → 음성 | 헬스장 | 폰 입력, 이어폰 코칭 |
| C2C | 채팅 → 채팅 | 새벽·도서관 | 완전 무음 |
| S2C | 음성 → 채팅 | 조용히 답만 보고 싶을 때 | 드물게 |

### 2-2. 모드 전환 정책

- 기본 모드: 사용자가 환경 설정에서 지정
- 자동 전환 없음 — 사용자 명시적 변경
- 세션 중 전환 가능

### 2-3. C2S 특화 설계

| 요소 | C2S 모드 설계 |
|---|---|
| 채팅 입력 | 원터치 빠른 응답 버튼 우선 ("세트 완료", "한 세트 더") |
| AI 카운팅 | 화면 큰 숫자 + 이어폰 음성 카운팅 동시 |
| 인터럽트 | 화면 탭 1회로 코치 음성 즉시 중단 (Pipecat broadcast_interruption) |
| 휴식 알림 | 음성 + 화면 진동 |
| 폼 기록 | 음성 폼 코칭 대신 채팅 4지선다 |

### 2-4. 모드별 기능 가용성

| 기능 | S2S | C2S | C2C | S2C |
|---|---|---|---|---|
| AI 음성 카운팅 | ✓ | ✓ | 화면 대체 | ✓ |
| 코칭 대화 | ✓ | ✓ | ✓ | ✓ |
| 능동 제안 | ✓ | ✓ | ✓ | ✓ |
| 인터럽트 | 음성 | 화면 탭 | 화면 탭 | 음성 |
| 부상 감지 | 음성 키워드 | 채팅+버튼 | 채팅+버튼 | 음성 키워드 |

---

## 3. 핵심 기능

### 3-1. Must-have (P0)

| 기능 | 설명 | ADR |
|---|---|---|
| 4-모드 입출력 매트릭스 | S2S/C2S/C2C/S2C 자유 전환 | 009, 011 |
| 능동 코치 대화 | 세션 시작 시 능동 인사 + 운동 기록 활용 제안 + 사용자 확답 후 실행 | **013** |
| AI 카운팅 | 메트로놈/타이머 자동 전환, 음성·화면 동시 출력 | **014** |
| 카운팅 자동 트리거 | 사용자 발화 "푸시업 10회 시작"으로 LLM이 `start_counting` 액션 발화 | **013, 014** |
| 실시간 일정 자동 조정 | LLM이 `propose_set` 액션으로 루틴 변경 제안 | 013 |
| 운동 중 인터럽트 | Pipecat broadcast_interruption — 음성/탭 즉시 중단 | 011, 007 |
| 컨디션 체크인 | LLM `log_condition` 액션 → DB 기록 | 013 |
| 사용자 온보딩 | 목표 / 체력 측정 or 자가 평가 / 시작 (부록 A) | — |
| 안전 모니터링 | 부상 키워드 감지 → 즉시 중단 + 면책 (부록 B) | 011, 013 |
| 운동 기록 + 루틴 분석 | SQLite + SQLModel | 008 |
| **운동 캘린더 시각화** | **연간 히트맵 + 날짜 클릭 상세. 능동 코치가 패턴 활용** | **020** |
| 에러 폴백 | STT 실패 → C2S 전환 제안. LLM 지연 시 카운팅 유지 | 014 |

### 3-2. Nice-to-have

| 우선순위 | 기능 |
|---|---|
| P1 | 미수행 알림 + 자동 일정 재조정 |
| P1 | 장기 패턴 인식 (월간 요일별 피로 패턴) |
| P1 | 라이브 세션 복원 (앱 재시작 후 진행 세션 유지) |
| P1 | Smart Turn 활성화 (intonation 기반 turn 검출) |
| P1 | 폰 PWA + Tailscale 원격 접속 |
| P2 | 코치 페르소나 다중 |
| P2 | **vision 기반 카운팅 (MediaPipe Pose 99.5% 정확도)** |
| P2 | E2E S2S 모델 업그레이드 |

---

## 4. 아키텍처 개요

> 상세는 `docs/architecture/adr/` ADR 19개 참조.

### 4-1. 모드별 파이프라인 및 지연 목표

| 모드 | 파이프라인 | 총 지연 (목표) |
|---|---|---|
| S2S | VAD → STT → SafetyGuard → instructor LLM → ActionDispatch → SentenceAgg → TTS | 2~3초 |
| C2S | (text inject) → SafetyGuard → instructor LLM → ActionDispatch → SentenceAgg → TTS | 1~2초 |
| C2C | (text inject) → SafetyGuard → instructor LLM → ActionDispatch → text | 0.8~1.5초 |
| S2C | VAD → STT → SafetyGuard → instructor LLM → ActionDispatch → text | 1.5~2.5초 |

> **핵심 설계 원칙**
> - STT·TTS는 Pipecat 노드 on/off로 4-모드 자연 동작
> - LLM·ActionDispatch는 모든 모드 공통
> - **카운팅 박자 멘트는 LLM 응답과 분리** — LLM 지연 중에도 끊김 없이 박자 유지

### 4-2. 기술 스택 (v4 확정)

| 레이어 | 확정 기술 | ADR |
|---|---|---|
| 메인 언어 | Python 3.11+ | 001 |
| LLM 런타임 | Ollama (`keep_alive: 24h`) | 003 |
| LLM 모델 | qwen3:8b 단일 | 004 |
| STT | faster-whisper large-v3-turbo + 16kHz 강제 | 005 |
| TTS | Qwen3-TTS + SDPA + sentence-streaming | 006 |
| VAD/Turn | silero-vad (+ Smart Turn P1) | 007 |
| DB | SQLite + SQLModel | 008 |
| 백엔드 | FastAPI + Pipecat FastAPIWebsocketTransport | 009 |
| UI | React + Vite PWA (브라우저, 패키징 없음) | 010 |
| 운동 캘린더 | react-activity-calendar 히트맵 + 능동 코치 패턴 활용 | **020** |
| **음성 파이프라인** | **Pipecat 전면 채택** | **011** |
| 어댑터 계층 | Domain Adapter + Pipecat Service 분리 | 012 |
| 능동 코치 | instructor + Pydantic + JSON 구조화 | 013 |
| 카운팅 | 메트로놈/타이머 + LLM 액션 트리거 | 014 |
| 모델 상주 | LLM 24h, STT/TTS lifespan 사전 로드 | 015 |
| 모델 다운로드 | setup 스크립트 (HF + Ollama 캐시) | 016 |
| 패키지 매니저 | uv (Python) + pnpm (JS) | 017 |
| 로깅 | loguru + 파일 + 지연 메트릭 | 018 |
| 테스트 | pytest + Pipecat MockTransport | 019 |

기준 환경: Windows 10/11 + RTX 5090(32GB) + 64GB RAM.

---

## 5. AI 카운팅

### 5-1. 운동별 모드

| 운동 | 모드 | 박자 구성 | 음성 예시 (C2C는 화면) |
|---|---|---|---|
| 풀업 | 메트로놈 | 올라가기 + 내려가기 | "하나 — 올라가요! / 내려오세요" |
| 푸시업 | 메트로놈 | 내려가기 + 올라가기 | "둘 — 내려가요! / 올라와요!" |
| 스쿼트 | 메트로놈 | 앉기 + 서기 | "셋 — 앉아요! / 올라와요!" |
| 플랭크 | 타이머 | 초 단위 카운트다운 | "30초, 코어에 힘! / 15초 남았어요" |

### 5-2. 설정값

| 파라미터 | 기본 | 범위 |
|---|---|---|
| 박자 간격 (메트로놈) | 2초 | 1~4초 |
| 플랭크 목표 시간 | 30초 | 10~120초 |
| 세트 간 휴식 | 60초 | 15~120초 |

> 박자 정확도 ±10%. `time.monotonic()` 절대 시각 기반 (sleep 누적 금지).

### 5-3. 트리거 (v4 신규)

- 사용자 발화 "푸시업 10회 시작" → LLM `StartCountingAction` 발화 → 자동 시작
- 능동 코치 제안 → 사용자 "좋아" 확답 → 자동 시작 (ADR-013 확답 룰)
- UI 버튼 (수동, fallback)

---

## 6. 안전 정책 (요약)

> 상세는 부록 B.

### 6-1. 필수 3가지

1. **의료 면책 고지** — UI 설정 화면 옵션 (단일 사용자 가정 — v1 결정 계승)
2. **부상 키워드 감지** — `SafetyGuardProcessor`가 LLM 호출 전 인터셉트 → 즉시 운동 중단 + 전문의 안내
3. **LLM 안전 프롬프트 하드코딩** — 통증 무시·운동 강행 권유 금지

### 6-2. 필수 문구

> **LocalFit AI는 피트니스 가이던스 앱이며, 의료 기기나 의료 전문가를 대체하지 않습니다. 통증, 부상, 또는 건강 이상이 있다면 운동을 중단하고 의료 전문가와 상담하세요.**

---

## 7. MVP 출시 기준 & 미결 사항

### 7-1. MVP 동작 확인 체크리스트

- [ ] 4모드(S2S, C2S, C2C, S2C) 모두 끊김 없이 동작
- [ ] AI 카운팅이 메트로놈/타이머 자동 전환, 박자 정확도 ±10%
- [ ] **사용자 발화로 카운팅 자동 시작** (v4 신규 — ADR-013, 014)
- [ ] **능동 코치 인사 + 추천 제안 + 확답 → 자동 실행** (v4 신규 — ADR-013)
- [ ] 코칭 대화 일정 변경 5종 자연스러운 처리
- [ ] 부상 키워드 감지 시 즉시 중단 + 면책 100% 동작
- [ ] LLM 응답 지연 4초 초과 시 폴백, 카운팅은 끊기지 않음
- [ ] **TTS 첫 청크 지연 < 500ms** (v4 신규 — ADR-006)
- [ ] **운동 중 음성/탭 인터럽트 견고 동작** (v4 강화 — ADR-011)
- [ ] **운동 캘린더 화면 — 연간 히트맵 정상 표시 + 날짜 클릭 상세 모달 + 능동 코치가 패턴 활용** (v4 신규 — ADR-020)

### 7-2. 미결 사항

| # | 질문 | 상태 |
|---|---|---|
| 1 | Pipecat 0.x breaking change 대응 정책 | **P1 검토** (별도 ADR) |
| 2 | C2S 빠른 응답 버튼 목록 최종 | UI 작업(phase-6)에서 확정 |
| 3 | 부상 키워드 전체 목록 (20+종) | SafetyGuard 작업에 포함 |
| 4 | Smart Turn 한국어 정확도 | P1 검증 |
| 5 | vision 기반 카운팅 도입 시점 | P2 |

---

# PART 2 — 부록

(v3.2 부록 A·B·C·D·E·F·G는 그대로 계승. 본 문서에서는 인덱스만 유지. 상세는 `_archive/v1/prd-v3.2.md` 참조 후 필요 시 v4용으로 갱신)

## 부록 H. 아키텍처 참조

| # | 제목 | 상태 |
|---|---|---|
| 001 | 메인 언어 Python | Accepted |
| 002 | 토폴로지 — 데스크탑 단독 | Accepted |
| 003 | LLM 런타임 Ollama | Accepted |
| 004 | LLM 모델 qwen3:8b 단일 | Accepted |
| 005 | STT faster-whisper + 16kHz | Accepted |
| 006 | **TTS Qwen3-TTS + SDPA + streaming** | Accepted |
| 007 | VAD silero + Smart Turn (P1) | Accepted |
| 008 | DB SQLite + SQLModel | Accepted |
| 009 | 백엔드 FastAPI + Pipecat WS transport | Accepted |
| 010 | UI React PWA (패키징 없음) | Accepted |
| 011 | **음성 파이프라인 Pipecat 전면 채택** | Accepted |
| 012 | 도메인 어댑터·서비스 계약 | Accepted |
| 013 | **능동 코치 instructor + JSON** | Accepted |
| 014 | 카운팅 엔진 메트로놈/타이머 + LLM 트리거 | Accepted |
| 015 | 모델 동시 상주 | Accepted |
| 016 | 모델 다운로드 | Accepted |
| 017 | 패키지 매니저 uv + pnpm | Accepted |
| 018 | 로깅·관측성 loguru | Accepted |
| 019 | 테스트 전략 pytest + MockTransport | Accepted |

## 부록 I. 변경 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| v3.1 (Lean) | 2026-05-19 | 초판 |
| v3.2 | 2026-05-22 | 아키텍처 결정 반영 (ADR 16개) |
| **v4** | **2026-05-31** | **v3-rewrite. Pipecat 전면 채택, TTS Qwen3+SDPA 복귀, 능동 코치 구현 명시, 단일 LLM, 데스크탑 패키징 폐기** |

---

*문서 끝 — LocalFit AI PRD v4 (v3-rewrite) | Part 1: 7 sections + Part 2: 부록*
