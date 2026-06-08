"""Per-connection Pipecat Service factory (ADR-011/012).

Pipecat 1.3.0의 FrameProcessor 인스턴스는 단일 파이프라인 lifecycle에 종속된다
(내부 task / settings / audio context). 따라서 ws 연결마다 *Service 인스턴스를
새로 만들어야 안전하다. 모델 자체는 Client (FasterWhisperClient / Qwen3TTSClient /
MeloTTSClient) 안에서 로드되어 있고, lifespan 시점에 한 번만 만들어진다 — 여기서는
그 client를 받아 Pipecat 래퍼만 새로 인스턴스화한다.
"""

from __future__ import annotations

from loguru import logger
from pipecat.processors.frame_processor import FrameProcessor


def build_tts_service(tts_client: object) -> FrameProcessor | None:
    """Construct a fresh Pipecat TTSService wrapping *tts_client*.

    Returns ``None`` if the client type is unknown (e.g. no TTS adapter loaded).
    """
    if tts_client is None:
        return None

    # Local import so a missing optional GPU dep doesn't break import-time.
    from app.adapters.tts.qwen3_client import Qwen3TTSClient

    if isinstance(tts_client, Qwen3TTSClient):
        from app.pipecat_services.qwen3_tts_service import Qwen3TTSService

        return Qwen3TTSService(tts_client)

    logger.warning("build_tts_service: unknown client type {}", type(tts_client).__name__)
    return None


def build_stt_service(stt_client: object) -> FrameProcessor | None:
    """Construct a fresh Pipecat STTService wrapping *stt_client*."""
    if stt_client is None:
        return None

    from app.adapters.stt.faster_whisper_client import FasterWhisperClient

    if isinstance(stt_client, FasterWhisperClient):
        from app.pipecat_services.whisper_service import LocalFitWhisperSTTService

        return LocalFitWhisperSTTService(stt_client)

    logger.warning("build_stt_service: unknown client type {}", type(stt_client).__name__)
    return None
