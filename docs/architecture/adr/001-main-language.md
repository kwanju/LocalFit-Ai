# ADR-001: 메인 언어로 Python 3.11+ 채택

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-003 (Ollama), ADR-005 (faster-whisper), ADR-006 (Qwen3-TTS), ADR-011 (Pipecat)

## 컨텍스트

LocalFit AI 백엔드는 LLM·STT·TTS·VAD 같은 ML 모델을 로컬에서 다룬다. 이 생태계는 Python 중심이다. v1 출시본도 Python 3.11+로 구성됐고 안정성·생산성 모두 검증됐다. v3-rewrite도 같은 선택을 유지한다.

UI(React + Vite)는 TypeScript이지만 별도 컨텍스트로 분리된다.

## 결정

- 백엔드 메인 언어 = **Python 3.11+** (3.11 또는 3.12 사용 가능, 3.13은 일부 의존성 호환성 검증 필요)
- 타입 힌트 필수, mypy/pyright는 사용하지 않고 ruff + pyright lite 정도만 적용
- async/await 적극 사용 (FastAPI, Pipecat 모두 async 기반)

## 결과

### 긍정
- ML/AI 생태계와 직접 결합 (Pipecat·faster-whisper·Qwen3-TTS 모두 Python)
- 타입 힌트로 어댑터 계약 명세 가능
- async 기반이라 Pipecat frame 처리에 자연 부합

### 부정
- GIL — 단일 사용자 환경이라 영향 미미하나, CPU bound 작업은 ProcessPool 고려
- 일부 ML 라이브러리(torch + cu128)는 설치가 무거움 — uv로 관리(ADR-017)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| TypeScript (Node.js) | Pipecat은 Python 우선. faster-whisper·Qwen3-TTS 공식 Python. 어댑터 작성 부담 큼 |
| Rust | ML 생태계 성숙도 부족. 1인 프로젝트 생산성 낮음 |
| Go | 동일 사유 (ML 생태계 부족) |

## References
- [Python 3.12 Release Notes](https://docs.python.org/3.12/whatsnew/3.12.html)
- [Pipecat — Python 기반 프레임워크](https://github.com/pipecat-ai/pipecat)
