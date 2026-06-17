# Phase v4-9b — Google Calendar UI (설정 화면 연동 진입점)

## 배경 / 문제

phase v4-9는 Google Calendar를 **백엔드만** 구현했다 — `/api/gcal/*`(OAuth·등록·틈새·상태), 스케줄러 소스, 음성 액션(`propose_calendar_sync`). 그러나 **프론트엔드 진입점이 없다**: 사용자가 GUI에서 연동/해제/등록할 방법이 없어, 지금은 음성(코치 제안→확답) 또는 API 직접 호출(`Invoke-RestMethod`)로만 동작한다.

특히 **최초 OAuth 연동(브라우저 동의 트리거)은 음성으로 못 한다** — 설정 화면의 버튼이 필요하다. 이 문서는 그 UI 갭만 메운다(백엔드 변경 없음).

## 목표 (스코프)

설정 화면(`Settings.tsx`)에 **"캘린더" 섹션**을 추가해 다음을 노출:

1. **상태 표시** — 연동됨 / 안 됨 / 비활성(`enabled=false`).
2. **연동하기 / 해제** — 최초 1회 브라우저 동의 트리거, 토큰 삭제.
3. **이번 주 플랜 등록** — 미리보기(쓰기 X) → 사용자 확인 → 등록(확답 게이트, ADR-022/013).
4. **미연동 graceful 안내** — "연동하면 폰과 동기화돼요" 수준의 짧은 설명.

### 비목표
- 백엔드 변경 없음(엔드포인트·로직 그대로 재사용).
- 틈새(`/gaps`) 별도 위젯·캘린더 이벤트 목록 뷰 — 후순위(필요 시 별도).
- 음성 등록 경로(`propose_calendar_sync`)는 이미 동작 — 변경 없음.
- ADR-020 로컬 운동 히트맵(`/api/calendar`)과 무관(절대 섞지 않음).

## 재사용할 백엔드 (이미 존재)

| 엔드포인트 | 용도 | 응답 |
|---|---|---|
| `GET /api/gcal/status` | 연동 상태 | `{enabled, connected}` |
| `POST /api/gcal/connect` | OAuth 동의(브라우저) → 토큰 저장 | `{enabled, connected}` |
| `POST /api/gcal/disconnect` | 연동 해제 | `{enabled, connected}` |
| `POST /api/gcal/plan/preview` | 등록 후보 미리보기(쓰기 X) | `[{exercise,start,end,summary}]` |
| `POST /api/gcal/plan/register` | 등록(확답 게이트) | `{created,skipped,events[]}` |

## 작업 항목

### 9b-1. API 클라이언트 (`ui/src/api/client.ts`)
- 타입: `GcalStatus{enabled,connected}`, `GcalProposedEvent{exercise,start,end,summary}`, `GcalRegisterResult{created,skipped,events}` (기존 `NotificationSettings`처럼 client.ts에 인라인).
- 함수: `getGcalStatus()`, `gcalConnect()`, `gcalDisconnect()`, `previewPlanEvents()`, `registerPlanEvents()`.
- ★ **`gcalConnect()`는 긴 타임아웃 필요** — `/connect`는 브라우저 동의 동안 블로킹(수십 초)이라 기본 `REQUEST_TIMEOUT_MS=8000`이면 중단된다. 전용 긴 타임아웃(예: 180s) fetch로 처리.
- `register`는 항상 `{confirm:true}`로 보냄(버튼 클릭 = 사용자 확인. confirm 없으면 백엔드가 400).

### 9b-2. 설정 UI (`Settings.tsx` `CalendarSection`)
- 마운트 시 `getGcalStatus()` (콜드스타트 대비 `loadWithRetry` 재사용).
- `enabled=false`: "설정에서 비활성화됨" 안내, 버튼 숨김.
- `connected=false`: **연동하기** 버튼 → `gcalConnect()`(로딩 표시 "브라우저에서 동의해 주세요…") → 성공 시 상태 갱신.
- `connected=true`: "연동됨 ✅" + **해제** 버튼 + **이번 주 운동 등록** 버튼.
  - 등록 클릭 → `previewPlanEvents()` → 후보 목록(날짜·종목) 표시 + **"N건 등록" 확인 버튼** → `registerPlanEvents()` → 결과("N건 등록됨") 표시.
  - 플랜 없으면 미리보기 빈 목록 → "등록할 주간 플랜이 없어요" 안내.
- 실패/오프라인: 한국어 에러 + 코칭엔 영향 없음 명시(degrade).

### 9b-3. 테스트 (`Settings.tsx` 또는 `CalendarSection.test.tsx`)
- vitest: client 함수 mock.
  - 미연동 → "연동하기" 버튼 노출, 클릭 시 `gcalConnect` 호출 → connected=true 반영.
  - 연동됨 → 등록 버튼 → preview 표시 → 확인 → `registerPlanEvents({confirm:true})` 호출.
  - `enabled=false` → 버튼 숨김/비활성 안내.

## Definition of Done
- [ ] 설정에 캘린더 섹션 노출(상태/연동/해제/등록).
- [ ] 연동하기 → 브라우저 동의(긴 타임아웃) → connected 반영.
- [ ] 등록은 **미리보기→확인** 2단계(확답 게이트, 자동 등록 없음).
- [ ] 미연동/오프라인 graceful 안내(코칭 영향 0).
- [ ] vitest + tsc + build 통과. 백엔드 무변경.
- [ ] 수동 검증 문서 C-3을 "GUI로 가능"으로 갱신.

## ADR 준수
- **ADR-022**: 등록은 확답 게이트(미리보기→확인). 본인 계정 1개. 미연동 degrade.
- **ADR-002**: 멀티계정/`user_id` 분기 없음.
- **ADR-033**: 안전/면책 잔소리 없음(중립 안내).
- **ADR-010(UI)**: 컴포넌트는 `client.ts` 경유만(직접 fetch 금지) — coding-style §9.

## 검증
- vitest/build = 자동. **연동하기→브라우저 동의 / 실제 캘린더 이벤트 생성**은 여전히 사람(C-3) — 단 이제 GUI 버튼으로 수행.
