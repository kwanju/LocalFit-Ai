# Phase 8 — 운동 캘린더 + 코치 컨텍스트 강화

## 목적

운동 기록 캘린더 시각화(연간 히트맵)를 구현하고, 같은 데이터를 능동 코치 컨텍스트 빌더에 자동 주입하여 캘린더 기반 능동 제안을 가능하게 한다.

## 사전 조건

- Phase 7 완료 (UI 재배선 + 음성 파이프라인 검증)
- 능동 코치(phase-5)가 동작 중 — 컨텍스트 빌더에 데이터 주입 가능 상태

## 관련 ADR

- ADR-020 (운동 캘린더 시각화) — **본 phase의 단일 진실 소스**
- ADR-008 (DB, Repository)
- ADR-013 (능동 코치 컨텍스트)
- ADR-012 (4계층 분리)

## 작업 항목

### 8-1. 강도 산정 + 일별 집계 (Domain Core)

- `app/core/calendar_metrics.py` 신규
- 순수 함수만 (외부 의존성 0)
- `aggregate_daily(sessions: list, set_logs: list, conditions: list) -> list[DayStat]`
- `compute_level(volume_today, max_volume_30d) -> int (0~4)`
- 운동별 강도 가중치 상수 (`EXERCISE_INTENSITY = {"풀업": 1.0, "푸시업": 1.0, "스쿼트": 1.0, "플랭크": 1.0}` — MVP 단순화)
- `compute_weekly_pattern(sessions) -> WeeklyPattern` — 요일별 빈도 분석 (코치 컨텍스트용)
- `compute_last_exercise_dates(sessions) -> dict[str, date]` — 운동별 마지막 수행일
- `detect_rest_streak(sessions, now) -> int` — 연속 휴식일 수

### 8-2. Repository 확장 (DB)

- `app/db/repositories.py`의 `SessionRepository`에 메서드 추가:
  - `async def get_range(from_: date, to: date) -> list[WorkoutSession]` — 기간 내 세션 + 관련 set_logs eager load
- 또는 `SetLogRepository.get_range`, `ConditionRepository.get_range` 분리 추가

### 8-3. 캘린더 API (Backend)

- `app/api/calendar.py` 신규
- `GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD`
- 응답 스키마 (Pydantic):
  ```python
  class DayStat(BaseModel):
      date: date
      level: int  # 0~4
      volume: float
      sessions: list[SessionSummary]
      exercises: list[str]
      condition_avg: float | None
  ```
- 내부 흐름: `repos.get_range` → `calendar_metrics.aggregate_daily` → 응답
- 기본 from/to = 최근 1년 (`today - 365 days` ~ `today`)
- `app/main.py` 라우터 등록

### 8-4. UI — react-activity-calendar 통합

- `pnpm -F ui add react-activity-calendar`
- `ui/src/api/calendar.ts` — API 클라이언트 (fetch wrapper)
- `ui/src/components/CalendarHeatmap.tsx` — `<ActivityCalendar>` 래퍼
  - data 변환: API 응답 → `{date, count, level}` (react-activity-calendar 포맷)
  - tooltip: 운동 요약 ("푸시업 3×12 + 스쿼트 3×15, 컨디션 7/10")
  - color scheme: Tailwind 색 톤에 맞춤 (level 0 = `gray-100`, level 4 = `green-600` 같은)
- `ui/src/components/DayDetailModal.tsx` — 날짜 클릭 시 상세 모달
  - Tailwind dialog (Radix UI 없이도 충분, 추가 라이브러리 0)
  - 표시: 세션 시작/종료 시각, 운동·세트·렙, 컨디션, 메모
- `ui/src/screens/Calendar.tsx` — 메인 화면
  - 헤더: "운동 기록" + 연도 선택 dropdown
  - 본문: CalendarHeatmap
  - 빈 상태: "아직 운동 기록이 없어요. 첫 세션을 시작해보세요!" + 세션 시작 버튼
