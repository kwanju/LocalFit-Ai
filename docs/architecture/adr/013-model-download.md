# ADR-013: 모델 다운로드 전략

- **상태**: Accepted (Revised 2026-05-21)
- **이력**: STT/TTS 모델 갱신(ADR-005, 006)에 따라 다운로드 목록 업데이트
- **관련 ADR**: ADR-004 (LLM), ADR-005 (STT), ADR-006 (TTS)

## 컨텍스트

첫 실행 시 다음 모델을 다운로드해야 한다.

| 모델 | 크기 | 출처 |
|---|---|---|
| Qwen 3.5 9B Q4 (Ollama) | ~6.6GB | Ollama registry |
| Gemma 4 E4B Q4 (Ollama) | ~3GB | Ollama registry |
| faster-whisper large-v3-turbo | ~1.6GB | HuggingFace |
| Kokoro-82M | ~300MB | HuggingFace |
| Qwen3-TTS 0.6B | ~1.2GB | HuggingFace |
| silero-vad | <1MB | torch.hub |
| **합계** | **~12GB** | |

HuggingFace 다운로드가 한국에서 가끔 느리다(15~60분).

## 결정

### 별도 셋업 스크립트로 분리
`scripts/setup_models.py`. 앱 시작 시 모델 존재 여부만 확인, 없으면 에러로 종료하며 셋업 스크립트 실행 안내.

```python
# scripts/setup_models.py 동작
# 1. ollama pull qwen3.5:9b   (= qwen3.5:latest)
# 2. ollama pull gemma4:e4b
# 3. faster-whisper large-v3-turbo 다운로드 (HF_HUB_CACHE)
# 4. Kokoro 다운로드
# 5. Qwen3-TTS 다운로드
# 6. silero-vad 다운로드
# 진행률 표시, 재시도, 부분 다운로드 재개
```

### Ollama 모델 이름 방어 코드
Qwen 3.5, Gemma 4 모두 2026년 출시 직후라 Ollama 태그가 변동될 수 있다. `ollama list`로 정확한 이름 확인 후 진행하는 방어 코드 필수.

### 저장 위치
- Windows: `%LOCALAPPDATA%\localfit\models\`
- HF 캐시: `HF_HOME` 환경변수로 같은 경로 지정

### HF 미러 지원
한국 네트워크 환경에서 `HF_ENDPOINT=https://hf-mirror.com` 환경변수 우회 경로 유지.

### 선택적 다운로드
TTS는 교체형(ADR-006)이므로 셋업 시 `--tts kokoro,qwen3` 또는 `--tts all` 플래그로 선택 다운로드 지원. 기본은 둘 다.

### P1 진입 시
PWA UI에서도 "모델 셋업" 화면 제공.

## 결과

### 긍정
- 앱 시작 로직과 다운로드 로직 분리 — 디버깅 단순
- 셋업 실패가 앱 크래시로 이어지지 않음
- 미러 환경변수로 한국 네트워크 우회 가능
- TTS 선택 다운로드로 불필요한 모델 회피 가능

### 부정
- 사용자가 셋업 스크립트 직접 실행 — README 명확화 필수
- 총 ~12GB (전체 다운로드 시)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| 앱 첫 실행 시 자동 다운로드 | 12GB가 앱 안에서 일어남, 백엔드 비대화 |
| 모델 앱 번들 | 배포 파일 과대 |
| Docker 이미지 | 1인 오버킬, GPU 패스스루 복잡 (ADR-016) |
