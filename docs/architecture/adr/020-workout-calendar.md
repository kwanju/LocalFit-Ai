# ADR-020: 운동 캘린더 시각화 — react-activity-calendar + 강도 히트맵

- **상태**: Accepted (2026-06-01)
- **관련 ADR**: ADR-008 (DB), ADR-010 (UI), ADR-013 (능동 코치 컨텍스트)
- **번호 주의**: v2 시점에도 ADR-020("데스크탑 패키징")이 있었으나 폐기 후 `_archive/v1/020-desktop-packaging.md`로 보존됨. v3-rewrite에서는 020을 새 결정(운동 캘린더)으로 재사용한다. 이전 020을 찾는 사람은 archive 폴더 참조.

## 컨텍스트

PRD v4 §3-1 (P0)에 "운동 기록 + 루틴 분석" 항목이 있고, v1 DB 모델 (`WorkoutSession`, `SetLog`, `ConditionLog`)은 이미 운동 기록을 적재한다. 그러나 v1·v3 초안에는 **사용자가 과거 기록을 한눈에 확인하는 시각화가 없었다.** 또한 능동 코치(ADR-013)가 "최근 5세션 요약"만 가져가서 주간/월간 패턴을 활용하지 못한다.

본 ADR은:
1. 사용자에게 **운동 빈도·강도를 한눈에 보여주는 캘린더 화면**을 추가하고,
2. 같은 데이터를 **능동 코치 컨텍스트에 자동 주입**하여 "지난주 화요일에 푸시업 하셨네요, 오늘도 같은 운동 어떠세요?" 같은 캘린더 기반 능동 제안을 가능하게 한다.

### 라이브러리 후보 비교 (2026-06-01)

| 라이브러리 | 의존성 무게 | 적합성 | 평가 |
|---|---|---|---|
| **react-activity-calendar** | ~30KB, 외부 의존 0 | GitHub 잔디 정확 재현, TS, level 0~4 강도, tooltip | ✅ 운동 빈도 시각화 최적 |
| @uiw/react-heat-map | ~25KB | 가벼움, SVG | 비슷한 좋은 대안 |
| react-calendar-heatmap (kevinsqi) | ~30KB | 표준격, 잘 알려짐 | 업데이트 빈도 낮음 |
| shadcn-heatmap | copy-paste 컴포넌트 | shadcn/ui 의존 | 우리는 shadcn/ui 미사용 — 코드 수정 부담 |
| @nivo/calendar | ~200KB+ (D3) | 강력함 | 무거움, over-engineering |
| @fullcalendar/react | 매우 무거움 | 일정 관리 시스템 | use case 불일치 |
| react-calendar (zackify) | 가벼움 | 월간 뷰만 | 히트맵 없음 — use case 미달 |

운동 기록은 "1년치 빈도·강도를 한눈에"가 직관적이라 GitHub 잔디 패턴이 적합. 라이브러리 무게·TS 지원·tooltip·활성 유지보수 종합 시 **react-activity-calendar**가 최적.

## 결정

### 캘린더 라이브러리 = react-activity-calendar

- `pnpm -F ui add react-activity-calendar`
- 메인 화면: 연간 히트맵 (가로 스크롤 또는 반응형 줄바꿈)
- 각 셀: 하루의 운동 강도를 level 0~4로 표현
- tooltip: hover 시 해당 날짜의 운동 요약 ("푸시업 3×12 + 스쿼트 3×15, 컨디션 7/10")
- 클릭: 해당 날짜 상세 모달 (Tailwind dialog — 추가 라이브러리 0)

### 강도 산정 식 (level 0~4)

```
volume_today = Σ (set_log.reps * set_intensity_factor)
              for set in WorkoutSession.set_logs of that day
max_volume_30d = max(volume) over last 30 days (rolling)

level = 0   if 운동 없음
      = 1   if volume_today / max_volume_30d <= 0.25
      = 2   if <= 0.50
      = 3   if <= 0.75
      = 4   if >  0.75
```

`set_intensity_factor`는 운동별 가중치 (예: 풀업=1.5, 푸시업=1.0, 스쿼트=1.0, 플랭크=0.8 — `app/core/calendar_metrics.py`에 상수로). 단순화를 위해 MVP는 모두 1.0으로 시작하고 사용자 피드백 후 조정.