- `ui/src/App.tsx` — 라우팅 `/calendar` 추가
- SessionLive 헤더에 "기록" 메뉴 링크 추가

### 8-5. 코치 컨텍스트 강화 (ADR-013 연계)

- `app/core/coach_context.py`의 `CoachContextBuilder.build()`에 추가 데이터 inject:
  - 주간 패턴: `WeeklyPattern.summary()` → "월·수·금 주 3회 패턴"
  - 마지막 운동: 직전 7일 내 수행한 운동 + 5일 이상 미수행 운동 ("푸시업 마지막 = 5일 전")
  - 휴식 streak: 2일 이상이면 "최근 2일 휴식 중"
- 시스템 프롬프트 (`ACTIVE_COACH_PROTOCOL`)에 안내: "사용자의 캘린더 패턴을 자연스럽게 언급해서 능동 제안을 한다 (예: '지난주 화요일처럼 푸시업 어떠세요?')"

### 8-6. 빈 상태 가드

- DB에 세션 0건 → 캘린더 진입 시 빈 상태 UI
- 최근 7일 데이터만 있으면 1주일 strip 뷰 (전체 연간이 비어 보이는 것 방지)

### 8-7. 테스트

- `tests/test_calendar_metrics.py` — 강도 산정·집계 단위 테스트
- `tests/test_calendar_api.py` — TestClient로 `/api/calendar` 응답 검증 (mock repo)
- `tests/test_session_repository_range.py` — 기간 조회 단위 테스트
- `tests/test_coach_context_calendar.py` — 컨텍스트 빌더가 주간 패턴·마지막 운동을 포함하는지 검증

UI 테스트는 phase-7과 동일하게 수동 위주.

### 8-8. 수동 검증

- `docs/qa-checklist-v4.md`에 캘린더 섹션 추가:
  - 빈 DB 상태 캘린더 진입 → 빈 상태 UI
  - 1주일 데이터로 1주일 strip 뷰
  - 1년치 데이터로 연간 히트맵 + 색 강도 자연스러움
  - 날짜 클릭 → 상세 모달 정상 표시
  - 능동 코치 인사가 캘린더 패턴 언급 ("지난주처럼", "5일 만에")

## Definition of Done

- [ ] `GET /api/calendar` 정상 응답 (mock 데이터로 통합 테스트 통과)
- [ ] `/calendar` 화면 진입 시 연간 히트맵 정상 표시
- [ ] 날짜 hover → tooltip, 클릭 → 상세 모달
- [ ] 빈 DB 상태 빈 상태 UI 정상
- [ ] 능동 코치 인사 응답에 캘린더 패턴 언급 (수동 검증 — LLM 응답 5회 중 3회 이상)
- [ ] ruff + pytest 통과, pnpm typecheck + build 통과
- [ ] git commit `feat(phase-8): 운동 캘린더 + 코치 컨텍스트 강화`

## 리스크

- 강도 산정 식이 단순 (모든 운동 가중치 1.0) — 실제 사용 후 사용자가 "풀업 1회 = 푸시업 1회와 같지 않다"는 피드백 줄 가능. 가중치는 config로 조정 가능하게 두기
- react-activity-calendar의 Tailwind 통합 — color scheme이 inline style일 가능성. 라이브러리 옵션 확인 후 Tailwind theme variable 사용 검토
- 능동 코치 LLM이 캘린더 데이터를 "자연스럽게" 사용하지 못할 수 있음 — 프롬프트 튜닝 필요

## 소요 추정

2~3일 (백엔드 1일 + UI 1~1.5일 + 코치 컨텍스트 강화 + 검증 0.5일).

## v3-rewrite 종료 기준 (phase-8 포함)

- phase 1~8 모두 통과
- PRD v4 §7-1 출시 체크리스트 (캘린더 항목 포함) 통과
- 사용자 수동 검증 통과 + 만족
- master 브랜치에 머지 (사용자 명시 승인 필수)
