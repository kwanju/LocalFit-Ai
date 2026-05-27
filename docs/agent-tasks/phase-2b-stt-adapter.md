# Task: Phase 2B — STT 어댑터 (faster-whisper + VAD)

## 배경 자료
- `AGENTS.md`
- `docs/architecture/adr/005-stt.md`
- `docs/architecture/adr/012-vad.md`
- `docs/architecture/adr/010-adapter-interfaces.md`

## 작업 범위
1. `app/adapters/stt/protocol.py` — STTAdapter Protocol + STTResult dataclass
2. `app/adapters/stt/whisper.py` — FasterWhisperAdapter (large-v3-turbo, config의 stt 섹션 사용)
3. `app/adapters/stt/vad.py` — silero-vad 래퍼 (발화 구간 감지)
4. `tests/integration/test_stt_whisper.py` — @pytest.mark.gpu, 한국어 음성 샘플 전사
5. CLI smoke test: 음성 파일 입력 → 텍스트 출력

## 제약
- 모델 이름 config.yaml 참조 (stt.model)
- 동기 라이브러리 → asyncio.to_thread로 감싸기 (coding-style.md 2번)
- VAD는 STT 전처리 (발화 시작/종료 감지)
- 운동 호흡 소음 환경 고려 (튜닝 파라미터 노출)

## 비범위
- 마이크 입력 캡처 (UI Phase 5)
- Orchestrator 연동 (Phase 4A)

## 완료 기준
- 한국어 음성 샘플 전사 정확도 확인
- pytest 통과 (GPU 없으면 skip)

## 자가 보고
AGENTS.md 9번. checklist A·D·E·F 확인.
