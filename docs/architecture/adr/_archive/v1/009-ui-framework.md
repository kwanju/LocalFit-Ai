# ADR-009: UI 프레임워크로 React + Vite PWA

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-002 (토폴로지), ADR-008 (FastAPI)

## 컨텍스트

PRD는 "Electron 또는 PWA"를 미결로 두었다. ADR-002에서 데스크탑+폰 동시 접근을 P1 목표로 설정했고, ADR-008에서 백엔드를 HTTP/WebSocket으로 노출한다. 폰은 Android, 데스크탑은 Windows다.

## 결정

**React 18 + Vite + TypeScript**로 SPA를 구축한다. PWA 매니페스트와 Service Worker를 처음부터 포함하되, MVP에서는 데스크탑 브라우저 사용을 우선 목표로 한다.

### 보조 결정
- **스타일**: Tailwind CSS
- **상태 관리**: 초기 React Context + useReducer, 복잡도 증가 시 Zustand 검토
- **라우팅**: React Router
- **WebSocket 클라이언트**: 표준 브라우저 API + 재연결 로직 직접 작성
- **화면 꺼짐 방지**: `Screen Wake Lock API` (플랭크 등 긴 카운팅 필수)

## 결과

### 긍정
- Android Chrome PWA 지원 우수 (iOS 제약 없음)
- 같은 코드베이스가 데스크탑·폰 브라우저 모두 동작
- Vite 빠른 HMR — 1인 개발 효율
- PWA "홈화면에 추가"로 네이티브 같은 경험

### 부정
- Electron 대비 OS 통합 약함 (시스템 트레이, 알림 제한)
- iOS Safari PWA 제약 (현재 무관하지만 향후 영향 가능)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| Electron + React | 폰 시나리오 별도 작업 필요 |
| Tauri + React | 폰 동시 지원 약함 |
| 순수 HTML + Vanilla JS | 카운팅 UI·세션 상태 관리 복잡도 증가 시 결국 프레임워크 필요 |
| Svelte/SvelteKit | 사용자의 React 경험 가정 — 학습 비용 |
| Next.js | SSR 불필요, 오버킬 |
