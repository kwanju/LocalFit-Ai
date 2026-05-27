# Task: Phase 2C — TTS 어댑터 (Kokoro + Qwen3-TTS 교체형)

## 배경 자료
- `AGENTS.md`
- `docs/architecture/adr/006-tts.md`
- `docs/architecture/adr/010-adapter-interfaces.md`

## 작업 범위
1. `app/adapters/tts/protocol.py` — TTSAdapter Protocol + TTSRequest dataclass
2. `app/adapters/tts/kokoro.py` — KokoroAdapter
3. `app/adapters/tts/qwen3.py` — Qwen3TTSAdapter
4. `app/adapters/tts/__init__.py` — dict 매핑으로 config.tts.active 기반 선택 (coding-style.md 8번)
5. `tests/integration/test_tts.py` — @pytest.mark.gpu, 두 어댑터 한국어 합성
6. CLI smoke test: 텍스트 → WAV 파일 (양쪽 어댑터)

## 제약
- 교체형 (동시 사용 아님) — 활성 1개만 로드
- dict 매핑 사용, 팩토리 클래스 과용 금지
- synthesize() + stream() + health() 구현
- WAV bytes 반환

## P0 첫 주 청취 비교
두 어댑터로 한국어 30문장 합성 → 청취 → config.tts.active 결정.
청취용 스크립트 `scripts/tts_compare.py`도 함께 작성 (30문장 양쪽 합성하여 wav 저장).

## 비범위
- 오디오 재생 (UI Phase 5)
- 페르소나별 음색 (P2)

## 완료 기준
- 양쪽 어댑터 한국어 WAV 생성
- 청취 비교 스크립트 동작
- pytest 통과 (GPU 없으면 skip)

## 자가 보고
AGENTS.md 9번. checklist A·D·E·F·H 확인.
