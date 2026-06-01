# ADR-015: 모델 동시 상주 — Ollama keep_alive 24h + GPU 메모리 예산

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-003 (Ollama), ADR-005 (STT), ADR-006 (TTS)

## 컨텍스트

LocalFit AI는 세 가지 모델을 GPU에 동시 상주시켜야 한다.

| 모델 | VRAM(추정) | 비고 |
|---|---|---|
| qwen3:8b (q4_K_M) | ~5GB | Ollama keep_alive 24h |
| faster-whisper large-v3-turbo (float16) | ~1.5GB | 첫 호출 시 GPU 로드 |
| Qwen3-TTS-1.7B (bfloat16) | ~3.5GB | 첫 호출 시 GPU 로드 |
| **합계** | **~10GB** | RTX 5090 32GB 여유 충분 |

기준 환경: RTX 5090 (32GB) + 64GB RAM (v1 검증). 최소 사양은 16GB VRAM (qwen3:4b로 다운그레이드 시).

## 결정

### 모델 상주 정책

- **Ollama LLM**: `keep_alive: "24h"` — 24시간 GPU 메모리 상주
- **faster-whisper STT**: FastAPI lifespan에서 사전 로드 + 상주
- **Qwen3-TTS**: FastAPI lifespan에서 사전 로드 + ref WAV latent 캐시

### Warm-up 순서 (FastAPI lifespan)

```python
async with lifespan(app):
    init_db()
    await llm_service.warmup()       # Ollama generate 1회 호출
    await stt_service.warmup()       # 1초 무음 transcribe 1회
    await tts_service.warmup()       # "안녕하세요" 1회 합성
    yield
```

순차 warmup (병렬은 GPU 메모리 spike 위험). 총 30~120초 소요. 완료 전 `/health`는 503.

### GPU 메모리 예산 모니터링

- `app/utils/gpu_stats.py` (신규) — `torch.cuda.mem_get_info()`로 사용/여유 측정
- `/health` 응답에 `gpu_free_mb` 포함
- 메모리 부족 시 STT 또는 TTS 동적 unload는 P1 (MVP는 항상 상주)

### 동시 추론 정책

- 음성 파이프라인 1개 (단일 사용자) — 동시 추론 충돌 없음
- 카운팅 박자 멘트 TTS와 LLM 응답 TTS는 같은 모델 사용 — Pipecat가 queue로 직렬화

## 결과

### 긍정
- 첫 사용자 요청 시 cold start 0 — UX 매끄러움
- 단일 사용자 환경에서 GPU 충돌 없음
- RTX 5090 32GB로 여유 22GB 확보 — 향후 모델 업그레이드 여지

### 부정
- 미사용 시간에도 GPU 메모리 ~10GB 점유 — 다른 작업 동시 사용 시 불편
- 모델 unload·전환은 P1 (필요 시 동적 키 옵션 추가)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| 모델 lazy load (요청 시 로드) | 첫 요청 30~60초 지연 → UX 불가 |
| LLM만 상주, STT/TTS는 lazy | STT/TTS도 1~2초 cold start, S2S 모드에 큰 영향 |
| Ollama `keep_alive: -1` (영구) | 동작상 24h와 차이 미미, 명시적 timeout이 안전 |

## References
- [Ollama keep_alive](https://github.com/ollama/ollama/blob/main/docs/api.md#parameters)
- [faster-whisper 모델 로딩](https://github.com/SYSTRAN/faster-whisper#model-conversion)
- v1 known_constraints — RTX 5090 cu128 검증 환경
