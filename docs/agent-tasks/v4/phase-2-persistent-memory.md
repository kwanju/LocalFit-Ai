# Phase v4-2 — 영속 메모리 (2층: 구조화 전량주입 + 자유텍스트)

## 목적

세션을 넘어 사용자의 **부상·제약·기준선**을 영구 기억하고, 매 세션 프롬프트에 **전량 주입**한다(ADR-025). v3 회고의 "왼쪽 어깨" 사례(안전 직결 제약을 못 기억해 놓침)를 직접 해결한다. 이후 컨디션(phase 3)·플랜(phase 4)·첫 체력검증(phase 5)이 참조하는 **공용 기준선 저장소**를 깐다.

> 도메인 기반 phase. 신규 기능을 코치 흐름에 붙이는 첫 단계이며, **기존 `CoachContextBuilder` 확장**이 핵심이지 새 빌더 작성이 아니다.

## 사전 조건

- Phase v4-1 완료(3모드 + DB 마이그레이션 스캐폴드 `app/db/migrations.py` 존재)
- 기존 자산 확인: `app/core/coach_context.py`(`CoachContextBuilder`), `app/db/repositories.py`, `app/db/models.py`

## 관련 ADR

- **ADR-025** — 2층 메모리(1층 구조화 전량주입 / 2층 자유텍스트), vector DB 미도입
- ADR-008 — SQLite + SQLModel + Repository 패턴
- ADR-013 — 능동 코치(메모리 추출·주입은 컨텍스트 빌더 + 액션 경유)
- ADR-002 — 단일 사용자(메모리에 `user_id` 분기 금지)

## 작업 항목

### 2-1. DB — 1층 구조화 필드 (안전·기준선)

- **부상/제약**: `injuries`·`constraints`. 현재 `UserProfile`(models.py:35)에 없음 → 추가 방식 결정:
  - 권장: 신규 `UserMemory`(또는 `user_constraint`) 테이블 — `kind`("injury"|"constraint"), `text`, `severity?`, `active`, `created_at`. 다건·활성/해소 관리에 유리.
  - 대안(단순): `UserProfile` 에 JSON 컬럼. 다건·이력 관리엔 테이블이 나음.
- **기준선**: `fitness_baseline` — 종목별 자가보고 최대치·시작 강도(ADR-028 입력). JSON 또는 종목별 행. **phase 5 가 쓰고 phase 2 가 스키마만 마련**.
- 구조화 선호(예: 선호 운동 시간대)는 기존 `UserProfile.available_times` 재활용 가능 — 신규 최소화.
- 마이그레이션: phase v4-1 `migrations.py` 스텝으로 컬럼/테이블 추가(멱등 가드).

### 2-2. DB — 2층 자유텍스트 메모

- `memory_facts` 테이블 신규 — `id`, `text`, `tags`(JSON/CSV), `created_at`.
- 검색 = **최근순 / 키워드**(벡터 X). 주입 시 토큰 예산 내 최근·관련 N건.

### 2-3. Repository

- `MemoryRepository`(신규, `repositories.py`):
  - 1층: `get_constraints()`(active 전량), `upsert_constraint(...)`, `set_baseline(...)`, `get_baseline()`.
  - 2층: `add_fact(text, tags)`, `recent_facts(limit)`, `search_facts(keyword, limit)`.
- 기존 `UserProfileRepository`(repositories.py:210) 와 책임 분리 — 프로필 정적값 vs 메모리 누적값.

### 2-4. CoachContextBuilder 확장 (★ 핵심)

`app/core/coach_context.py` 의 `build()` 에 메모리 주입 추가. **순수 도메인 유지**(repo 주입, instructor/Pipecat import 금지 — 현 구조 그대로).

- **부상/제약(1층) = 항상 전량 주입.** 절대 검색·요약·생략하지 않음.
- ⚠️ 현재 `_MAX_CONTEXT_CHARS = 700` cap(coach_context.py:17·151)이 잘릴 때 부상/제약이 손실되면 **안전 사고**. → **cap 정책 재설계**: 부상/제약은 예산 밖 우선 보장(먼저 배치 + cap 면제), 잘림은 2층 자유텍스트에만 적용.
- 2층 자유텍스트 = 토큰 예산 내 최근/관련 N건만.
- `condition_repo`·`calendar_signals_fn` 처럼 `memory_repo` 를 `CoachContextBuilder` 의존성으로 주입(생성자에서 wiring — `app/pipecat_services/coach_context_adapter.py` 갱신).

### 2-5. 메모리 쓰기 경로 (대화 중 추출)

- LLM 이 대화에서 추출한 정보를 저장하는 액션을 `app/core/coach_response.py` `CoachAction` 유니온에 추가:
  - `RememberFactAction`(2층 자유텍스트 누적) / `RecordConstraintAction`(1층 부상·제약 승격).
- **1층 승격(안전) 규칙**: `app/core/safety.py`(SafetyGuard 키워드, v1 자산) 재활용해 부상·통증 키워드는 1층 구조화로 승격.
- **확인 정책 결정**: 부상/제약 저장을 즉시 vs 사용자 확인(ConfirmRule) 후 — 안전 정보라 **즉시 저장 + 사용자에게 "기억했어요" 통지** 권장(놓침 0 우선). 결정 시 사용자 보고.
- `app/pipecat_services/processors/action_dispatcher.py` 에 신규 액션 디스패치 연결.

## Definition of Done

- [ ] 1층 테이블/필드 + 2층 `memory_facts` 마이그레이션 적용(신규 DB·기존 DB 모두)
- [ ] `MemoryRepository` 단위 테스트(1층 전량 조회, 2층 최근/키워드)
- [ ] `CoachContextBuilder.build()` 가 부상/제약을 **cap 무관 전량** 포함 — 긴 제약 다건으로도 잘리지 않음을 테스트로 증명
- [ ] 대화로 "왼쪽 어깨 아파요" → 1층 저장 → **다음 세션 컨텍스트에 자동 포함** E2E 사람 확인(회고 사례 재현·해소)
- [ ] ruff + pyright, pytest 비-GPU 통과. `app/core/` 에 외부 import 0건 유지(grep)
- [ ] git commit `feat(v4-2): 2층 영속 메모리 + 부상·제약 전량 주입`

## 명시적 비목표

- vector DB / 임베딩 (ADR-025 명시 배제)
- 컨디션 체크인(phase 3)·플랜(phase 4)·기준선 산정 로직(phase 5 가 baseline 채움)
- 메모리 UI 편집 화면(후순위)

## 소요 추정

1~1.5일.

## 다음 phase

Phase v4-3 — 컨디션 트래킹(ADR-023). 인덱스: [`README.md`](README.md).
