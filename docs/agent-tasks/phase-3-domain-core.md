# Task: Phase 3 — 도메인 코어 (Safety / Intent / Counting)

3개 하위 작업. 각각 별도 세션 권장. Safety → Intent → Counting 순.

## 공통 배경 자료
- `AGENTS.md`
- `docs/prd-v3.1.md` 6장 + 부록 B (안전), 3장 (의도·카운팅), 5장 (카운팅 설정)
- `docs/conventions/coding-style.md` 7번 (박자 스케줄러)

---

## 3A. Safety Guard (최우선)

### 배경
- PRD 6장, 부록 B-1 (4단계 부상 대응), B-2 (LLM 안전 프롬프트)

### 작업
1. `app/core/safety.py` — SafetyGuard 클래스. 키워드 매칭 (정규식), 4단계 위험도(낮음/중간/높음/응급)
2. `app/prompts/safety.py` — 단계별 안전 응답 한국어 템플릿 (app/messages.py 활용)
3. 부상 키워드 최소 20개 (PRD 미결 사항 #4) — 변형 표현 포함
4. `tests/unit/test_safety.py` — 키워드 20개 변형 테스트, 커버리지 높게

### 제약
- LLM 호출 없는 순수 규칙 기반 (응급은 LLM 우회)
- core 모듈 = 순수 Python (외부 의존 0)

---

## 3B. Intent Classifier

### 배경
- PRD 3-1 (의도 5종: 몸상태·일정·피드백·목표·일반)

### 작업
1. `app/core/intent.py` — IntentClassifier. LLM 어댑터 주입받아 6종 분류 (5종 + injury)
2. `app/prompts/coaching.py` — 의도 분류 프롬프트 + 의도별 응답 프롬프트
3. 폴백: 분류 실패 시 "general"
4. `tests/unit/test_intent.py` — Mock LLM 사용

### 제약
- LLM 어댑터 경유 (ADR-010)
- 시스템 프롬프트 최상단에 안전 규칙 (PRD 부록 B-2)

---

## 3C. Counting Engine

### 배경
- PRD 5장 (운동별 모드, 카운팅 설정값)

### 작업
1. `app/core/counting.py` — CountingEngine. 메트로놈/타이머 모드. time.monotonic() 기반
2. `app/utils/timer.py` — 절대시각 박자 스케줄러 (drift 방지)
3. 이벤트 발행 (Orchestrator가 구독할 형태)
4. `tests/unit/test_counting.py` — 박자 정확도 ±10% 검증 (PRD 7-1)

### 제약
- LLM과 독립 (LLM 지연 중에도 카운팅 지속, PRD 4-1)
- sleep 누적 금지 (coding-style.md 7번)
- 4종 운동 박자: 풀업/푸시업/스쿼트(메트로놈), 플랭크(타이머)

## 완료 기준 (3 전체)
- 3개 모듈 단위 테스트 통과
- Safety 커버리지 80%+
- 박자 정확도 ±10% 확인

## 자가 보고
각 하위 작업마다 AGENTS.md 9번. checklist A·B·C·D·E·F 확인.
