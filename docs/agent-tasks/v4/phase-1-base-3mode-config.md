# Phase v4-1 — v4 base 정리 + 3모드(S2C 제거) + 모델 config 검증

## 목적

v4 구현의 출발점을 정리한다. v3 의 4모드에서 **S2C 를 제거해 3모드(C2C/C2S/S2S)** 로 줄이고(ADR-021), 이미 교체된 `qwen3.5:9b`(ADR-029)를 **회귀 검증**하며, 이후 phase(메모리·컨디션·플랜)가 테이블을 깨끗이 추가할 수 있도록 **v3→v4 DB 스키마 확장 스캐폴드**를 깐다.

> 기능을 새로 만드는 phase 가 아니라 **base 정리 + 검증 게이트**다. native 런타임(Tauri·lifecycle)은 phase 6~7, 도메인 신규 기능은 phase 2~5.

## 사전 조건

- 브랜치 `v4-rewrite` 체크아웃, Phase v4-0 탐사 GO 반영 커밋(`1a3587a`, `e68a686`) 포함 상태
- `app/`·`ui/` v3 자산 그대로 존재(이 phase 는 삭제·축소 중심)

## 관련 ADR

- **ADR-021** — v4 진입: UX 4모드 → 3모드(S2C 제거), 단일 사용자 계승, 마이그레이션 전제
- **ADR-029** — LLM `qwen3.5:9b` (supersedes 004). config 한 줄, instructor `from_provider("ollama/qwen3.5:9b")`
- ADR-013 — 능동 코치 instructor + JSON 구조화 출력 (9b 회귀 검증 대상)
- ADR-030 — `keep_alive` 는 on-demand 에서 재정의(이 phase 에서 keep_alive 손대지 않음 — phase 7 소관)

## 작업 항목

### 1-1. S2C 제거 → 3모드 (백엔드)

현재 S2C 가 박힌 지점(grep 확인):
- `app/db/models.py:26` — `SessionMode` enum 의 `s2c = "s2c"` **제거**
- `app/api/ws_voice.py` — 모듈 docstring(`?mode=...S2C`, `Phase 4: ...S2S/S2C`) 정리 + `use_stt = session_mode in (SessionMode.s2s, SessionMode.s2c)` → `in (SessionMode.s2s,)`
- `app/pipecat_services/pipeline_builder.py` — 별도 `SessionMode` enum(`s2c = "S2C"`, line 48), 헤더 주석(`S2C : STT on + TTS off`, line 7·10), docstring(line 71), `use_stt = mode in (s2s, s2c)`(line 109) **전부 S2C 제거**

> ⚠️ `SessionMode` enum 이 `app/db/models.py` 와 `app/pipecat_services/pipeline_builder.py` **두 곳**에 중복 정의돼 있음. 이번에 통합할지(`db.models` 를 단일 소스로)·그대로 둘지 결정. **권장: 통합은 scope 밖, 두 곳 모두에서 s2c 값만 제거**하고 통합은 별도 정리 과제로 남김(YAGNI).

### 1-2. S2C 제거 → 3모드 (프론트엔드)

- `ui/src/api/types.ts:4` — `SessionMode = "s2s" | "c2s" | "c2c" | "s2c"` → `"s2s" | "c2s" | "c2c"`. line 16 주석(`streaming S2S/S2C`)도 정리
- `ui/src/api/ws.ts` — S2C 분기 제거
- `ui/src/components/ModeSwitch.tsx` — 토글에서 S2C 옵션 제거(3개만 노출). 기본 모드/순서 확인
- `ui/src/screens/SessionLive.tsx` — S2C 전용 분기(있으면) 제거
- `ui/src/screens/Settings.tsx` — S2C 관련 설정/문구 제거

### 1-3. S2C 데이터 마이그레이션

- 기존 v3 SQLite(`session.mode = "s2c"`) 행이 enum 축소 후 로드 실패할 수 있음. **단일 사용자·소량**이므로:
  - 마이그레이션 스텝(1-4 스캐폴드 활용)에서 `UPDATE session SET mode='s2s' WHERE mode='s2c'` 1회 실행(S2C 는 마이크 on 이었으므로 S2S 로 매핑).
  - 신규 DB 에는 영향 없음.

### 1-4. v3→v4 DB 스키마 확장 스캐폴드

