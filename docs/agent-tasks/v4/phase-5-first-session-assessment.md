# Phase v4-5 — 첫 세션 대화형 체력검증

## 목적

신규 사용자의 첫 세션을 **대화형 체력검증 + 함께 계획 세우기**로 격상한다(ADR-028). v3 의 고정값(푸시업 10회 3세트) 대신, 온보딩 폼 값을 **시드**로 코치가 대화로 확인·보정하고 **보수적 시작 강도**(예: 70%)를 합의해 `fitness_baseline`(메모리 1층)에 저장한다. 이것이 플랜(phase 4)·컨디션 조절의 공통 기준선이 된다. v4 "대화형 코칭"의 첫 적용 사례.

## 사전 조건

- Phase v4-2(메모리 1층 `fitness_baseline`)·v4-4(플랜 기준선 소비) 완료
- 기존 자산: `ui/src/screens/Onboarding.tsx`(체력 측정 입력칸), `app/api/onboarding.py`, `app/core/coach_response.py`(액션 유니온), `app/core/coach_context.py`(신규 사용자 판정: effective_sessions 빈 리스트 = "신규 사용자")

## 관련 ADR

- **ADR-028** — 첫 세션 대화형 체력검증(자가보고, 실측 세트 X, 보수적 시작, 재평가 트리거)
- ADR-025 — `fitness_baseline` 1층 저장 / ADR-024 — 플랜 입력
- ADR-013 — 능동 코치(단발 propose_set → 대화형 plan-building tool-use)

## 작업 항목

### 5-1. 첫 세션 감지

- "기준선 없음 + 운동 기록 없음"을 첫 세션으로 판정. `coach_context.py` 의 effective_sessions 비었음 신호 + 메모리 1층 `fitness_baseline` 미존재 결합.
- 판정되면 일반 코칭 대신 **대화형 체력검증 흐름** 진입.

### 5-2. 온보딩 폼 시드 활용

- `Onboarding.tsx` 폼 값(풀업/푸시업/스쿼트/플랭크 최대) + `/onboarding`(api/onboarding.py) 저장값을 코치 대화의 **시드**로 로드.
- 폼 미입력(안 행복한 경로) → 대화로 처음부터 수집.

### 5-3. 대화 흐름 (★ 핵심 — 대화형 plan-building)

- 코치가 시드 값 확인/보정: 예 "푸시업 15개로 적으셨는데 맞나요? 그럼 70%인 10개로 가볍게 시작할게요."
- **자가보고만** — 실측 1세트 최대치 측정 안 함(부담·부상 위험).
- 수치 회피(안 행복한 경로) → 매우 보수적 기본값으로 시작 후 빠르게 조정.
- 합의된 시작 강도 → 첫 루틴 확정(동의 게이트, `confirm_rule.py` 재활용).
- `CoachAction` 유니온에 대화형 검증/기준선 확정 액션 추가(`SetBaselineAction` 등). 단발 `ProposeSetAction` 을 첫 세션에서는 **대화형 흐름으로 대체**.

### 5-4. 기준선 저장 + 재평가 트리거

- 합의 결과 → 메모리 1층 `fitness_baseline`(phase 2 `MemoryRepository.set_baseline`) 저장 → 플랜(phase 4)·컨디션 조절이 참조.
- 재평가 트리거: N주 경과 또는 사용자 "너무 쉬움/어려움" 피드백 → 재측정 대화 진입.

## Definition of Done

- [ ] 첫 세션 자동 감지(기준선·기록 없음) → 대화형 검증 흐름 진입
- [ ] 온보딩 폼 값이 대화 시드로 로드됨(미입력 시 대화 수집 fallback)
- [ ] 대화 → 보수적 시작 강도 합의 → **동의 후** 첫 루틴 확정(동의 없이 미확정 — 회귀 가드)
- [ ] 합의 결과가 `fitness_baseline` 1층에 저장되고 **다음 세션/플랜이 이를 기준선으로 사용** E2E 사람 확인
- [ ] 재평가 트리거("너무 쉬움" 피드백) → 재측정 대화 동작
- [ ] 9b 로 대화형 plan-building tool-use 출력 회귀 없음(phase 1 게이트 연장 확인)
- [ ] ruff + pyright, pytest 비-GPU, `cd ui && pnpm test` 통과
- [ ] git commit `feat(v4-5): 첫 세션 대화형 체력검증 + 기준선 저장`

## 명시적 비목표

- 실측 1RM/한계 테스트(부상 위험, ADR-028 배제)
- 종목 확장(ADR-026 Deferred — v3 4종 고정)
- native 런타임/알림(phase 6~8)

## 소요 추정

1.5~2일.

## 다음 phase

(도메인 트랙 종료) → native 트랙 Phase v4-6 — Tauri 셸 통합. 인덱스: [`README.md`](README.md).
