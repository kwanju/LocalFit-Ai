# Agent Tasks — v4-rewrite

v4 구현 phase 인덱스. v3(master 동결)을 base 로, ADR-021~031 을 구현한다.
진실 소스 = `docs/future/v4-vision.md` §0-2 + 각 ADR. v3 와 충돌 시 **v4 우선**(ADR-021).

> **Phase v4-0 (Tauri 탐사) 완료 — GO** (`phase-0-tauri-spike-result.md`).
> native 의존 ADR(027/030/031) Accepted 승격, 010/015 Superseded 갱신(2026-06-10).
> 본 인덱스는 그 GO 이후의 **구현** phase 들이다.

## 진행 원칙 (회고 4원칙 — `docs/retrospectives/2026-06-07-v3-lessons.md`)

- 각 phase 끝에 **사람 E2E 검증**(회고 원칙 2) 후 다음 phase 진입.
- 새 메이저 의존성/플랫폼 변경은 **별도 탐사**(회고 원칙 3) — Tauri 는 v4-0 에서 완료.
- timebox 안에 안 되면 그 자체가 신호, 무한정 매달리지 않음(회고 4-4).
- 각 phase 진입 시 해당 phase 의 작업 명세(`phase-N-*.md`)를 먼저 작성하고 시작.

## Phase 인덱스

순서 = **비-native 도메인 기반부터** 쌓고, 그 위에 native 런타임(Tauri 셸·모델 lifecycle·알림)을 올린다.
도메인 phase(1~5)는 v3 의 상주-모델 런타임 위에서 그대로 개발·검증 가능하고, native phase(6~8)에서 런타임을 교체한다.

| # | Phase | 핵심 산출물 | 관련 ADR | 의존 |
|---|---|---|---|---|
| 0 | [Tauri 탐사 (완료·GO)](phase-0-tauri-spike.md) | S-1~S-8 검증, go/no-go 게이트 | 027·030·031 | — |
| 1 | v4 base 정리 + 3모드 + 모델 config | `v4-rewrite` 정리, **S2C 제거 → 3모드(C2C/C2S/S2S)**, `config.llm.model=qwen3.5:9b`, v3→v4 DB 스키마 확장 스캐폴드 | 021, 029 | 0 |
| 2 | 영속 메모리 | SQLite **구조화(부상·제약) + 자유텍스트 메모** 하이브리드 + Repository + `CoachContextBuilder` 에 부상/제약 **전량 주입** | 025 | 1 |
| 3 | 컨디션 트래킹 | 자가보고 체크인(피로/근육통, 로컬-only) 저장 + 코치가 컨디션 읽어 **강도 조절 제안(확인)** | 023 | 2 |
| 4 | 운동 플랜 | **주간 목표 + 일자 분배**, 컨디션 결합 자동 제안은 **ConfirmRule 동의**(LLM 임의조정 금지) | 024 | 2, 3 |
| 5 | 첫 세션 대화형 체력검증 | 단발 `propose_set` → **대화형 plan-building tool-use**, 온보딩 폼 시드 보정 → 메모리 기준선 저장 | 028 | 2, 4 |
| 6 | Tauri 셸 통합 (런타임 교체) | 탐사 산출물 제품화: `ui/` Tauri 웹뷰 탑재 + FastAPI **사이드카 lifecycle**(spawn/tree-kill) + 사이드카 사망 감지 UI. **후속 fix: S-4 마이크 입력(webview2 권한)** | 031 | 1 |
| 7 | 모델 lifecycle on-demand | 세션 시작 GPU 로드 / 종료 언로드(Ollama `keep_alive=0` + `empty_cache()`), **병렬 로드 + 앱-열림 prewarm + "코치 준비 중" UX** 로 콜드스타트(~30s) 단축, VRAM 반환 검증 | 030 | 6 |
| 8 | 능동 알림 + 백그라운드 스케줄러 | 트레이 상주 경량 스케줄러 + native toast(운동시간/체크인) + **클릭→앱 포커스→세션 시작**(S-6 후속 마무리), 음소거 시간대 | 027 | 6, 4 |
| 9 | Google Calendar 연동 | OAuth2 Desktop client, 운동 일정 등록 + 타 일정 읽어 틈새 추천. **로컬-only(ADR-002)를 캘린더에 한해 완화** | 022 | 4, 8 |

> **ADR-026(종목 확장)** 은 Deferred — v4 는 v3 4종(풀업/푸시업/스쿼트/플랭크) 고정 유지, phase 없음.

## 작업 순서 가이드

- **1 → 2 → 3 → 4 → 5** 가 도메인 코어 라인(비-native). 메모리(2)가 컨디션·플랜·체력검증의 공통 기반이라 먼저.
- **6 → 7** 은 런타임 교체 라인: Tauri 셸(6)이 들어와야 모델 lifecycle(7)·트레이 스케줄러(8)가 의미. 6 에서 **S-4 마이크 입력**(탐사 유일 미검증)을 반드시 통과시켜야 S2S 모드가 산다 — 집 환경 검증 필요(spike-result §5 런북).
- **8(알림)** 은 6(트레이) + 4(스케줄 소스: 플랜/캘린더)에 의존. **9(캘린더)** 는 가장 후순위 — 외부 API 라 독립적으로 붙임.
- 도메인 phase(1~5)는 native 와 **병행 가능**: 6~9 와 별개 트랙으로 개발하다 통합 가능(단 사람 검증은 각 트랙 끝에서).

## 리스크 게이트

- **S-4 마이크 입력**(phase 6) — 탐사에서 유일하게 미검증(webview2 `getUserMedia`). FAIL 시 음성 모드 붕괴 → 차선책(브라우저 fallback) 또는 권한 설정으로 해결. 집 환경 우선 검증.
- **qwen3.5:9b 회귀**(phase 1·5) — 9b 가 instructor/JSON/ConfirmRule 출력(ADR-013)에서 회귀하는지 첫 코칭 구동 시 확인(메모리 v4-status 경고).
- **콜드스타트 30s**(phase 7) — 병렬 로드 + prewarm 으로 체감 단축이 목표대로 되는지 실측 게이트.

## 산출물 공통 요구

- ruff + pyright 통과, pytest 비-GPU 스위트 통과
- 각 phase 종료 시 "작업 완료 보고"(CLAUDE.md §9 형식) + 사람 E2E 검증
- Conventional Commits + 한국어 본문. ADR 변경은 별도 커밋.

## 관련 문서

- `docs/future/v4-vision.md` — v4 비전 + deep interview 결과(§0-2)
- `docs/architecture/adr/README.md` — ADR 인덱스(v4 시리즈 021~031)
- `phase-0-tauri-spike-result.md` — Tauri 탐사 GO 기록(런북 §5)
- `docs/retrospectives/2026-06-07-v3-lessons.md` — 회고 4원칙
