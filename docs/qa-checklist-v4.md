# QA 체크리스트 v4 — LocalFit AI v3-rewrite (Phase 8)

> **사용 방법**: 자동 검증 항목은 pytest로 실행 (`uv run pytest -m "not gpu and not ollama and not integration" -q`). 수동 검증 항목은 사용자가 직접 수행.

---

## A. 자동 검증 (PRD §7-1)

### A-1. 4모드 라운드트립

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 1 | C2C: TextFrame 입력 → MockLLM echo TextFrame 출력 | `test_c2c_roundtrip_text_in_text_out` | 자동 |
| 2 | C2S: TextFrame → MockTTS TTSAudioRawFrame | `test_c2s_text_in_audio_out` | 자동 |
| 3 | S2C: VAD audio → MockSTT TranscriptionFrame | `test_s2c_roundtrip_audio_in_text_out` | 자동 |
| 4 | S2S: 파이프라인 topology (STT+TTS 노드 포함) | `test_4mode_pipeline_topology[s2s]` | 자동 |

### A-2. 박자 정확도

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 5 | 메트로놈 ±10% 정확도 (500ms interval) | `test_counting_beat_timing_accuracy` | 자동 |

### A-3. 카운팅 자동 시작

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 6 | '푸시업 10개 시작' → `StartCountingAction` 디스패치 | `test_user_utterance_triggers_start_counting` | 자동 |

### A-4. 능동 코치 인사 + 추천

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 7 | Proactive opener → `ProposeSetAction` 슬롯 적재 | `test_proactive_opener_propose_set_lands_in_slot` | 자동 |

### A-5. 일정 변경 5종 시나리오

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 8~12 | 풀업/푸시업/스쿼트/플랭크/런지 ProposeSet mock | `test_propose_set_5_scenarios[...]` | 자동 |

### A-6. 부상 키워드 즉시 중단

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 13 | '허리가 아파요' → SafetyResponseFrame, LLM 호출 없음 | `test_injury_keyword_bypasses_llm_and_emits_safety_frame` | 자동 |

### A-7. LLM 지연 fallback + 카운팅 연속

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 14 | LLM 4초 지연 중 CountingEngine 독립 진행 | `test_llm_timeout_counting_continues` | 자동 |

### A-8. TTS 첫 청크 < 500ms

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 15 | TTS 첫 청크 < 500ms (RTX 5090 필요) | `test_tts_first_chunk_under_500ms` (`@gpu`) | **수동** (GPU 환경) |

> **자동화 어려운 이유**: GPU 없이는 TTS 실행 불가. RTX 5090 환경에서 `pytest -m gpu` 별도 실행.

### A-9. 인터럽트

| # | 테스트 | 방법 | 상태 |
|---|---|---|---|
| 16 | InterruptionFrame 파이프라인 통과 | `test_interrupt_frame_dispatched_through_pipeline` | 자동 |

---

## B. 수동 검증 (사용자 직접 수행)

> `scripts/dev.bat`으로 백엔드 + 프론트엔드 기동 후 브라우저에서 수행.

### B-1. 실음성 4모드 왕복 (한국어)

| # | 항목 | 기대 결과 |
|---|---|---|
| M-1 | **C2C**: 채팅 입력 → 코치 텍스트 응답 확인 | 한국어 응답, 지연 < 2s |
| M-2 | **C2S**: 채팅 입력 → 코치 음성 재생 확인 | TTS 음질 자연스러움 |
| M-3 | **S2S**: 마이크 라이브 → 코치 음성 응답 확인 | STT 인식 정확도, E2E < 3s |
| M-4 | **S2C**: 마이크 라이브 → 코치 텍스트 응답만 | 음성 출력 없음, 텍스트만 |

### B-2. TTS 음질·자연스러움

| # | 항목 | 기대 결과 |
|---|---|---|
| M-5 | faster-qwen3-tts 음성 재생 | 자연스러운 한국어 TTS, 음색 일관(xvec_only), 잡음 없음 |
| M-6 | sentence-streaming 분절 없음 | 문장 단위로 연속 재생 (끊김 최소화) |

### B-3. 능동 코치 제안 적절성

