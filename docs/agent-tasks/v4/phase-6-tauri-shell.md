# Phase v4-6 — Tauri 셸 통합 (탐사 산출물 제품화)

## 목적

Phase v4-0 탐사의 Tauri 셸(`ui/src-tauri/`)을 **"spike" 딱지를 떼고 실사용 가능한 셸**로 끌어올린다(ADR-031). 핵심은 탐사에서 **유일하게 미검증으로 남은 S-4 마이크 입력**(webview2 `getUserMedia`)을 통과시키는 것 — 이게 안 되면 음성 모드(S2S/C2S)가 붕괴한다. 더불어 사이드카 lifecycle 견고화(종료-정리 재확인)와 사이드카 사망 감지 UI 를 넣는다.

> 이 phase 의 "런타임 교체"는 **브라우저 서빙 → Tauri 셸 서빙**으로의 전환을 뜻한다. **모델 상주/언로드 전환은 phase 7**(ADR-030)에서 별도로 다룬다.

## 사전 조건

- Phase v4-0 GO + native ADR Accepted 상태
- 집 환경(마이크 사용 가능) — **S-4 검증은 마이크 필수**(탐사 런북 = spike-result §5)
- 기존 자산: `ui/src-tauri/src/lib.rs`(spawn/tree-kill·tray·notify), `ui/src-tauri/capabilities/default.json`, `ui/src-tauri/tauri.conf.json`, `ui/vite.config.ts`(`server.watch.ignored`), `ui/src/api/ws.ts`(`VITE_WS_BASE`)

## 관련 ADR

- **ADR-031** — Tauri 데스크탑 + FastAPI 사이드카, 기존 React UI 웹뷰 재사용
- ADR-009/011 — Pipecat WS(`/ws/voice`) 무변경
- ADR-005 — STT 16kHz 강제(마이크 캡처 sampleRate 정합)

## 작업 항목

### 6-1. S-4 마이크 입력 fix (★ 최우선 — 탐사 유일 미검증)

- 증상(탐사): 오디오 **출력**은 통과(`tts.first_chunk 370~597ms`), **마이크 입력**은 webview2 `getUserMedia` 권한 프롬프트/캡처 미확인(spike-result §3 S-4, 최대 위험).
- 작업:
  - webview2 미디어 권한 핸들러 설정 — Tauri/WRY 의 webview 미디어 권한 자동 허용 또는 권한 콜백 배선. `capabilities/default.json` 및 webview 설정 점검.
  - `getUserMedia({audio:{sampleRate:16000, channelCount:1}})`(ADR-005 정합, v3 `useAudio` 자산) 가 webview2 에서 캡처되는지.
  - S2S 모드: 발화 → STT 인식 → 코치 음성 응답 E2E.
- **안 행복한 경로**: 권한 거부 시 UI 한국어 안내(v3 자산 재활용).
- **FAIL 시**: 음성 입력 모드 영향 → 우선 webview2 권한 설정으로 해결 시도, 정 안되면 사용자 보고 후 입력 경로 대안 재평가(설계 전면 후퇴보다 입력 경로부터). ADR-031 no-go 후퇴는 최후수단.

### 6-2. 사이드카 lifecycle 견고화

- 현재 `lib.rs` 는 dev 트리에서 `uv run python -m app.main` spawn(헤더 주석 "NOT production"). **번들(Python+모델 수 GB) 전략은 ADR-031 대로 후순위** — 이 phase 는 **dev/외부기동 경로를 안정화**하고 번들은 별도 과제로 명시.
- **종료-정리 재확인(S-5 수정본)**: `kill_backend()` 의 `taskkill /PID <id> /T /F` 트리킬(uv→python 손자 고아 방지)이 실제로 python/uv 0 잔존인지 **사람 눈 재확인**(탐사에서 수정·컴파일만 됨).
- 사이드카 spawn 실패 시 UI 가 로드는 되도록(현행 tolerate) + 안내.

### 6-3. 사이드카 사망 감지 UI

- ADR-031 "안 행복한 경로": 사이드카(Python+모델) 사망 시 UI 가 감지·안내.
- `/health` 폴링 또는 WS 끊김 → "백엔드 연결 끊김 — 재시작" 안내 + 재기동 트리거(`start_backend` invoke, 이미 lib.rs 에 존재).

### 6-4. 셸 production 표시 정리

- `lib.rs` 헤더의 "spike / NOT production" 주석을 실제 상태로 갱신. tray 메뉴 문구("알림 테스트" 등) 정리(임시 테스트 항목 제거 또는 정식화).
- prod WS 경로(`VITE_WS_BASE` → `ws://127.0.0.1:8000` 직결, spike-result §3) 웹뷰에서 확인.

## Definition of Done

- [ ] **S-4 마이크 입력 PASS** — S2S 발화 → STT → 코치 음성 응답 E2E 사람 확인(권한 거부 안내 포함)
- [ ] 종료-정리(트레이 "종료"/앱 Exit) 후 작업관리자에 python/uv **0 잔존** 재확인
- [ ] 사이드카 강제 종료 시 UI 가 감지·안내·재기동 동작
- [ ] 웹뷰에서 3모드 WS 라운드트립 정상(prod 경로)
- [ ] `cargo build` exit 0, `tauri build` 설치본 산출
- [ ] git commit `feat(v4-6): Tauri 셸 production 통합 + S-4 마이크 입력 fix`

## 명시적 비목표

- Python+모델 **사이드카 번들/installer 자동화**(ADR-031 후순위 — 별도 과제)
- 모델 on-demand 로드/언로드(phase 7)
- toast 클릭→세션 진입(phase 8 — 능동 알림과 함께)
- 하드웨어 자동 감지/setup 마법사(§6-1 후순위)

## 소요 추정

1~2일 (마이크 fix 난이도에 좌우 — timebox 의식, 회고 4-4).

## 다음 phase

Phase v4-7 — 모델 lifecycle on-demand(ADR-030). 인덱스: [`README.md`](README.md).