현재 `app/db/engine.py::init_db` 는 `SQLModel.metadata.create_all` 뿐 — **신규 테이블은 자동 생성되나 기존 테이블 컬럼 추가는 반영 안 됨**. phase 2(메모리)·4(플랜)가 컬럼·테이블을 추가하므로 경량 마이그레이션 훅을 먼저 깐다.

- `app/db/migrations.py`(신규, 경량) — `schema_version` 메타 테이블 + 순차 마이그레이션 스텝 리스트.
  - 단일 사용자·SQLite 라 **Alembic 도입은 과잉(YAGNI)**. 단순 버전 정수 + 멱등 스텝 함수로 충분.
  - 스텝 형태: `def step_N(conn): ... # ALTER TABLE / UPDATE`. `PRAGMA table_info` 로 멱등 가드.
  - `init_db` 끝에서 `apply_migrations(engine)` 호출(create_all 이후 → 신규 테이블은 create_all, 기존 테이블 변경은 step 으로).
  - 첫 스텝 = 1-3 의 `s2c → s2s` UPDATE.
- ⚠️ **이미 존재**: `ConditionLog`(fatigue/pain/notes, models.py:113)·`InteractionLog` 테이블은 v3 에 이미 있음 → phase 3(컨디션)·메모리에서 **재활용**, 신규 생성 금지. 이 phase 에서는 테이블 추가하지 않고 **스캐폴드만**.

### 1-5. qwen3.5:9b 회귀 검증 (★ 리스크 게이트)

`config.yaml:llm.model` 은 **이미 `qwen3.5:9b`**(ADR-029 수락 시 교체됨). 이 phase 는 교체가 아니라 **검증**이다.

- Ollama 에 `qwen3.5:9b` pull 되어 있는지 확인(`ollama list`). 없으면 setup 스크립트/안내.
- **instructor 구조화 출력 스모크**(ADR-013): 능동 코치 경로로 샘플 발화 → Pydantic 액션 스키마(예: `propose_set`)가 깨지지 않고 파싱되는지. 8b→9b 로 JSON 출력/ConfirmRule 분기가 회귀하지 않는지 **사람 1회 확인**.
- 회귀 발견 시: 프롬프트/스키마 보정 또는 ADR-029 대안표대로 재교체 검토 → **사용자 보고**(임의 교체 금지).

### 1-6. v4 문서 헤더 최소 정리 (선택, 가벼움)

- `CLAUDE.md`·`README` 상단 "v3-rewrite" 표기가 작업 맥락과 어긋남. **전면 v4 리프레시는 별도 과제**(메모리 노트). 이 phase 에서는 혼동 큰 헤더 한 줄 수준만 손대거나, 손대지 않고 별도 과제로 남겨도 됨. scope 보호를 위해 **기본은 건드리지 않음**.

## Definition of Done

- [ ] `app/`·`ui/src` 에 `S2C`/`s2c` grep 0건 (1-3 마이그레이션 SQL 문자열·주석 제외)
- [ ] UI 모드 토글에 3개(C2C/C2S/S2S)만 노출 — 사람 눈 확인
- [ ] 3모드 각각 WS 라운드트립 동작(C2C 텍스트, S2S/C2S STT 경로) — 최소 사람 1회
- [ ] `init_db` → 신규 DB 정상 + **기존 v3 DB 에 `apply_migrations` 적용 후 s2c 행이 s2s 로** 변환 확인
- [ ] `qwen3.5:9b` 로 instructor 구조화 출력 스모크 PASS(액션 파싱·ConfirmRule 회귀 없음) — 사람 확인 기록
- [ ] ruff + pyright 통과, `cd ui && pnpm test` + `tsc` 통과
- [ ] pytest 비-GPU 스위트 통과(CountingEngine·Repository·SafetyGuard·신규 migration 테스트)
- [ ] git commit `refactor(v4-1): S2C 제거 3모드 + DB 마이그레이션 스캐폴드 + 9b 검증`

## 명시적 비목표

- 신규 도메인 테이블(메모리/플랜) 생성 — phase 2·4
- Tauri/모델 lifecycle/알림 — phase 6~8
- `SessionMode` enum 중복 정의 통합(YAGNI, 별도 정리 과제)
- 전면 문서 v4 리프레시(별도 과제)

## 소요 추정

반나절~1일.

## 다음 phase

Phase v4-2 — 영속 메모리(ADR-025). 인덱스: [`README.md`](README.md).