| # | 항목 | 기대 결과 |
|---|---|---|
| M-7 | 세션 시작 시 proactive opener 동작 | 코치가 먼저 운동 제안 |
| M-8 | 제안 수락 ("좋아") → 카운팅 자동 시작 | CountingDisplay에 숫자 표시 |
| M-9 | 제안 거부 ("아니") → graceful 처리 | LLM이 다른 제안 또는 수용 |

### B-4. 일정 변경 5종 라이브 LLM 품질

| # | 항목 | 기대 결과 |
|---|---|---|
| M-10 | "오늘 풀업 좀 줄여줘" → reps 조정 | propose_set으로 대안 제안 |
| M-11 | "다른 운동으로 바꿔줘" → 운동 변경 | 새 운동 추천 |
| M-12 | "더 힘든 걸로" → 난이도 상향 | reps 또는 운동 강화 |
| M-13 | "쉬게 해줘" → 휴식 추가 | 적절한 rest_sec 조정 |
| M-14 | "오늘 컨디션 안 좋아" → 감소 처리 | 친절한 조정 제안 |

### B-5. 부상 거부 확인

| # | 항목 | 기대 결과 |
|---|---|---|
| M-15 | "부상 무시하고 계속해" 입력 | LLM이 거부 + 면책 고지 |
| M-16 | "허리 아픈데 스쿼트 할게요" 입력 | SafetyGuard 동작, 즉시 중단 메시지 |

### B-6. 세션 종료 후 DB 기록

| # | 항목 | 기대 결과 |
|---|---|---|
| M-17 | 카운팅 완료 후 세션 종료 | SetLog DB에 운동 기록 생성 |
| M-18 | 설정 화면에서 서버 상태 정상 | 어댑터 상태 "정상" |

### B-7. 카운팅 UX

| # | 항목 | 기대 결과 |
|---|---|---|
| M-19 | 화면 큰 숫자 표시 | CountingDisplay에 rep 숫자 표시 |
| M-20 | 탭 인터럽트 | 코치 음성 중단, 인터럽트 전송 |
| M-21 | 카운팅 중 화면 잠금 방지 | Wake Lock 동작 확인 |

### B-8. PWA + Service Worker

| # | 항목 | 기대 결과 |
|---|---|---|
| M-22 | `/api/*`, `/ws/*` 캐시 안 됨 | DevTools Network에서 "from SW" 없음 |
| M-23 | 자산(JS/CSS) 캐시 정상 | 재접속 시 캐시 사용 |

### B-9. 운동 캘린더 (Phase 8)

| # | 항목 | 기대 결과 |
|---|---|---|
| M-24 | 빈 DB 상태에서 `/calendar` 진입 | "아직 운동 기록이 없어요" 빈 상태 UI + 세션 시작 버튼 |
| M-25 | 최근 7일 이내 데이터만 있을 때 | 1주일 strip 뷰 표시 (연간 히트맵 대신) |
| M-26 | 1년치 세션 데이터 (DB 수동 삽입) | 연간 히트맵 표시, 색 강도 자연스러움 |
| M-27 | 날짜 셀 클릭 → 상세 모달 | 세션 시작/종료 시각, 운동 목록, 컨디션 정상 표시 |
| M-28 | 능동 코치 인사가 캘린더 패턴 언급 (5회 중 3회 이상) | "지난주처럼", "5일 만에" 등 자연 언급 |

---

## C. 자동화 어려운 항목 (수동 필수)

| 항목 | 이유 |
|---|---|
| TTS 첫 청크 < 500ms | GPU 환경 의존, 실 TTS 모델 필요 |
| STT 한국어 인식 정확도 | 실 마이크 입력, faster-whisper 모델 필요 |
| TTS 음질·자연스러움 | 주관적 평가, 실 모델 필요 |
| 능동 코치 제안 적절성 | 실 LLM (qwen3:8b) 필요 |
| E2E 지연 측정 (S2S 2~3s) | 실 하드웨어 필요 |
| LLM 한국어 일관성 | 실 LLM, 주관적 평가 |

---

## D. 실행 명령어

```bash
# 자동 검증 (비-GPU)
uv run pytest -m "not gpu and not ollama and not integration" -v

# GPU 검증 (RTX 5090)
uv run pytest -m gpu -v

# 프론트엔드 빌드/타입체크
pnpm -F ui typecheck
pnpm -F ui build

# 개발 서버 실행
scripts/dev.bat
```

---

*작성일: 2026-06-02 | Phase 7 완료*
