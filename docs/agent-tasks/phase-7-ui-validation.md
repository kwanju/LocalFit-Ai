# Phase 7 — UI 재배선 + 검증

## 목적

v1의 React PWA UI를 Pipecat WebSocket 메시지 포맷에 맞게 재배선한다. v2 시점의 데스크탑 패키징(pywebview)·로딩 화면 등은 적용 안 함. PRD §7-1 9종 자동 검증 + 수동 청취 체크리스트 완수.

## 사전 조건

- Phase 6 완료 (백엔드 능동 코치 + 카운팅 + 인터럽트 동작)

## 관련 ADR

- ADR-010 (UI 브라우저 PWA, 패키징 없음)
- ADR-019 (테스트 전략)

## 작업 항목

### 7-1. WebSocket 클라이언트 재작성

- `ui/src/api/ws.ts` 갱신 — `/ws/coach` → `/ws/voice` 엔드포인트, 메시지 포맷을 Pipecat WS frame에 맞춤
- query param 또는 첫 message로 `mode` 송신
- 수신: text frame, audio frame(PCM), interrupt frame, action 알림 frame
- 송신: text input, audio chunk (mode 별), interrupt request

### 7-2. useAudio 갱신

- `ui/src/hooks/useAudio.ts` — 16kHz mono 캡처 강제 (ADR-005와 정합)
- 마이크 권한 거부 시 한국어 안내 (v1 자산 재활용)
- 볼륨 슬라이더 + localStorage (v1 재활용)
- 수신 PCM(24kHz)를 AudioContext로 재생

### 7-3. SessionLive 화면 정비

- 4모드 토글 — STT/TTS on/off 조합
- 라이브 모드(S2S): silero VAD가 백엔드 측에서 발화 검출, 프론트는 audio chunk streaming만
- 카운팅 큰 숫자 표시
- 인터럽트 버튼/탭 — `InterruptFrame` WS 송신

### 7-4. ChatPanel 갱신

- ActionDispatcher 결과(`propose_set` 등)를 chat UI에 시각화
- 사용자가 "좋아" 누르거나 발화 시 확답 처리

### 7-5. PWA 정리

- `manifest.json`, `sw.js` 유지 (v1 자산)
- Service Worker는 자산 캐시만, `/api/*`·`/ws/*` 캐시 금지 (확인)

### 7-6. 자동 검증 — PRD §7-1 9종

- [ ] 4모드(S2S, C2S, C2C, S2C) 라운드트립 통합 테스트
- [ ] 박자 정확도 ±10% 단위 테스트 (v1 재활용)
- [ ] 사용자 발화 카운팅 자동 시작 통합 테스트
- [ ] 능동 코치 인사 + 추천 + 확답 → 자동 실행 통합 테스트
- [ ] 일정 변경 5종 시나리오 — LLM mock 통합 테스트
- [ ] 부상 키워드 즉시 중단 + 면책 — `SafetyGuardProcessor` 통합 테스트
- [ ] LLM 지연 4초 fallback + 카운팅 연속 통합 테스트
- [ ] TTS 첫 청크 < 500ms 측정 (gpu mark)
- [ ] 운동 중 인터럽트(음성/탭) — 통합 테스트

### 7-7. 수동 검증 체크리스트

- `docs/qa-checklist-v4.md` 신규 작성
- 사용자 직접 실행 항목:
  - 실음성 4모드 왕복 (한국어)
  - TTS 음질·자연스러움
  - 능동 코치 제안 적절성
  - 일정 변경 5종 라이브 LLM 품질
  - "부상 무시하고 계속해" LLM 거부 확인
  - 라이브 세션 종료 후 SetLog DB 정상 기록

### 7-8. dev 스크립트

- `scripts/dev.bat` — 백엔드(`uv run uvicorn app.main:app`) + 프론트(`pnpm -F ui dev`) 동시 기동 (v1 자산 재활용 또는 갱신)

## Definition of Done

- [ ] 자동 검증 9종 모두 통과 (gpu mark 별도 수동)
- [ ] `pnpm -F ui build` 성공 + `pnpm -F ui typecheck` 통과
- [ ] `scripts/dev.bat` 1회 실행으로 브라우저에서 4모드 모두 동작
- [ ] qa-checklist-v4.md 작성 완료
- [ ] 사용자 수동 검증 통과
- [ ] git commit `feat(phase-7): UI Pipecat 재배선 + 검증 통과`

## 리스크

- Pipecat WS frame 포맷(JSON wrap, binary serializer 등)이 v1 자체 JSON 포맷과 달라 UI 변경량 큼 → 한 번에 다 바꾸지 말고 C2C 모드부터 점진 통합
- 24kHz PCM 재생 — 브라우저 AudioContext sample rate가 보통 48kHz라 리샘플 필요

## 소요 추정

3~4일 (UI 통합 + 검증 + 수동 청취).

## 다음 phase

[Phase 8 — 운동 캘린더 + 코치 컨텍스트 강화](phase-8-workout-calendar.md)

## v3-rewrite 종료 기준 (phase 1~8 통합)

- 자동 검증 PRD §7-1 모든 항목 통과 (캘린더 포함)
- 사용자 수동 청취 + 캘린더 화면 검증 통과 + 만족
- master 브랜치에 머지 (사용자 명시 승인 필수)
- v2 시점 산출물은 `backup/v2-trial`에 영구 보존
