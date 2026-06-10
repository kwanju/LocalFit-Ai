# Phase v4-0 — Tauri 탐사 (Spike / Go-No-Go 게이트)

> **이것은 탐사 phase다. 기능을 만드는 게 아니라 "Tauri가 v4 native 요구를 실제로 충족하는가"를 검증한다.**
> 회고 원칙 3(의존성 메이저 변경 = 별도 탐사 phase) + v2 데스크탑 패키징 통째 폐기 이력에 대한 직접 대응.
> **timebox 1~2일.** 끝에 go/no-go 를 *반드시* 결정한다 (회고 4-4 "그만하기").

## 0. 왜 이 phase 가 먼저인가

v4 의 최대 불확실성은 native(Tauri) 다. 다음 결정들이 전부 "Tauri 가 되느냐"에 매달려 있다:
- Native toast 알림 (§6-3)
- 트레이 백그라운드 상주 + 스케줄러 (§6-3)
- on-demand 모델 로드/언로드 (§6-8, ★새 ADR)
- ADR-010(데스크탑 패키징 폐기)을 v4 에서 뒤집는 결정 전체

이 게이트를 통과하기 전에는 native 관련 ADR 을 확정하지 않는다. **실패하면 PWA(브라우저 Notification API + Service Worker)로 후퇴**하고, 비전 §0-2 의 알림/상주 결정을 그에 맞게 수정한다.

> Tauri 와 **독립적인** ADR(메모리/플랜/컨디션/캘린더/첫 체력검증)은 이 phase 와 병행해서 초안 작성 가능.

## 1. 검증 대상 환경

- Windows 10/11 네이티브, uv venv (기존 환경 계승)
- 기존 v3 `ui/` React PWA + `app/` FastAPI 백엔드를 그대로 재사용 시도
- GPU: 16GB VRAM 베이스라인 가정 (개발기는 RTX 5090 32GB — 16GB 제약은 의도적으로 모사)

## 2. 검증 항목 (각각 PASS/FAIL 게이트)

각 항목은 **사람이 직접 눈으로 확인**한다(회고 원칙 2). 항목별로 PASS 기준과 FAIL 시 영향을 적는다.

### S-1. Tauri 빌드·실행 기본
- Tauri 프로젝트 생성 → `tauri dev` 실행 → `tauri build`로 Windows 실행 파일(.exe/installer) 산출.
- **PASS**: dev 창이 뜨고, build 산출물이 더블클릭으로 실행됨.
- **FAIL 영향**: Rust 툴체인/빌드 자체가 막히면 v2 와 동일한 함정 → 즉시 no-go 후보.

### S-2. 기존 React UI 웹뷰 탑재
- `ui/`(v3 React PWA) 프로덕션 빌드를 Tauri 웹뷰에 로드.
- **PASS**: 기존 화면(모드 토글 등)이 웹뷰에 그대로 렌더됨.
- **FAIL 영향**: UI 재작성 필요 → 비용 급증, no-go 가중치 큼.

### S-3. 백엔드 WebSocket 연결
- 웹뷰 React ↔ FastAPI `127.0.0.1:8000` WebSocket(`/ws/voice`) 연결.
- **PASS**: 웹뷰에서 WS 핸드셰이크 성공, 텍스트 라운드트립(C2C echo 수준) 확인.
- **FAIL 영향**: CORS/CSP/localhost 접근 제약 → 설정으로 해결 가능한지 확인. 해결 불가면 no-go.

### S-4. 마이크 캡처 + 오디오 출력 (음성 모드 핵심)
- Tauri 웹뷰에서 `getUserMedia` 마이크 캡처 + 오디오 재생(Web Audio).
- **PASS**: 마이크 권한 프롬프트 → 허용 → 캡처된 오디오가 WS 로 전송되고, 수신 오디오가 스피커로 재생됨.
- **FAIL 영향**: 음성 모드(S2S/C2S) 불가 → v4 핵심 기능 붕괴, **치명적 no-go**.
- **안 행복한 경로**: 마이크 권한 거부 시 UI 안내가 뜨는지.

### S-5. Python 사이드카 프로세스 관리
- Tauri 가 FastAPI+모델 백엔드를 사이드카로 spawn / 종료(또는 외부 기동 프로세스에 연결).
- **PASS**: 앱 시작 시 백엔드 기동, 앱 종료 시 백엔드도 정리(좀비 프로세스 없음).
- **FAIL 영향**: 사용자가 수동으로 백엔드를 켜야 함 → 배포 편의 저하(친구 공유 §6-1 어려워짐). 차선책(외부 기동) 허용 가능 여부 판단.
- **안 행복한 경로**: 사이드카가 죽으면 UI 가 감지하고 안내하는지.

