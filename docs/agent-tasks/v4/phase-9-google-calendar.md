# Phase v4-9 — Google Calendar 연동 (OAuth2 Desktop)

## 목적

운동 일정을 Google Calendar 와 연동한다(ADR-022). 폰 등 기기 간 동기화 + 미팅 같은 **기존 일정을 읽어 틈새 시간 추천**이 목표. 능동 알림 스케줄러(phase 8)의 **일정 소스를 로컬 스케줄 → 캘린더로 확장**한다. v4 phase 중 **최후순위**(외부 API·OAuth, 로컬-only 완화).

> ⚠️ **이름 충돌 주의**: 기존 `app/api/calendar.py`(`/api/calendar`)는 **v3 운동 히트맵**(ADR-020, 로컬 DB 통계)이고 **Google Calendar 가 아니다**. 본 phase 의 신규 연동은 **별도 네임스페이스**(예: `app/adapters/calendar/`(gcal) + `app/api/gcal.py`)로 둬서 ADR-020 히트맵과 절대 섞지 않는다.

## 사전 조건

- Phase v4-4(플랜 = 등록할 운동 일정 소스)·v4-8(스케줄러/알림 = 캘린더 소비처) 완료
- **사용자 확인 필요**: 신규 의존성 `google-api-python-client` + `google-auth-oauthlib`(CLAUDE.md §8 — 추가 전 사용자 승인). Google Cloud 프로젝트 + OAuth Desktop client 자격증명(사용자 발급)
- 기존 자산(혼동 방지용 확인): `app/api/calendar.py`(ADR-020 히트맵), `app/core/calendar_metrics.py`, `CoachContextBuilder.calendar_signals_fn`(히트맵 신호 hook — 이것도 ADR-020 계열)

## 관련 ADR

- **ADR-022** — Google Calendar API, OAuth2 Desktop, 등록은 확인, 다른 일정 읽어 틈새 추천
- ADR-027 — 스케줄러/알림(캘린더가 일정 소스) / ADR-021 — 로컬-only 완화는 캘린더에 한함
- ADR-002 — 단일 사용자 본인 계정 1개(멀티계정·`user_id` 분기 금지)
- ADR-013 — 일정 등록은 확답 게이트(자동 등록 금지)

## 작업 항목

### 9-1. OAuth2 Desktop 흐름 + 토큰 저장

- OAuth2 Desktop client: 최초 1회 브라우저 동의 → refresh token 획득.
- **토큰 안전 저장**: OS 자격증명 저장소 또는 **암호화 파일**(평문 금지 — 로컬-only 완화의 보안 책임, ADR-022 부정 항목). 이후 자동 갱신.
- 단일 사용자(계정 1개)라 다계정 분기 코드 금지(ADR-002).

### 9-2. 운동 일정 등록 (확인 게이트)

- 코치가 일정을 캘린더에 등록 시 **반드시 사용자 확인 후** 기록(ADR-022/013 — 자동 등록 금지). `confirm_rule.py`(기존) 재활용.
- 소스 = phase 4 주간 플랜의 일자 분배 → 캘린더 이벤트.

### 9-3. 다른 일정 읽기 → 틈새 추천

- 캘린더 free/busy 읽어 빈 시간 계산 → "오늘 저녁 8시까지 비어 있으니 그때 어때요?" 능동 제안.
- `CoachContextBuilder` 에 **새 캘린더 신호**(오늘 빈 시간대) 주입 — ADR-020 히트맵 신호와 **별도 필드**로(혼동 방지). 토큰 예산 내.

### 9-4. 스케줄러 소스 확장 (phase 8 연계)

- phase 8 트레이 스케줄러의 일정 소스를 **로컬 스케줄/플랜 → 캘린더 이벤트**로 확장. 캘린더 우선, 미연동 시 로컬 fallback.

### 9-5. 안 행복한 경로 (★ ADR-022, 회고 원칙 1)

- 캘린더 없음/연동 거부 → **로컬 스케줄 fallback**(phase 8), 캘린더 기능만 비활성(나머지 코칭 정상).
- 토큰 만료/오프라인/Google 장애 → 캘린더 기능 **graceful degrade**, 로컬 스케줄·코칭 계속.
- 모든 외부 호출 실패는 `logger.error` + 사용자 안내(ADR-018) — 무시 금지.

## Definition of Done

- [ ] OAuth2 동의 1회 → 토큰 안전 저장 → 재시작 후 자동 갱신(평문 저장 아님 확인)
- [ ] 운동 일정 등록이 **확답 게이트**를 거침(동의 없이는 미등록) — 회귀 가드
- [ ] 다른 일정 읽어 틈새 시간 제안 E2E 사람 확인
- [ ] phase 8 스케줄러가 캘린더 이벤트를 소스로 알림 발생
- [ ] **미연동/오프라인 시 로컬 fallback** 으로 graceful degrade(코칭 안 죽음)
- [ ] ADR-020 히트맵(`/api/calendar`)과 신규 gcal 네임스페이스가 분리됨(혼동 0)
- [ ] 신규 의존성은 사용자 승인 후 `uv add`. ruff + pyright, pytest 비-GPU(외부 API 는 mock) 통과
- [ ] git commit `feat(v4-9): Google Calendar 연동(OAuth2) + 틈새 추천`

## 명시적 비목표

- CalDAV/타 캘린더 범용 연동(ADR-022 탈락 — Google 직접)
- 자동 일정 등록(확인 없음 — 금지)
- 멀티 계정/멀티 유저(ADR-002)
- 운동 기록·메모리·음성의 외부 동기화(로컬 유지 — 완화는 캘린더 한정)

## 소요 추정

2일 (OAuth 흐름 + 토큰 보안 저장 + fallback 검증).

## 다음 phase

(v4 phase 인덱스 종료) — 인덱스: [`README.md`](README.md).
