# Phase v4-7 — 모델 lifecycle on-demand (로드/언로드)

## 목적

무거운 모델(STT+TTS+LLM)을 **상주시키지 않고**, 운동/대화 세션 시작 시 GPU 로드 → 종료 시 언로드한다(ADR-030, supersedes ADR-015). 평소 VRAM 을 해방해 **게임 등 타 앱과 공존**(v4 핵심 요구, 16GB 베이스라인). 트레이드오프인 콜드스타트(탐사 실측 **~30s**)는 **병렬 로드 + 앱-열림 prewarm + "코치 준비 중" UX** 로 흡수한다.

> v3 의 상주 런타임을 뒤집는 phase. 현재 `app/main.py` lifespan 이 **시작 시 전 모델 로드 + LLM warmup**(ADR-015 방식)이라, 이걸 세션-스코프 로드/언로드로 재구성하는 게 핵심.

## 사전 조건

- Phase v4-6(Tauri 셸 — 앱-열림 prewarm 트리거의 발신처) 완료
- 기존 자산: `app/main.py:50`(lifespan, 현재 startup 로드+warmup), `app/config.py:13`(`keep_alive`), `app/adapters/{llm,stt,tts}/`, `app/api/ws_voice.py`(세션 시작/종료 훅), `app/api/health.py`(adapters 상태), **`scripts/spike_vram_lifecycle.py`**(탐사 로드/언로드·empty_cache 레퍼런스)

## 관련 ADR

- **ADR-030** — on-demand 로드/언로드, `keep_alive=0` + `empty_cache()`, 콜드스타트 완화 (a)(b)(c)
- ADR-029 — LLM `qwen3.5:9b`(세션 중 ~5.6GB) / ADR-005·006 — STT/TTS
- ADR-015 — (Superseded) 폐기 대상 상주 정책

## 작업 항목

### 7-1. lifespan 에서 모델 상주 제거

- `app/main.py` lifespan(50-89)의 **startup 어댑터 로드 + `llm.warmup()` 제거**. 시작 시 무거운 모델 미상주(평소 VRAM ≈ baseline).
- `/health`(adapters:true/false) 의미 재정의 — "상주" 아니라 "로드 가능/현재 세션 로드됨".

### 7-2. 세션-스코프 모델 매니저

- 세션 시작(`ws_voice` 연결/세션 생성) → STT+TTS+LLM 로드. 세션 종료 → 언로드.
  - **LLM**: Ollama `config.llm.keep_alive=0`(또는 짧게) — 요청 후 자동 언로드.
  - **STT/TTS**: Python 모델 객체 해제 + `torch.cuda.empty_cache()`로 VRAM 반환(spike 스크립트 패턴).
- 단일 사용자(ADR-002)라 동시 세션 1개 — 매니저는 단순(락 1개). 멀티세션 가정 코드 금지.

### 7-3. 콜드스타트 완화 (★ ADR-030 결정)

- **(a) 병렬 로드**: STT/TTS/LLM 동시 로드 → 순차 30s 가 "가장 긴 하나"(TTS CUDA graph ~15s)로 수렴. GPU 메모리 spike 주의(탐사 12.2GB < 16GB 여유 확인됨).
- **(b) 앱-열림 prewarm**: 사용자가 "시작" 누르기 전, **Tauri 앱 포커스/열림 시점**(phase 6 셸)에 로드 개시. `/prewarm` 엔드포인트 + Tauri app-open 이벤트 → invoke.
  - ⚠️ **스케줄러 prewarm 은 금지**(ADR-030 — 백그라운드 선제 로드는 게임 VRAM 충돌). 오직 **사용자 의도(앱 열림)** 시점만.
- **(c) "코치 준비 중" UX**: 세션 시작~첫 응답 사이 로딩 상태 표시(UI). 탐사에서 사용자가 "세션 시작 느림"으로 체감한 지점.

### 7-4. VRAM 반환·누수 검증

- 세션 종료 후 `nvidia-smi`/`torch.cuda.mem_get_info` 로 반환 확인(탐사: 언로드 +1s 에 baseline 복귀).
- **반복 세션 누수 가드**: 세션 N회 반복 후에도 baseline 복귀 유지(테스트/실측). 메모리 누수 = ADR-030 부정 항목.

### 7-5. 안 행복한 경로

- VRAM 부족(타 앱 점유)으로 로드 실패 → "게임/다른 앱을 닫아주세요" 안내.
- 앱-열림 prewarm 실패 시 (a) VRAM 안내로 폴백(세션 시작 시 재시도).

## Definition of Done

- [ ] lifespan startup 모델 로드 제거 — 앱 시작 후 평소 VRAM ≈ baseline(`nvidia-smi` 확인)
- [ ] 세션 시작 로드 → 종료 언로드 → **VRAM baseline 복귀** 실측(반복 세션 누수 0)
- [ ] 병렬 로드로 콜드스타트 < 순차 30s(실측치 기록), "코치 준비 중" UX 표시
- [ ] 앱-열림 prewarm 동작(스케줄러 prewarm 아님 — 사용자 의도 시점만)
- [ ] VRAM 부족 시 로드 실패 안내
- [ ] ruff + pyright, pytest 비-GPU 통과(모델 로드/언로드는 GPU 스모크로 별도)
- [ ] git commit `feat(v4-7): on-demand 모델 lifecycle + 콜드스타트 완화`

## 명시적 비목표

- 스케줄러 백그라운드 prewarm(ADR-030 금지)
- 모델 양자화/속도 자체 최적화(별도)
- 알림/스케줄러(phase 8)

## 소요 추정

2일 (로드/언로드 재구성 + 누수 검증).

## 다음 phase

Phase v4-8 — 능동 알림 + 백그라운드 스케줄러(ADR-027). 인덱스: [`README.md`](README.md).
