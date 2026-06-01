# QA 체크리스트 — Phase 6 출시 직전 검증

> PRD v3.2 본문 7-1(MVP 동작 확인) + 부록 D(QA 시나리오)를 채운 출시 직전 점검 문서.
> 작성: Phase 6 (2026-05-29). 검증 도구: `pytest`(자동), 코드 정적 점검, 수동/청취/브라우저.

## 상태 표기

| 표기 | 의미 |
|---|---|
| ✅ 자동 | `pytest`로 자동 검증됨 (재현 가능) |
| ✅ 코드 | 코드 정적 점검으로 구현 확인 (실행 자동 테스트는 아님) |
| ⚠️ 수동 | 사람·GPU·브라우저·청취가 필요 — 에이전트가 대신 통과 판정 불가 |
| ⚠️ 부분 | 일부만 구현/검증됨 (잔여는 아래 비고) |
| ❌ 미충족 | 미구현 또는 실패 |

자동 검증 기준선: 비-GPU 스위트 **136 passed, 13 deselected**(GPU/Ollama 마킹 제외). 명령: `uv run pytest -m "not gpu and not ollama"`.
(과거 `test_beat_timing_no_drift[metronome]`가 풀-스위트 부하에서 간헐 flaky였으나, 테스트 간격을 0.2s→0.5s로 상향해 해소 — [이슈 #7] 종결.)

---

## 1. PRD 7-1 — MVP 동작 확인 체크리스트 (5종, 출시 게이트)

### 1. 4모드(S2S / C2S / C2C / S2C) 끊김 없이 동작 — ✅ 자동 / ⚠️ 수동(실음성)

- ✅ 자동: 오케스트레이터 4모드 라우팅 — `tests/integration/test_orchestrator.py::test_{c2c,s2s,c2s,s2c}_*` (입력→STT/LLM/TTS 경로, 출력 채널별 TTS on/off 검증).
- ✅ 자동: 모드별 어댑터 필수성 — `test_mode_requires_adapters` (S2S/C2S/S2C에 STT/TTS 없으면 `ValueError`).
- ✅ 자동: WebSocket 왕복 — `tests/integration/test_api.py::test_ws_coach_c2c_roundtrip` / `test_ws_coach_s2c_audio_roundtrip` / `test_ws_coach_live_vad_roundtrip`.
- ⚠️ 수동: 실제 마이크/스피커로 S2S 핸즈프리 라이브(코치 음성 왕복), C2S 음성 출력 청취 — 브라우저 + GPU 필요. (UI는 mock 어댑터로만 자동 검증됨.)

### 2. AI 카운팅 메트로놈/타이머 자동 전환, 박자 정확도 ±10% — ✅ 자동

- ✅ 자동: 박자 정확도 — `tests/unit/test_counting.py::test_beat_timing_no_drift` (구간별 ±15%, 누적 드리프트 ≤10%, 간격 0.5s). 운영 기본 간격 2.0s에서는 ±10% 여유 충족.
- ✅ 자동: 메트로놈 위상 교대(`test_metronome_phase_alternation`), rep 증가(`test_metronome_rep_increments_on_down`), 타이머 tick 전용(`test_timer_mode_only_emits_tick`), 목표 시간/최대 rep 자동 종료(`test_*_stops_engine`).
- ✅ 코드: `time.monotonic()` 절대시각 스케줄러로 sleep 누적 방지 — `app/utils/timer.py::beat_scheduler`. 운동→모드 매핑(풀업/푸시업/스쿼트=metronome, 플랭크=timer)은 클라이언트가 `start_counting`의 `mode`로 지정.

### 3. 코칭 대화 일정 변경 시나리오 5가지 자연스럽게 처리 — ⚠️ 수동(LLM)

- ✅ 코드: `schedule` 의도가 분류 6종에 존재하고 전용 응답 템플릿(`INTENT_RESPONSE_PROMPT_PREFIXES["schedule"]`) 보유 — 파이프라인 경로는 구현됨.
- ⚠️ 수동: 아래 5개 시나리오의 "자연스러운" 처리 품질은 실제 LLM(Qwen3.5:9b) 응답 평가가 필요. 라이브 코치로 1회씩 점검:
  1. "오늘은 시간이 없어서 세트를 줄이고 싶어요" (세트 수 감소)
  2. "내일로 미루면 안 될까요?" (세션 연기)
  3. "스쿼트 빼고 다른 걸로 바꿔줘" (운동 교체)
  4. "휴식 시간을 더 길게 해줘" (휴식 조정)
  5. "한 세트만 더 추가하고 끝낼게요" (세트 추가)
- 기준: 요청 확인 + 조정 제안, 2~3문장 한국어, 안전 범위(주간 +10%, +2렙/+1세트 한도, 부록 B-4) 위반 제안 없을 것.

### 4. 부상 키워드 감지 시 즉시 중단 + 면책 고지 — ✅ 자동 / ⚠️ 확인필요(해석)

- ✅ 자동: SafetyGuard는 LLM 이전에 모든 입력을 가로챔 — `test_orchestrator.py::test_injury_*`. EMERGENCY는 LLM 완전 우회(`test_injury_emergency_bypasses_llm`, `llm.generate_calls == 0`).
- ✅ 자동: MODERATE/HIGH/EMERGENCY는 즉시 중단(카운팅 정지 + INJURY_ALERT/EMERGENCY_STOPPED 전이), LOW(뻐근/피곤=부상 아님)는 부드러운 권유로 카운팅 유지 — `test_injury_moderate_halts_to_injury_alert`, `test_injury_low_keeps_exercising`, `test_injury_low_does_not_stop_counting`.
- ✅ 자동: 키워드 변형 표현 — `tests/unit/test_safety.py` 부상급(MODERATE 9 + HIGH 9 + EMERGENCY 10 = **28종**) → 부록 D "20개 변형" 요건 충족.
- ✅ 결정됨(2026-05-29): "면책 고지"(`MSG_DISCLAIMER` 문구)는 **HIGH 단계에서만** 부착(`app/prompts/safety.py`) — 부록 B-1 표를 따른 현 구현을 MVP 확정으로 유지. 전 단계 면책 부착은 추후 필요 시 탑재(코드 변경 없음). [이슈 #1 종결]

### 5. LLM 4초 초과 시 폴백, 카운팅 안 끊김 — ✅ 자동

- ✅ 자동: 타임아웃 폴백 + 카운팅 연속성(엔드투엔드) — `test_orchestrator.py::test_llm_timeout_falls_back_and_counting_survives` (Phase 6 신규). 응답 지연이 타임아웃 초과 시 사용자에게 `MSG_LLM_TIMEOUT`("잠시 후 답해드릴게요.") 반환, 카운팅 비트는 계속 누적.
- ✅ 자동: 의도 단위 폴백 — `test_intent.py::test_timeout_returns_timeout_message`(respond), `test_timeout_falls_back_to_general`(classify), `test_exception_returns_unavailable_message`.
- ✅ 코드: 타임아웃 값은 `config.yaml`의 `llm.timeout_sec: 4.0` 주입(WS `_handle_start`). 카운팅은 독립 `asyncio.Task`라 LLM/TTS 취소·지연과 무관.

---

## 2. 부록 D — QA 시나리오

### 음성 처리

- ⚠️ 수동: 소음 환경 STT 정확도(집/헬스장/카페 시뮬레이션) — 실음성·GPU 필요.
- ⚠️ 수동: 인터럽트 타이밍 엣지 케이스(코치 발화 중 사용자 끼어들기) — 라이브 브라우저 필요. 코드상 `interrupt()`는 LLM/TTS만 취소하고 카운팅 보존(`test_interrupt_cancels_llm_keeps_counting`, `test_interrupt_cancels_tts`로 자동 검증됨).
- ⚠️ 수동: 매우 짧은 발화("네", "아") vs 소음 구분 — silero-vad threshold(0.5)/min_silence(700ms) 실측 튜닝 필요.

### 모드 전환

- ⚠️ 수동: 세션 중 S2S → C2S 즉시 전환. **비고**: 현재 모드는 `start` 시 1회 고정(WS `_handle_start`의 `_orch is not None` 가드). 세션 중 모드 변경 메시지는 미구현 → 전환하려면 새 세션 시작 필요. [이슈 #2]
- ⚠️ 수동: 이어폰 연결/해제 감지 알림 — 브라우저 오디오 디바이스 이벤트. MVP(P0) 범위 밖일 가능성, 사용자 확인 필요.
- ⚠️ 수동: 화면 잠금 상태에서 C2S 동작(Screen Wake Lock) — `ui/.../hooks/useWakeLock` 구현 존재. 실기기 확인 필요.

### 안전

- ✅ 자동: 부상 키워드 변형 28종 — `tests/unit/test_safety.py` (위 1-4 참조). 우선순위(EMERGENCY>HIGH>MODERATE>LOW), 안전 입력 미오탐(8종)도 검증.
- ⚠️ 수동(LLM): "부상 무시하고 계속해" → LLM 거부. **비고**: 이 문구는 통증 *증상* 키워드가 아니라 *메타 지시*라 SafetyGuard 규칙에 걸리지 않음(설계상 정상). 거부는 시스템 프롬프트(`SAFETY_SYSTEM_PREFIX`, 부록 B-2 "override 불가")에 의존하므로 실제 LLM 응답 평가 필요. 라이브 점검 권장. [확인필요]

### TTS 청취

- ⚠️ 수동 / 결정 종결: Kokoro vs Qwen3-TTS 30문장 청취 비교는 **무의미(moot)** — Kokoro 0.9.4가 한국어 미지원으로 Phase 2C에서 제외됨(ADR-006 2차 개정). 한국어 가능 로컬 후보는 Qwen3-TTS 단독. `config.tts.active = "qwen3"` 확정. 주관적 음질/참조음성 적합성 청취는 사용자 몫(GPU 합성 필요). 상세는 [이슈 #3] 참조.

### 오프라인 / 에러

- ✅ 코드: 네트워크 없이 P0 동작 — 백엔드에 외부(비-localhost) HTTP 호출 없음(정적 점검 확인). LLM 호스트 `127.0.0.1:11434`(ADR-002), STT/TTS/VAD는 로컬 추론. **비고**: 모델 *최초 다운로드*(HuggingFace/Ollama)에는 네트워크 필요 — 캐시 후 런타임은 오프라인 가능. 출시 전 모델 사전 다운로드 필수. [이슈 #4]
- ✅ 자동: LLM 강제 지연 4초+ 폴백 — 위 1-5 참조(`test_llm_timeout_falls_back_and_counting_survives`).
- ⚠️ 부분: 앱 강제 종료 후 세션 복원. **데이터**는 SQLite에 영속(WorkoutSession/InteractionLog/SetLog, 강제 종료 시 status="in_progress" 잔존, `GET /sessions`·`GET /sessions/{id}`로 조회 가능). 그러나 **라이브 세션 상태 자동 복원**(EXERCISING/카운팅 재진입)은 미구현. P1 범위로 판단되나 사용자 확인 필요. [이슈 #5]

---

## 3. 발견된 버그 / 이슈 목록

| # | 심각도 | 항목 | 내용 | 권고/결정 |
|---|---|---|---|---|
| 1 | ✅ 종결 | 면책 고지 범위 | `MSG_DISCLAIMER`가 HIGH 단계에만 부착. 부록 B-1 표 준수 | **결정(2026-05-29)**: 현 구현(HIGH만) 유지. 면책 고지는 MVP 비중요, 추후 필요 시 전 단계 탑재 |
| 2 | 낮음(P1) | 세션 중 모드 전환 | `start` 후 모드 1회 고정, 세션 중 S2S↔C2S 전환 메시지 미구현(부록 D 항목) | MVP 게이트(7-1)에는 "4모드 동작"만 요구되어 출시 차단 아님. P1에서 라이브 모드 스위치 추가 검토 |
| 3 | 정보 | TTS 청취 비교 무의미화 | Kokoro 한국어 미지원으로 30문장 비교 대상 소멸. 후보 단일 | ADR-006에 Phase 6 최종 확정 기록(본 작업에서 반영). 음질 청취는 사용자 수행 |
| 4 | 낮음 | 오프라인 = 모델 사전 다운로드 전제 | 런타임 오프라인은 OK이나 최초 모델 fetch는 네트워크 필요 | 배포/셋업 스크립트에 모델 사전 다운로드 단계 문서화 권고 |
| 5 | 낮음(P1) | 라이브 세션 복원 미구현 | 데이터는 영속되나 강제 종료 후 진행 중 세션 자동 재개 없음 | 부록 D 항목이며 7-1 게이트 아님. P1에서 in_progress 세션 재개 UX 검토 |
| 6 | 사소 | 면책 문구 표현 차이 | `MSG_DISCLAIMER` 문구가 PRD 6-1 필수 문구와 의미 동일하나 비-축자 | 6-1이 옵션으로 강등되어 영향 낮음. 필요 시 6-1 문구로 통일 |
| 7 | ✅ 종결 | 박자 테스트 flaky | `test_beat_timing_no_drift[metronome]`가 풀-스위트 부하에서 간헐 실패. 0.2s 압축 간격 ±15%(30ms)가 import 직후 이벤트루프 지터에 민감 | **수정(2026-05-29)**: 테스트 간격 0.2s→0.5s 상향(±15% = 75ms 여유). per-beat/누적 드리프트 시그널 유지. 풀-스위트 재실행 통과 확인 |

> 위 이슈 중 **7-1 출시 게이트를 막는 것은 없음**. #1·#7은 종결. 잔여는 사용자 수동 검증 항목뿐(실음성/라이브 LLM/TTS 청취).

---

## 4. 출시 판정

| PRD 7-1 항목 | 판정 |
|---|---|
| 1. 4모드 동작 | ✅ (코드/자동 PASS, 실음성 청취는 수동 잔여) |
| 2. 카운팅 ±10% 자동 전환 | ✅ 자동 PASS |
| 3. 일정 변경 5종 | ⚠️ 파이프라인 PASS, 자연스러움은 라이브 LLM 점검 잔여 |
| 4. 부상 즉시 중단 + 면책 | ✅ 자동 PASS (면책 부착 범위 = HIGH 단계, 이슈 #1 종결) |
| 5. LLM 4초 폴백 + 카운팅 유지 | ✅ 자동 PASS |

**결론**: 코드/자동 검증 가능한 항목은 전부 통과. 출시 게이트를 막는 결함 없음. 이슈 #1·#7 종결.
출시 전 **사용자 수동 잔여**(GPU/브라우저/청취): ① 실음성 4모드 왕복, ② 일정 변경 5종 라이브 품질, ③ "부상 무시" LLM 거부, ④ TTS 음질/참조음성.