### 백엔드 API

```
GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD
→ [
    {
      "date": "2026-05-30",
      "level": 3,
      "volume": 124.0,
      "sessions": [{"id": 42, "started_at": "...", "duration_min": 35}],
      "exercises": ["푸시업", "스쿼트"],
      "condition_avg": 7.0
    },
    ...
]
```

- `SessionRepository.get_range(from, to)` (신규) — 기간 내 세션 + 세트 로그 + 컨디션 join
- `app/core/calendar_metrics.py` (신규) — 강도 산정 + 일별 집계 순수 함수 (Domain Core, ADR-012 정합)
- `app/api/calendar.py` (신규) — REST 엔드포인트

### UI 화면

```
ui/src/screens/Calendar.tsx     # 메인 (연간 히트맵 + 모달)
ui/src/api/calendar.ts          # API 클라이언트
ui/src/components/CalendarHeatmap.tsx   # react-activity-calendar 래퍼
ui/src/components/DayDetailModal.tsx    # 날짜 클릭 시 상세
```

라우팅: `/calendar` (React Router)
네비게이션: SessionLive 헤더에 "기록" 메뉴 추가

### 능동 코치 컨텍스트 강화 (ADR-013 연계)

`CoachContextBuilder.build()`에 다음 데이터 추가:

- **주간 패턴 요약** — 최근 4주 요일별 운동 빈도 ("월·수·금 주 3회 패턴")
- **마지막 운동 메타** — 운동별 마지막 수행일 ("푸시업 마지막 = 5일 전")
- **휴식일 검출** — 연속 휴식 2일 이상 시 플래그

이 데이터는 `app/core/calendar_metrics.py`에서 산정해서 컨텍스트 빌더가 사용. ADR-013 본문에 상세 명세 (ADR-020에서는 데이터 표면만 명시).

### 캘린더 진입 가드

- DB가 비어 있으면 "아직 운동 기록이 없어요. 첫 세션을 시작해보세요!" 빈 상태 UI
- 최근 1주일 이내 데이터만 있으면 1주일 뷰만 표시 (히트맵 strip 1줄)

## 결과

### 긍정
- 사용자가 과거 운동 패턴을 한눈에 확인 — 동기 부여 + 자기 인식
- 능동 코치가 캘린더 데이터로 더 자연스러운 제안 가능 ("지난주처럼", "5일 만에")
- react-activity-calendar는 가볍고 검증됨 — 의존성 부담 작음
- 백엔드 변경 최소 (DB 모델 0, Repository read 1개 신규, API 1개 신규)

### 부정
- UI 신규 화면 1개 (Calendar.tsx) + 컴포넌트 2개 — phase-8 작업량 추가
- 강도 산정 식이 단순 (volume 기반) — 향후 운동별 가중치 튜닝 필요할 수 있음
- 능동 코치 컨텍스트 토큰 증가 (~100자) — qwen3:8b는 영향 미미

## 대안

| 후보 | 탈락 사유 |
|---|---|
| 캘린더 기능 미구현 (MVP에서 빠뜨림) | 사용자 직접 요구 — P0 |
| @nivo/calendar | 200KB+ 무거움, D3 의존 |
| 직접 SVG 작성 | "바퀴 재발명 금지" 원칙 위반, 라이브러리 30KB로 충분 |
| 월간 캘린더 뷰 (react-day-picker)만 | 히트맵 강도 표현 없음, 빈도 한눈에 안 들어옴 |
| 두 가지 뷰 동시 (월간 + 히트맵) | MVP 복잡도 — 히트맵 단독으로 충분, 월간 뷰는 P1 검토 |

## 후속

- 운동별 강도 가중치 튜닝 (사용자 피드백 후)
- 월간 캘린더 뷰 (날짜별 상세 보기) P1 검토
- 패턴 분석 자동 인사이트 ("목요일마다 컨디션이 낮으시네요") — PRD §부록 G(P1) 연계
- 외부 캘린더(Google Calendar) 연동 — P2

## References
- [react-activity-calendar](https://github.com/grubersjoe/react-activity-calendar) — 활성 유지보수
- [react-calendar-heatmap (참고)](https://github.com/kevinsqi/react-calendar-heatmap)
- v1 DB 스키마 — `app/db/models.py` (WorkoutSession·SetLog·ConditionLog)
