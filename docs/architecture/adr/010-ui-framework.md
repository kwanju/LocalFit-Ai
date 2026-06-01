# ADR-010: UI — React + Vite PWA (브라우저 사용, 데스크탑 패키징 없음)

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-002 (토폴로지), ADR-009 (transport)

## 컨텍스트

v1은 React + Vite + TypeScript strict + Tailwind PWA로 구현됐다. v2에서 같은 코드를 pywebview + PyInstaller로 데스크탑 셸 안에 패키징 시도 → 빌드·DLL·마이크 권한 이슈 누적 → 폐기 결정. v3는 v1의 브라우저 PWA 형태를 그대로 유지한다.

PWA Service Worker는 v1에서도 LLM 응답을 캐시·intercept 위험이 있어 신중히 다뤘다. v3에서는 SW를 도구·자산 캐시 용도로만 한정한다.

## 결정

- **프레임워크**: React 18 + Vite 6 + TypeScript (strict)
- **스타일**: Tailwind CSS
- **라우팅**: React Router 6
- **PWA**: manifest + Service Worker (자산 캐시만, API 응답 캐시 금지)
- **번들**: `pnpm build` → `ui/dist`
- **서빙**: 개발은 Vite dev server (`pnpm dev`), 운영은 FastAPI가 `ui/dist` 정적 서빙(v1 동일)
- **데스크탑 패키징 미시도** — pywebview/PyInstaller/Electron 전부 폐기. 사용자는 브라우저로 `http://127.0.0.1:8000` 접속

### 4-모드 UI

| 모드 | 마이크 | 음성 출력 | 화면 |
|---|---|---|---|
| S2S | 라이브 캡처 (silero VAD trigger) | 자동 재생 | 카운팅·메시지 |
| C2S | 비활성 | 자동 재생 | 채팅 입력 + 카운팅 |
| C2C | 비활성 | 음소거 | 채팅 + 카운팅 |
| S2C | 라이브 캡처 | 음소거 | 채팅 + 카운팅 |

### 마이크 권한 / 캡처

- `getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } })` — STT 16kHz 강제(ADR-005)와 정합
- 권한 상태별 한국어 안내 메시지 (v1 useAudio 자산 재활용)
- 볼륨 슬라이더 (localStorage 영속, v1 자산 재활용)
- Screen Wake Lock — 운동 중 화면 잠금 방지

### 카운팅 디스플레이

- 큰 숫자 표시 (C2S 헬스장 모드 핵심 UX)
- 메트로놈/타이머 시각적 박자 표시
- 인터럽트: 화면 1탭 → WS로 InterruptionFrame 전송

### Service Worker 정책

- 자산(JS/CSS/이미지) 캐시만
- `/api/*`, `/ws/*`는 **절대 캐시 안 함** (LLM 응답·세션 상태 stale 위험)

## 결과

### 긍정
- v1 코드·디자인 그대로 — 학습 곡선 0
- 데스크탑 패키징 폐기 → 빌드 매트릭스 단순화
- 브라우저 호환성 = Chromium 기반(Chrome/Edge) 우선, Firefox/Safari는 best-effort

### 부정
- 사용자가 매번 브라우저 + URL 열어야 함 — 데스크탑 단축아이콘은 PWA Install로 대체
- WebView2 같은 임베디드 셸 없음 — PWA Install 시 Chrome/Edge 의존
- 브라우저 마이크 권한 매 origin 1회 동의 필요 (v1과 동일)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| pywebview + PyInstaller (v2 ADR-020) | v2에서 빌드·DLL·검증 이슈 누적 — 폐기 결정 |
| Tauri | Rust 빌드 의존성 — 1인 프로젝트 운영 부담 |
| Electron | 비대(~150MB), 단일 사용자엔 가치 미만 |
| Next.js | SSR 불필요, Vite보다 빌드 무거움 |
| SvelteKit | 학습 비용, React 자산 폐기 |
| 순수 HTML/Vanilla JS | 4-모드 상태관리·라우팅 복잡도 감당 안 됨 |

## References
- [Vite 6](https://vite.dev/)
- [PWA Install Prompt 가이드](https://web.dev/install-criteria/)
- v2 데스크탑 패키징 폐기 회고: `_archive/v1/020-desktop-packaging.md`
