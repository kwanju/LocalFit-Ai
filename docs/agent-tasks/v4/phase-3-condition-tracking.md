# Phase v4-3 — 컨디션 트래킹 (자가보고 체크인)

## 목적

세션 전/일일 **자가보고 체크인**(피로·근육통 + 선택 메모)을 받아, 코치가 이를 읽고 **강도 조절을 제안**(확인 후 적용, 자동변경 금지)하게 한다(ADR-023). v4 비전의 차별점인 "컨디션 기반 코칭"의 입력 레이어.

> 기존 자산이 많다: `ConditionLog` 테이블·`ConditionRepository`·`LogConditionAction`·`CoachContextBuilder` 의 `latest_condition` 주입이 **이미 존재**. 이 phase 는 그것을 **체크인 UX + soreness + 강도 제안**으로 확장하는 작업이다.

## 사전 조건

- Phase v4-2 완료(메모리 2층 — 자유 메모를 2층과 연계 가능)
- 기존 자산 확인: `app/db/models.py:113`(`ConditionLog`: session_id·fatigue_level·pain_report·notes), `app/db/repositories.py:130`(`ConditionRepository`), `app/core/coach_response.py`(`LogConditionAction`), `coach_context.py`(latest_condition 주입)

## 관련 ADR

- **ADR-023** — 자가보고 체크인(선택형), 외부 건강 API 미연동, 강도 조절은 ADR-024 확인 게이트
- ADR-024 — 컨디션은 플랜 강도 조절의 **입력**(조절 실행은 phase 4)
- ADR-025 — 자유 메모는 메모리 2층과 연계
- ADR-002 — 로컬-only(외부 건강 API 금지)

## 작업 항목

### 3-1. 데이터 모델 — 체크인 (★ 결정 포인트)

- ADR-023 은 `condition_checkins(date, fatigue, soreness, note)`(일일·세션 독립)를 언급. 현 `ConditionLog` 는 **session_id 종속**.
  - **결정 필요**: (a) `ConditionLog` 확장(`soreness` 추가 + `session_id` nullable 로 세션 전 일일 체크인 허용) vs (b) 신규 `condition_checkin` 테이블.
  - **권장 (a)**: 기존 repo/컨텍스트 재활용 최대화. 세션 시작 전 체크인은 `session_id=None` 으로 저장하고 세션 생성 시 연결. soreness(1~5) 컬럼 추가.
  - 메모리 노트(컨디션 자유메모 저장처: 023.note vs 025 2층) 여기서 확정 — **note 는 ConditionLog 에, 부드러운 선호로 승격할 것만 메모리 2층 `add_fact`**.
- 마이그레이션: phase v4-1 스캐폴드 스텝으로 컬럼 추가(멱등).

### 3-2. 체크인 UX (UI)

- 세션 시작 전(또는 일일) 간단 입력: 피로·근육통 척도 + 선택 자유 메모. **선택형(건너뛰기)** — 건너뛰면 기본 강도(ADR-023).
- 3모드(phase 1) 정합 — C2C/C2S/S2S 어디서 시작하든 체크인 진입 가능.
- v3 UI 자산(`ui/src/screens/*`) 스타일 따름. 신규 화면 최소.

### 3-3. 코치 컨텍스트 — soreness/메모 주입

- `CoachContextBuilder` 의 `latest_condition`(현재 피로도만, coach_context.py:121-130)에 **근육통·메모 요약** 추가. 토큰 예산 내.
- `LogConditionAction`(coach_response.py:32) 확장 — `soreness` 필드 추가, 코치가 대화 중 컨디션을 받아 기록.

### 3-4. 강도 조절 제안 (확인 게이트 — phase 4 연계)

- 컨디션 신호 → 코치가 **"오늘 피곤하시니 강도 낮출까요?" 제안** → `app/pipecat_services/processors/confirm_rule.py`(기존) 경유 동의 → 적용.
- **자동 강도 변경 금지**(회고 ConfirmRule 정신, ADR-023/024). 이 phase 는 *제안*까지, 플랜 반영 실행은 phase 4.

## Definition of Done

- [ ] 체크인 데이터 모델 확정(soreness + 세션-독립) + 마이그레이션 적용
- [ ] `ConditionRepository` 확장 테스트(세션 전 체크인 → 세션 연결)
- [ ] 체크인 UX 에서 입력/건너뛰기 동작 — 사람 확인
- [ ] 코치 컨텍스트에 피로+근육통+메모 반영 → "피곤하면 강도 낮출까요?" **제안(확인)** E2E 사람 확인
- [ ] 컨디션이 사용자 동의 없이 강도를 **자동 변경하지 않음**을 확인(회귀 가드)
- [ ] ruff + pyright, pytest 비-GPU, `cd ui && pnpm test` 통과
- [ ] git commit `feat(v4-3): 자가보고 컨디션 체크인 + 강도 조절 제안(확인)`

## 명시적 비목표

- Apple Health / Google Fit 등 외부 건강 API (ADR-023 후순위)
- 컨디션 기반 **자동** 강도 변경 (금지)
- 플랜 반영 실행(phase 4)

## 소요 추정

1일.

## 다음 phase

Phase v4-4 — 운동 플랜(ADR-024). 인덱스: [`README.md`](README.md).
