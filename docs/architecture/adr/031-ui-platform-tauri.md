# ADR-031: UI 플랫폼 — native 데스크탑 (Tauri)

- **상태**: Proposed (★ 탐사 의존 — Phase v4-0 S-1~S-5 통과 전제)
- **Supersedes**: ADR-010 (React PWA, 데스크탑 패키징 없음)
- **관련 ADR**: ADR-009 (FastAPI + Pipecat WS), ADR-027 (native 알림), ADR-030 (모델 lifecycle)

## 컨텍스트

ADR-010 은 브라우저 React PWA 를 쓰고 **데스크탑 패키징을 폐기**했다(v2 의 pywebview + PyInstaller 빌드·검증 이슈 누적). CLAUDE.md §3 도 Tauri 를 포함한 데스크탑 패키징 재시도를 금지했다.

그러나 v4 는 **native toast 알림 + 트레이 백그라운드 상주**(ADR-027)가 필요하고, PWA 로는 브라우저를 닫으면 동작하지 않는다. v4-vision §3·§6-3 이 "PWA 한계 — native 재검토 필요"를 예견했다. v4 ADR 은 v3 와 충돌 시 우선(ADR-021)이므로, **본 ADR 이 ADR-010 을 의식적으로 뒤집는다.**

v2 와 같은 함정을 피하기 위해 **Phase v4-0 Tauri 탐사**로 먼저 검증한다(회고 원칙 3).

## 결정

- **UI 플랫폼 = Tauri 데스크탑 앱.**
  - 기존 `ui/`(React) 를 **Tauri 웹뷰에 그대로 탑재**(재사용, 재작성 X — S-2 검증).
  - 백엔드 = FastAPI `127.0.0.1` **사이드카**(Tauri 가 spawn/관리, S-5). Pipecat WS(`/ws/voice`)는 변경 없이 그대로(ADR-009/011).
  - Tauri 책임: 시스템 트레이 상주, native toast(ADR-027), 사이드카 lifecycle, 빌드/배포.
- **v2 와의 차이**: Tauri 는 Rust + 시스템 webview2(Windows) 기반으로 PyInstaller 번들과 빌드 체계가 다르다. 단 이 가정 자체를 탐사로 검증한 뒤 확정.
- **ADR-010 무효화**: "PWA only, 데스크탑 패키징 폐기" → 폐기(v4).
- **안 행복한 경로**:
  - webview2 의 `getUserMedia`/Web Audio 가 브라우저와 다를 수 있음(S-4 — 음성 모드 핵심, 최대 위험).
  - 사이드카(Python+모델) 사망 시 UI 감지·안내(S-5).

## 결과

### 긍정
- native 알림·트레이 상주 가능 → ADR-027 성립
- 기존 React UI 재사용(웹뷰) — 프론트 재작성 회피
- Pipecat 백엔드 무변경 — WS 경유 그대로

### 부정
- ADR-010·CLAUDE.md §3 를 뒤집음 — v2 패키징 폐기 이력에 대한 재도전(탐사로 리스크 관리)
- Rust 툴체인 + Tauri 빌드 학습/유지 비용
- 사이드카로 Python+모델 번들 시 배포 크기 큼(번들 전략 후순위)

## 탐사 의존 / no-go 대응

- **의존**: Phase v4-0 S-1(빌드)·S-2(웹뷰 탑재)·S-3(WS)·S-4(마이크/오디오)·S-5(사이드카) 통과.
- **no-go 시**: ADR-010(PWA) 유지. ADR-027(알림)을 PWA 범위로 축소, ADR-030 도 재검토. 비전 §0-2 수정. **v2 처럼 무한정 매달리지 않고 timebox 내 후퇴**(회고 4-4).

## 대안

| 후보 | 탈락 사유 |
|---|---|
| PWA 유지 (ADR-010) | 브라우저 닫으면 native 알림·트레이 상주 불가 — v4 능동 알림 미달 |
| Electron | 메모리·번들 무거움, Chromium 내장 — Tauri 가 경량 |
| pywebview + PyInstaller | v2 에서 빌드·검증 이슈로 폐기 |

## References
- ADR-010 (superseded) — PWA 및 데스크탑 패키징 폐기 근거
- `docs/future/v4-vision.md` §3, §6-3, §6-8
- `docs/agent-tasks/v4/phase-0-tauri-spike.md` (S-1~S-5)