### S-6. Native toast 알림
- Tauri notification plugin 으로 Windows toast 발생 → 클릭 시 앱 포커스/지정 동작.
- **PASS**: 앱이 백그라운드(또는 최소화) 상태에서 toast 가 뜨고, 클릭하면 앱이 떠서 세션 시작 흐름으로 진입.
- **FAIL 영향**: 능동 알림(§6-3) 불가 → native 채택 이유 절반 상실.
- **안 행복한 경로**: OS 알림이 꺼져 있을 때(집중모드 등) 동작.

### S-7. 트레이 상주
- 시스템 트레이 아이콘 + 창 닫아도 트레이에 상주(백그라운드 스케줄러 동작 전제).
- **PASS**: 창을 닫아도 프로세스가 트레이에 남고, 트레이 메뉴로 복원/종료 가능.
- **FAIL 영향**: "세션 모델 + 스케줄러"의 상주 주체가 사라짐 → 스케줄러 설계 재검토.

### S-8. on-demand 모델 로드/언로드 + VRAM 반환 (★ 핵심)
- 세션 시작 시 STT(faster-whisper) + TTS(faster-qwen3-tts) + LLM(Ollama qwen3.5:9b) 로드 → 세션 종료 시 언로드.
- LLM: Ollama `keep_alive=0`(또는 짧게). STT/TTS: Python 객체 해제 + `torch.cuda.empty_cache()`.
- **PASS**: `nvidia-smi`로 (a) 세션 중 VRAM ~13GB 점유 (b) 세션 종료 후 수 초 내 VRAM 반환 확인. 평소(세션 밖)엔 무거운 모델 미상주.
- 콜드스타트 실측: 세션 시작 → 첫 응답까지 로드 지연 시간 측정(목표 감각치 기록).
- **FAIL 영향**: 게임/타 앱과 VRAM 공존(§6-8) 불가 → lifecycle 설계 재검토.
- **안 행복한 경로**: VRAM 부족(타 앱이 점유)으로 로드 실패 시 사용자 안내.

## 3. Definition of Done

- [ ] S-1 ~ S-8 각 항목 PASS/FAIL 기록 (스크린샷 또는 `nvidia-smi`/로그 캡처 첨부)
- [ ] 콜드스타트 지연 실측치 1건 이상 기록
- [ ] **go/no-go 결정 명문화**:
  - **go** → native 확정. ADR(알림/상주/lifecycle) 초안 작성으로 진입. 비전 §0-2 "상주 형태" 최종 확정.
  - **no-go** → PWA 후퇴. 비전 §0-2 의 알림/상주/native 결정을 PWA 제약에 맞게 수정 + ADR-010 유지.
  - **부분 go** → 되는 것만 native, 안 되는 항목은 차선책/후순위 명시.
- [ ] 결과를 `docs/agent-tasks/v4/phase-0-tauri-spike-result.md`(또는 본 파일 하단)에 박제 — 회고 4-3(재현 가능 기록)

## 4. 명시적 비목표 (이 phase 에서 하지 않는 것)

- 실제 코칭 로직/메모리/플랜/캘린더 구현 (← 후속 phase)
- UI 디자인 다듬기
- installer 배포 자동화/하드웨어 자동 감지 (§6-1 후순위)
- 모든 엣지 케이스 처리 — **검증에 필요한 최소만**(회고 4-4)

## 5. 리스크 / 주의

- Tauri 는 webview2(Windows) 의존 — getUserMedia/Web Audio 동작이 브라우저와 미묘하게 다를 수 있음(S-4 가 가장 위험).
- 사이드카로 Python+모델(수 GB)을 번들하면 배포 크기 급증 — 탐사에선 "연결만" 검증하고 번들 전략은 후순위.
- **timebox 엄수**: 1~2일 안에 안 되면 그 자체가 신호. v2 처럼 패키징에 무한정 매달리지 않는다.

## 6. 소요 추정

1~2일 (timebox).

## 7. 다음 단계

- go → v4 ADR 초안 (native 의존 ADR 포함) + v4 phase 인덱스 작성
- no-go → PWA 기반 v4 재설계 + 비전 §0-2 수정
