# Task: Phase 5 — UI (React PWA)

3개 하위 작업. UI는 Python과 별도 컨텍스트/세션으로 진행 권장.
Cursor 등 시각 피드백 강한 도구 고려.

## 공통 배경 자료
- `AGENTS.md` (7번 TS 컨벤션)
- `docs/architecture/adr/009-ui-framework.md`
- `docs/prd-v3.1.md` 2-3 (C2S 헬스장 UI), 2장 (4-모드)
- `docs/conventions/coding-style.md` 9번

---

## 5A. 초기화

### 작업
1. `ui/` Vite + React 18 + TypeScript 초기화 (pnpm)
2. Tailwind CSS, React Router 설정
3. PWA: manifest.json, Service Worker, 아이콘
4. `ui/src/api/client.ts` (REST), `ui/src/api/ws.ts` (WebSocket + 재연결)
5. 빈 화면 3개 라우트 (Onboarding, SessionLive, Settings)

### 제약
- strict 모드, any 금지
- API 호출은 ui/src/api/에 집중

---

## 5B. C2C 모드 풀스택 연결 (가장 단순한 모드 먼저)

### 작업
1. `ui/src/components/ChatPanel.tsx` — 채팅 입출력
2. `ui/src/components/CountingDisplay.tsx` — 화면 큰 숫자 카운팅
3. `ui/src/screens/SessionLive.tsx` — 세션 화면 (C2C)
4. `ui/src/state/session.tsx` — Context + reducer
5. `ui/src/hooks/useWakeLock.ts` — 화면 꺼짐 방지 (플랭크)
6. 백엔드 WebSocket과 연결하여 채팅 코칭 + 화면 카운팅 동작

### 제약
- C2C 먼저 완전 동작 (STT/TTS 불필요 — 가장 단순)
- 진동 알림 (navigator.vibrate)

---

## 5C. 음성 모드 추가 (S2S → C2S → S2C)

### 작업
1. `ui/src/hooks/useAudio.ts` — 마이크 입력 캡처 + 오디오 재생
2. `ui/src/components/QuickButtons.tsx` — C2S 빠른 응답 버튼 (PRD 미결 #2, 10~15개)
3. `ui/src/components/ModeSwitch.tsx` — 1탭 모드 전환
4. 마이크 → 백엔드 STT, 백엔드 TTS → 오디오 재생
5. 인터럽트: 화면 탭 / 음성

### 제약
- 마이크 권한 처리
- C2S 빠른 버튼 우선 (헬스장 핵심)
- 이어폰 연결 감지 알림 (자동 전환 X)

## 완료 기준 (5 전체)
- C2C 완전 동작 (채팅 + 화면 카운팅)
- S2S 음성 왕복
- C2S 빠른 버튼 + 이어폰 출력
- 모드 1탭 전환

## 자가 보고
각 하위 작업마다 AGENTS.md 9번. checklist A·B·G 확인 (UI는 테스트 P1로 미룸).
