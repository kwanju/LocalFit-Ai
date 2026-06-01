# ADR-018: 로깅·관측성 — loguru + 파일 + 지연 메트릭

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-011 (Pipecat), ADR-013 (능동 코치 지연), ADR-014 (카운팅)

## 컨텍스트

v1은 표준 `logging`을 직간접 사용 — 포맷 설정·rotate·구조화 부족. v3에서는 PRD §4-1 지연 목표 검증을 위한 메트릭 + 디버깅 편의성이 필요하다.

`loguru`는 단일 import + 풍부한 기본값(컬러·rotate·async safe)으로 1인 프로젝트에 적합.

## 결정

### 로깅 = loguru

```python
from loguru import logger

logger.add(
    "logs/localfit_{time:YYYY-MM-DD}.log",
    rotation="00:00",        # 매일 자정 새 파일
    retention="14 days",     # 14일 보존
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    enqueue=True,            # async safe
)
```

- **콘솔**: 컬러 + 간결 포맷 (loguru 기본)
- **파일**: `logs/localfit_YYYY-MM-DD.log` (rotate, 14일 보존)
- **레벨**: 기본 INFO, DEBUG는 환경변수 `LOCALFIT_DEBUG=1`로 토글

### 로그 컨벤션 (CLAUDE.md §7 계승)

- 시스템 로그 = **영어** (예: `LLM warmup completed in 32.1s`)
- 사용자 대면 메시지 = **한국어** (UI/TTS 출력만)
- 예외는 잡되 무시 금지 — `logger.error` + 컨텍스트 첨부

### 지연 메트릭

PRD §4-1 검증을 위해 각 파이프라인 단계 지연을 INFO로 기록:

```python
from time import perf_counter
from loguru import logger

class LatencyTracker:
    def __init__(self, stage: str):
        self.stage = stage

    def __enter__(self):
        self._t0 = perf_counter()
        return self

    def __exit__(self, *_):
        elapsed_ms = (perf_counter() - self._t0) * 1000
        logger.info(f"latency.{self.stage}={elapsed_ms:.1f}ms")
```

기록 단계:
- `stt.transcribe` — 발화 종료부터 transcript 완성까지
- `llm.generate_structured` — LLM 호출 (instructor retry 포함)
- `tts.first_chunk` — TTS 첫 청크까지
- `e2e.s2s` — 사용자 발화 종료부터 첫 음성 출력까지
- `e2e.c2c` — 사용자 텍스트 입력부터 첫 텍스트 응답까지

### `/health` 엔드포인트

```json
{
  "status": "ok",
  "llm": true,
  "stt": true,
  "tts": true,
  "gpu_free_mb": 22000,
  "models": {
    "llm": "qwen3:8b",
    "stt": "large-v3-turbo",
    "tts": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
  },
  "uptime_sec": 1234
}
```

### 에러 추적

- 예외 발생 시 `logger.opt(exception=True).error(...)`로 traceback 포함
- 사용자에게 노출되는 에러는 한국어 메시지 + 영어 로그 동시 기록

### 메트릭 집계는 P1

- Prometheus·Grafana 같은 외부 도구는 P1 (단일 사용자엔 over-engineering)
- MVP에서는 로그 파일에서 grep으로 충분 (`grep "latency.e2e" logs/*.log`)

## 결과

### 긍정
- loguru 단일 import로 설정 단순
- 파일 rotate·async safe 기본 제공
- 지연 메트릭이 PRD §4-1 검증에 직접 활용
- 콘솔·파일 동시 출력

### 부정
- 표준 `logging`과 혼용 시 핸들러 중복 위험 (Pipecat 내부 `logging` 사용 시 — `logger.add(sys.stderr, ...)` + intercept handler 필요)
- 메트릭 집계 없음 — 수동 분석

## 대안

| 후보 | 탈락 사유 |
|---|---|
| 표준 `logging` | 포맷·rotate·async safe 직접 설정 |
| structlog | 학습 비용, JSON 출력 강점 활용도 낮음 (집계 안 함) |
| Prometheus + Grafana | 단일 사용자엔 over-engineering, P1 검토 |
| OpenTelemetry | 동일 사유 |

## References
- [loguru](https://github.com/Delgan/loguru)
- [loguru — intercept stdlib logging](https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging)
