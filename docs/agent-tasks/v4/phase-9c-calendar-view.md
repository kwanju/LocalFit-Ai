# Phase v4-9c — 기록 탭 캘린더 뷰 + 경량 CRUD

## 목적
사용자가 자기 일정을 앱에서 보고(틈새 추천 근거 확인), 운동 일정을 직접 잡고 지울 수 있게 한다. ADR-034 범위: **보기 + 생성 + 삭제**(수정·반복·그리드 제외).

## 관련 ADR
ADR-034(스코프), ADR-022(연동·확답게이트), ADR-002(단일 사용자). 백엔드 gcal 네임스페이스 재사용(ADR-020 로컬 히트맵과 분리 유지).

## 작업 항목

### 9c-1. 백엔드 — gcal 어댑터/엔드포인트 확장
- `app/adapters/calendar/client.py`:
  - `list_events(time_min, time_max) -> list[CalEvent]` — 제목+시작+종료+id(우리 마커 무관, 전체 일정). all-day 는 표시만(시간 없음).
  - `insert_event(start, end, summary) -> id` — 일반 일정 생성(운동 마커 없이; 기존 `insert_workout_event` 는 유지).
  - `delete_event(event_id) -> None`.
- `app/pipecat_services/calendar_sync.py`: `list_events_today/week`, `create_event`, `delete_event` 오케스트레이션(미연동/오류 → 빈/예외 degrade, asyncio.to_thread).
- `app/api/gcal.py`:
  - `GET /api/gcal/events?from=&to=` → `[{id,summary,start,end,all_day}]`
  - `POST /api/gcal/events` `{summary,start,duration_min}` → 생성(사용자 명시 액션 = 즉시, 운동 플랜 등록의 확답게이트와 별개).
  - `DELETE /api/gcal/events/{id}` → 삭제.
- 미연동 시 events 는 빈 목록 + connected=false 신호.

### 9c-2. 프론트 — 기록 탭에 캘린더 뷰
- `ui/src/api/client.ts`: `listGcalEvents`, `createGcalEvent`, `deleteGcalEvent` + 타입.
- `ui/src/screens/Calendar.tsx`(기존 기록/히트맵 탭): 위쪽에 **"내 일정"** 패널 추가.
  - 미연동: "설정에서 캘린더를 연동하면 일정이 보여요" 안내(설정 링크).
  - 연동됨: 오늘/이번 주 일정 목록(시간·제목) + 빈 시간 표시 + **일정 추가** 폼(제목/날짜/시각/길이) + 각 항목 **삭제** 버튼.
  - 히트맵(로컬 운동기록, ADR-020)은 그대로 아래 유지 — 둘은 다른 데이터임을 라벨로 구분.
- 컴포넌트 `MySchedulePanel`(또는 Calendar.tsx 내). client.ts 경유만(직접 fetch 금지).

### 9c-3. 테스트
- 백엔드: gcal events 엔드포인트(어댑터 mock) — list/create/delete + 미연동 degrade. ruff/pytest 비-GPU.
- 프론트: `MySchedulePanel` vitest — 미연동 안내 / 목록 렌더 / 추가 호출 / 삭제 호출(client mock).
- 실세션: `scripts/verify_session` 류로 events 생성→조회→삭제 스모크(선택).

## Definition of Done
- [ ] 기록 탭에서 연동 시 오늘/이번 주 일정이 제목+시간으로 보임.
- [ ] 일정 추가/삭제가 실제 Google Calendar에 반영.
- [ ] 미연동/오프라인 시 안내 + 코칭/히트맵 무영향(degrade).
- [ ] ADR-020 히트맵과 시각적·코드적 분리 유지.
- [ ] vitest + tsc + build + 비-GPU pytest + ruff 통과. 사람 검증(실제 구글 계정)은 C-3 연장선.

## 비목표 (ADR-034)
일정 수정(edit)·반복·참석자·알림·다중 캘린더·월간 그리드·드래그. → 필요 시 별도.
