# Phase 5 — 능동 코치: instructor + Action Dispatcher

## 목적

v1에서 Accepted였지만 미구현인 능동 코치를 완수한다. instructor로 JSON 구조화 출력을 안정화하고, 액션 디스패처로 카운팅 트리거·컨디션 로깅·세트 제안을 자동화한다.

## 사전 조건

- Phase 4 완료 (STT/TTS 동작)

## 관련 ADR

- ADR-013 (능동 코치 instructor + JSON) — **본 phase의 단일 진실 소스**
- ADR-012 (Service 분리)
- ADR-018 (지연 메트릭)

## 작업 항목

### 5-1. CoachResponse 모델 (Pydantic, Domain Core)

- `app/core/coach_response.py`
- `ProposeSetAction`, `StartCountingAction`, `LogConditionAction` Pydantic 모델
- `CoachAction = ProposeSetAction | StartCountingAction | LogConditionAction` (discriminated union, `type` field)
- `CoachResponse(text: str, actions: list[CoachAction])`

### 5-2. CoachContextBuilder (Domain Core)

- `app/core/coach_context.py`
- 프로필 + 최근 5세션 + 활성 루틴 + 최근 컨디션을 700자 이내 자연어로 압축
- 시각·시간대(아침/낮/저녁/새벽) 포함
- 입력: Repository 5종 의존 주입 / 출력: str
- **캘린더 패턴 데이터(주간 패턴·운동별 마지막 수행일·휴식 streak)는 phase-8에서 보강** — phase-5 시점에는 hook만 비워두고 phase-8 진입 시 `app/core/calendar_metrics.py` 함수 호출 추가 (ADR-013 §컨텍스트 빌더, ADR-020 §능동 코치 컨텍스트 강화 참조)

### 5-3. 시스템 프롬프트 정비

- `app/prompts/coaching.py`
- `SAFETY_SYSTEM_PREFIX` (v1 자산 + 강화) — 한국어 강제 + 통증 무시 거부 + 운동 강행 권유 금지
- `ACTIVE_COACH_PROTOCOL` 신규 — **ADR-013 §시스템 프롬프트 구조의 5개 항목 모두 명시** (능동 주도 원칙 + 응답 스키마 + 응답 길이 가이드 70/120/15/500/150 + 캘린더 활용 안내 + 수용 정책)
- `INTENT_RESPONSE_PROMPT_PREFIXES` (v1) 폐기 — 의도 분기 안 함

### 5-4. StructuredOllamaService (Pipecat 통합)

- `app/pipecat_services/ollama_service.py`
- `pipecat.services.ollama.OllamaLLMService` 상속 또는 자체 LLMService
- 내부에 `instructor.from_openai(AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama"), mode=instructor.Mode.JSON)` 인스턴스 보유
- `async def generate_structured(messages) -> CoachResponse` — `response_model=CoachResponse`, `max_retries=2`
- 응답 받으면 `text` (한자 후처리 적용) + `actions` 분리해서 frame 발행

### 5-5. SafetyGuardProcessor (Pipecat FrameProcessor)

- `app/pipecat_services/processors/safety_guard.py`
- `TranscriptionFrame` 가로채서 부상 키워드 검사 (`SafetyGuardCore` 호출)
- 응급 키워드 발견 → 즉시 운동 중단 + 면책 고지 frame 발행 + LLM 호출 우회
- 일반 발화는 downstream pass-through

### 5-6. ConfirmRuleProcessor (Pipecat FrameProcessor)

- `app/pipecat_services/processors/confirm_rule.py`
- `_pending_proposal: ProposeSetAction | None` 메모리 슬롯
- 사용자 발화 처리 전 confirm 키워드 매칭 → `_pending_proposal` → `StartCountingAction` 즉시 dispatch
- 거절 키워드 → 슬롯 해제 + 일반 LLM 흐름
- 매치 없음 → 슬롯 유지 + 일반 LLM 흐름

### 5-7. ActionDispatcherProcessor (Pipecat FrameProcessor)

