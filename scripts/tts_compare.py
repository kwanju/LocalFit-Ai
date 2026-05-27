"""Qwen3-TTS 한국어 합성 비교 스크립트.

한국어 30문장을 Qwen3-TTS로 합성하여 data/tts_compare/ 에 WAV로 저장합니다.
청취 후 config.yaml의 tts.qwen3 설정을 조정하세요.

사용법:
    python scripts/tts_compare.py
    python scripts/tts_compare.py --out data/my_output
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

KOREAN_SENTENCES = [
    "안녕하세요, 저는 AI 피트니스 코치입니다.",
    "오늘의 운동을 시작하겠습니다. 준비되셨나요?",
    "자, 스쿼트 10회를 함께 해보겠습니다.",
    "하나, 둘, 셋, 넷, 다섯.",
    "잠깐 쉬어가세요. 30초 휴식입니다.",
    "호흡을 고르세요. 깊게 들이마시고 내쉬세요.",
    "다음은 푸시업 15회입니다.",
    "자세를 바르게 유지하세요.",
    "무릎이 발끝을 넘지 않도록 주의하세요.",
    "잘 하고 계십니다. 조금만 더 힘내세요!",
    "오늘 운동 목표의 절반을 달성했습니다.",
    "플랭크 30초를 시작합니다. 지금!",
    "코어에 힘을 주세요.",
    "거의 다 됐습니다. 10초만 더요.",
    "수고하셨습니다. 잠깐 쉬겠습니다.",
    "이번 세트는 런지 12회입니다.",
    "왼발부터 시작합니다.",
    "균형을 잃지 마세요. 천천히 움직이세요.",
    "체중이 앞발에 실리도록 하세요.",
    "훌륭합니다! 오늘 컨디션이 좋아 보이네요.",
    "이제 마지막 세트입니다. 최선을 다해주세요.",
    "버피 5회를 마무리로 하겠습니다.",
    "전신 운동이니 속도보다 자세가 중요합니다.",
    "마지막 하나, 잘 마무리하세요.",
    "오늘 운동이 모두 끝났습니다. 수고 많으셨어요!",
    "스트레칭으로 근육을 풀어주세요.",
    "허벅지 스트레칭을 30초 동안 합니다.",
    "어깨를 뒤로 돌려 긴장을 풀어드립니다.",
    "물을 충분히 마시고 오늘 운동 기록을 남겨두세요.",
    "다음 운동도 함께해요. 건강한 하루 보내세요!",
]


async def synthesize_all(output_dir: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.adapters.tts.protocol import TTSRequest
    from app.adapters.tts.qwen3 import Qwen3TTSAdapter
    from app.config import load_config

    config = load_config()
    ref_path = config.tts.qwen3.get("ref_audio_path", "")
    if not Path(ref_path).exists():
        print(f"오류: 참조 음성 파일이 없습니다 — {ref_path}", file=sys.stderr)
        print("data/ref_voice.wav (3초 이상 한국어 WAV)를 먼저 준비하세요.", file=sys.stderr)
        sys.exit(1)

    print("Qwen3-TTS 모델 로딩 중...")
    adapter = Qwen3TTSAdapter(config)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(KOREAN_SENTENCES)
    t_start = time.monotonic()

    for i, sentence in enumerate(KOREAN_SENTENCES, 1):
        req = TTSRequest(text=sentence)
        wav_bytes = await adapter.synthesize(req)
        out_file = output_dir / f"qwen3_{i:02d}.wav"
        out_file.write_bytes(wav_bytes)
        elapsed = time.monotonic() - t_start
        print(f"[{i:02d}/{total}] {out_file.name}  {len(wav_bytes):>7,} bytes  ({elapsed:.1f}s)")

    total_sec = time.monotonic() - t_start
    print(f"\n완료: {total}문장 → {output_dir}/  (총 {total_sec:.1f}초)")
    print("청취 후 config.yaml 의 tts.qwen3 설정을 조정하세요.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen3-TTS 한국어 합성 비교 스크립트")
    parser.add_argument("--out", default="data/tts_compare", help="출력 폴더")
    args = parser.parse_args()
    asyncio.run(synthesize_all(Path(args.out)))


if __name__ == "__main__":
    main()
