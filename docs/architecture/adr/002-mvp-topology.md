# ADR-002: 토폴로지 — 데스크탑 단독, 127.0.0.1 바인딩

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-009 (백엔드 transport), ADR-010 (UI)

## 컨텍스트

LocalFit AI는 **단일 사용자 본인이 자기 머신에서 사용**하는 개인 프로젝트다. v1에서 검증된 토폴로지이며 v3-rewrite도 변경 사유가 없다.

폰·헬스장 같은 원격 시나리오는 P1으로 분리한다(Tailscale + Wake-on-LAN 검토 항목).

## 결정

- **백엔드 바인딩**: `127.0.0.1`만 (외부 노출 금지)
- **단일 사용자 가정**: `user_id` 컬럼·인증·권한·세션 격리 코드 작성 금지
- **UI 접근**: 데스크탑 브라우저 (`http://127.0.0.1:8000`)
- **P0 환경**: Windows 10/11 + NVIDIA GPU (RTX 5090 검증 환경)
- **데스크탑 패키징 미시도**: v2의 pywebview + PyInstaller는 폐기. 브라우저 PWA만(ADR-010).

## 결과

### 긍정
- 보안 표면 최소 (외부 노출 0)
- 멀티유저 코드 부재로 도메인 로직 단순
- 패키징 부담 0 — `uvicorn app.main:app` + `pnpm dev`로 즉시 기동

### 부정
- 폰·헬스장 시나리오는 P0에서 사용 불가 (P1으로 연기)
- 본인 외 사용 안 됨 — 공유 시 별도 인스턴스 셋업 필요

## 대안

| 후보 | 탈락 사유 |
|---|---|
| 0.0.0.0 바인딩 + 토큰 인증 | 단일 사용자엔 over-engineering, 공격 표면 증가 |
| pywebview + PyInstaller 데스크탑 앱 (v2 ADR-020) | v2에서 빌드·검증 이슈 누적 — DLL 로드 실패, 첫 실행 어댑터 미준비, 디버깅 비용 큼. 비용 대비 가치 낮음 |
| Tauri/Electron 데스크탑 셸 | 동일 사유 + Electron 비대 |
| Tailscale + Wake-on-LAN | P1로 분리 (PRD v4 §1-3) |

## 후속 (P1)

- Tailscale 100.x 대역 바인딩 추가 검토 (PRD v4 §1-3)
- Wake-on-LAN 셋업 가이드 작성

## References
- v2 데스크탑 패키징 폐기 회고: `_archive/v1/020-desktop-packaging.md` (v2 시점 ADR, history 참조용)
