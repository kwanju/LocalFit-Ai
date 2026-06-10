# Phase v4-4 — 운동 플랜 (주간 목표 + 조정은 확인)

## 목적

단발 `propose_set`(고정값)을 넘어 **주간 목표 + 일자 분배**로 격상한다(ADR-024). 컨디션(phase 3)·기준선(메모리 1층, phase 2/5)을 입력으로 강도를 조절하되, **모든 조정은 코치 제안 → 사용자 동의** 후 적용한다. 회고가 가장 강하게 경고한 "LLM 이 확답 없이 플랜을 마음대로 바꾸는 패턴"을 구조적으로 차단한다.

## 사전 조건

- Phase v4-2(메모리 1층 `fitness_baseline` 스키마)·v4-3(컨디션 입력) 완료
- 기존 자산: `app/core/coach_response.py`(`ProposeSetAction` 등 액션 유니온), `app/pipecat_services/processors/confirm_rule.py`·`action_dispatcher.py`, `app/db/repositories.py`(`RoutineRepository`)

## 관련 ADR

- **ADR-024** — 주간 목표 + 일자 분배, 조정은 확인(자동변경 금지), tool-use
- ADR-013 — 능동 코치 instructor + 확답 게이트(plan tool-use 확장)
- ADR-023 — 컨디션 = 강도 조절 입력 / ADR-025 — 기준선·제약
- ADR-029 — tool-use 정확도는 9b 검증에 의존(phase 1 게이트)

## 작업 항목

### 4-1. DB — 플랜 모델

- `weekly_plan`/`weekly_goal`(주간 목표: 종목·횟수·기간) + 일자 분배(`plan_day` 또는 기존 `Routine`/`RoutineExercise`(models.py:61·71) 재활용 검토). 진척 추적 필드(목표 대비 완료).
- 기준선 참조: 메모리 1층 `fitness_baseline`(phase 2 스키마, phase 5 가 채움). 부상/제약은 항상 안전 가드로 반영(메모리 전량 주입).
- 마이그레이션: phase v4-1 스캐폴드 스텝.

### 4-2. tool-use — 플랜 제안 액션

- `CoachAction` 유니온(coach_response.py)에 플랜 액션 추가:
  - `ProposePlanAction`(주간 목표 제안) / `ProposePlanAdjustmentAction`(컨디션·실패 기반 조정 제안).
- **실행(저장/변경)은 확답 게이트 통과 후**만 — `confirm_rule.py` 재활용. `action_dispatcher.py` 에 디스패치 연결.
- LLM 이 plan/db 를 도구로 호출해 제안 생성(instructor 확장). 카운팅 시작 실행은 기존 `StartCountingAction` 확답 흐름 유지.

### 4-3. 구현 순서 (ADR-024 점진)

- **1단계(이 phase 핵심)**: 주간 목표 세팅 + 일자 분배 + 진척 추적.
- **2단계**: 컨디션 기반 자동 *제안*(확인) — phase 3 컨디션 레이어가 안정된 상태이므로 얹는다.
- 자동 *변경*은 어느 단계에서도 금지.

### 4-4. 코치 컨텍스트 — 플랜·진척 주입

- `CoachContextBuilder` 에 현재 주간 목표·진척(예: "이번 주 푸시업 1/3 완료") 요약 주입. 토큰 예산 내.

### 4-5. fallback (안 행복한 경로)

- 목표 미설정 → 일일 자유 단발 제안(현행 `ProposeSetAction`)으로 fallback.
- 목표 실패 누적 → 코치가 "목표를 낮출까요?" **제안(확인)**.

## Definition of Done

- [ ] 플랜 모델 + 마이그레이션 적용, `PlanRepository`(또는 Routine 확장) 테스트
- [ ] 주간 목표 설정 → 일자 분배 → 진척 추적 동작 E2E 사람 확인
- [ ] 플랜 조정이 **반드시 확답 게이트**를 거침을 테스트로 증명(동의 없이는 미적용) — 회귀 가드
- [ ] 목표 미설정 시 단발 제안 fallback 동작
- [ ] 컨텍스트에 주간 목표·진척 반영
- [ ] ruff + pyright, pytest 비-GPU, `cd ui && pnpm test` 통과
- [ ] git commit `feat(v4-4): 주간 목표 플랜 + 일자 분배 + 조정 확인 게이트`

## 명시적 비목표

- 컨디션/실패 기반 **자동 변경**(금지)
- Google Calendar 일정 연동(phase 9)
- 월간 리뷰 자동 생성(후순위)

## 소요 추정

1.5~2일.

## 다음 phase

Phase v4-5 — 첫 세션 대화형 체력검증(ADR-028). 인덱스: [`README.md`](README.md).
