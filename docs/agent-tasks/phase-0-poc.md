# Task: Phase 0 — 환경 검증 PoC (에이전트 없이 직접)

ADR 전체가 무용지물이 되지 않으려면 이것부터. 약 1~3시간.

## 목표
5090 + CUDA + Ollama + Qwen 한국어 응답이 실제로 동작하는지 검증.
선택적으로 STT/TTS 후보까지 테스트하여 ADR-005/006 확정.

## 단계

### 1. 기본 환경
```powershell
# uv 설치
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
uv python install 3.11

# CUDA 확인
nvidia-smi   # 5090 + VRAM 확인
```

### 2. Ollama + LLM
```powershell
# Ollama 설치 (공식 Windows installer)
ollama --version
ollama pull qwen3.5:9b      # = qwen3.5:latest. 정확한 태그는 ollama list로 확인
ollama pull gemma4:e4b

# 한국어 응답 테스트
ollama run qwen3.5:9b "오늘 컨디션이 별로인데 운동 강도를 어떻게 조정할까?"
```

### 3. Python에서 호출
```powershell
uv venv
uv pip install ollama
uv run python -c "import ollama; print(ollama.chat(model='qwen3.5:9b', messages=[{'role':'user','content':'안녕'}])['message']['content'])"
```

### 4. (선택) STT 검증
```powershell
uv pip install faster-whisper
# large-v3-turbo 모델로 한국어 음성 샘플 전사 테스트
```

### 5. (선택) TTS 청취 비교
```powershell
# Kokoro, Qwen3-TTS 각각 설치하여 한국어 1~2문장 합성 후 들어보기
```

## 통과 기준
- nvidia-smi에 5090 정상 인식
- Qwen 3.5 한국어 응답 자연스러움
- Python에서 ollama 호출 성공

## 실패 시
- CUDA 버전이 5090 미지원 → 최신 드라이버 + CUDA 12.8+ 확인
- Ollama 태그 불일치 → ollama list로 정확한 이름 확인 후 ADR-004/013 갱신
- 한국어 품질 미흡 → ADR-004 재검토

## 통과 후
Phase 1A부터 에이전트로 진행. 에이전트에게 "환경은 이미 검증됨"이라고 명시.