- `app/pipecat_services/processors/action_dispatcher.py`
- LLM 응답 frame 받으면 `actions` 디스패치:
  - `ProposeSetAction` → `_pending_proposal` 저장 (ConfirmRuleProcessor와 슬롯 공유)
  - `StartCountingAction` → `CountingEngine.start(exercise, reps)` (phase-6에서 wired)
  - `LogConditionAction` → `ConditionRepository.create(...)`
- 그 후 `text` frame을 SentenceAggregator → TTS로 downstream

### 5-8. 능동 인사 (proactive opener)

- `app/api/ws_voice.py` 세션 시작 시 `config.coach.proactive_opener` 체크
- true이면 부트스트랩 user 메시지(`(세션을 시작했습니다. 사용자에게 인사하고, 최근 운동 기록을 토대로 오늘의 추천 1건을 제안하세요.)`) 자동 inject
- 응답은 일반 처리 경로

### 5-9. 한자 후처리 재활용

- `app/core/intent.py`의 `strip_non_korean_cjk`를 `CoachResponse.text`에만 적용 (action 페이로드는 미적용)

### 5-10. 지연 메트릭

- `LatencyTracker("llm.generate_structured")` — instructor 호출 (retry 포함) 측정
- `LatencyTracker("e2e.c2c")` — 사용자 입력 → 첫 텍스트 응답

### 5-11. config 갱신

ADR-013 §config 참조. 핵심 키:
- `coach.proactive_opener: true` (§0 완화 메커니즘 (a))
- `coach.context_recent_sessions: 5`
- `coach.response_length` 섹션 (70/120/500/150)
- `coach.instructor.max_retries: 2`, `mode: "json"`

### 5-12. 테스트

- `tests/test_coach_response.py` — Pydantic 모델 schema/parse 단위 테스트
- `tests/test_coach_context.py` — Repository mock으로 context 빌더 출력 검증
- `tests/test_structured_ollama_mock.py` — instructor mock으로 retry·schema 위반 시나리오
- `tests/test_safety_processor.py` — 부상·응급 키워드 인터셉트
- `tests/test_confirm_rule.py` — 수락/거절/매치없음 시나리오
- `tests/test_action_dispatcher.py` — 3종 action 디스패치
- `tests/test_proactive_opener.py` — 세션 시작 시 LLM 1회 호출 발생 확인
- `tests/test_ws_voice_active_coach.py` — C2C 모드에서 사용자 "푸시업 10개 시작" → `StartCountingAction` 디스패치 확인
- `tests/test_response_length.py` — Pydantic `max_length=500` hard cap 검증 + 능동 응답이 70자 가이드 안에 들어오는지 (실제 LLM 호출, gpu mark)
- `tests/test_proactive_principle.py` — 사용자 거절 발화 시 LLM이 수용 응답 반환 (자체 제안 안 함) 검증

## Definition of Done

- [ ] CoachResponse Pydantic 모델 validation 통과
- [ ] instructor + Ollama로 한국어 JSON 응답 정상 (수동 LLM 호출 확인)
- [ ] 능동 인사 — 세션 시작 시 LLM 호출 1회 자동 발생
- [ ] 부상 키워드 발화 → LLM 호출 우회 + 면책 frame
- [ ] 사용자 "푸시업 10회 시작" → `StartCountingAction` 디스패치 (phase-6에서 실제 카운팅 시작과 연결)
- [ ] 사용자 "좋아" 발화 → `_pending_proposal` → 자동 `StartCountingAction`
- [ ] `latency.llm.generate_structured` 로그 기록
- [ ] ruff + pytest (비-GPU) 통과
- [ ] git commit `feat(phase-5): 능동 코치 instructor + JSON + Action Dispatcher`

## 리스크

- qwen3:8b의 한국어 JSON 일관성 — instructor max_retries로 보완하나 schema drift 빈도 측정 필요. 빈번 시 시스템 프롬프트 추가 튜닝
- discriminated union의 type field 누락 시 instructor가 어떤 retry 메시지 보내는지 확인 필요
- 부상 키워드 목록 (20+종) 확정 — `SafetyGuardCore`에 명시

## 소요 추정

3~4일 (프롬프트 튜닝 + JSON 안정성 검증 포함).

## 다음 phase

[Phase 6 — 카운팅 트리거](phase-6-counting.md)
