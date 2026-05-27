# ADR-011: 모델 동시 실행 전략

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-003 (Ollama), ADR-014 (게임 워크플로우)

## 컨텍스트

RTX 5090(32GB) + 64GB RAM 환경에서 LLM(Qwen 9B, ~6.6GB), STT(faster-whisper medium, ~2GB), TTS(Kokoro, ~0.5GB)가 동시에 메모리에 상주할 수 있다. PRD 4-1의 지연 목표(S2S 2~3초, C2S 1~2초)를 달성하려면 모델 로딩 지연(첫 추론 5~10초)을 피해야 한다.

## 결정

| 컴포넌트 | 전략 |
|---|---|
| Ollama 데몬 | `OLLAMA_KEEP_ALIVE=1h` keep-alive. API 호출 시 동적 override 가능 |
| STT (faster-whisper) | Python 백엔드 시작 시 즉시 로드, 백엔드 종료 전까지 GPU 상주 |
| TTS (Kokoro) | 동일 |
| 총 VRAM 점유 | ~8GB (5090의 25%) |

게임 시나리오는 ADR-014의 수동 스크립트로 대응.

## 결과

### 긍정
- 첫 응답 지연 없음 — PRD 지연 목표 여유 달성
- Python 백엔드와 Ollama 데몬이 독립 프로세스 → 한쪽 크래시 격리

### 부정
- 평소 GPU VRAM ~8GB 점유 — 게임 시 ADR-014 수동 종료 필요
- Python 백엔드 메모리 누수 시 STT/TTS 모델도 함께 누수 — 정기 재시작 가능성

## 대안

| 후보 | 탈락 사유 |
|---|---|
| Lazy 로딩 (첫 요청 시 로드) | 첫 응답 5~10초 지연 → PRD 위반 |
| 모든 모델을 별도 프로세스 | 격리 ↑, 복잡도 ↑. 1인 프로젝트엔 in-process 단순 |
| `OLLAMA_KEEP_ALIVE=24h` | 게임 안 할 때 메모리 항상 점유. 1h가 균형점 |
| `OLLAMA_KEEP_ALIVE=5m` | 평소 사용에서도 잦은 재로딩 발생 |
