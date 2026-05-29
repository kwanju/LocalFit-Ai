"""WebSocket /ws/coach — real-time bidirectional coaching.

JSON protocol (client → server): {"type": "start"|"text"|"audio"|"listen_start"|
"audio_chunk"|"listen_stop"|"interrupt"|"pause"|"resume"|"start_counting"|
"stop_counting"|"end", ...}. Server → client: "session_started" | "response" |
"beat" | "state" | "error" | "session_ended".

The endpoint stays thin: it owns the socket and translates messages into
SessionOrchestrator calls (core). Beat events are pushed concurrently while the
receive loop keeps reading, so an "interrupt" can cancel in-flight LLM/TTS.

Live S2S (hands-free): the client streams 16kHz mono PCM16 chunks ("audio_chunk")
while "listening". A server-side silero-vad session segments utterances; each
completed utterance runs the same voice-reply pipeline. Half-duplex — chunks are
ignored while a reply is in flight (the coach is "speaking").
"""

import asyncio
import base64
import logging

import numpy as np
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import AppConfig
from app.core.counting import BeatEvent, ExerciseMode
from app.core.intent import IntentClassifier
from app.core.orchestrator import InteractionResult, SessionMode, SessionOrchestrator
from app.core.safety import SafetyGuard
from app.core.state_machine import is_terminal
from app.db.engine import get_session
from app.db.repositories import SessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

_INT16_SCALE = 32768.0  # int16 <-> float32 normalization
_LIVE_SAMPLE_RATE = 16000  # silero-vad / STT fixed rate


class _CoachConnection:
    """Per-connection coaching session. One DB session for the connection's lifetime."""

    def __init__(
        self,
        websocket: WebSocket,
        db_session: AsyncSession,
        *,
        config: AppConfig | None,
        llm: object,
        stt: object | None,
        tts: object | None,
        vad: object | None = None,
    ) -> None:
        self._ws = websocket
        self._config = config
        self._llm = llm
        self._stt = stt
        self._tts = tts
        self._vad = vad
        self._session_repo = SessionRepository(db_session)
        self._orch: SessionOrchestrator | None = None
        self._send_lock = asyncio.Lock()
        # Serializes state/DB-mutating ops so the background reply task and the
        # receive loop never touch the (non-concurrency-safe) orchestrator or
        # AsyncSession at the same time. interrupt() is intentionally lock-free.
        self._op_lock = asyncio.Lock()
        self._handle_tasks: set[asyncio.Task] = set()
        # Live S2S streaming state.
        self._vad_session: object | None = None
        self._reply_active = False  # half-duplex: True while the coach is responding

    async def run(self) -> None:
        try:
            while True:
                message = await self._ws.receive_json()
                stop = await self._dispatch(message)
                if stop:
                    break
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:  # noqa: BLE001 — never let a bad frame crash the socket loop
            logger.error("WebSocket loop error: %s", e)
        finally:
            await self._cleanup()

    async def _dispatch(self, message: dict) -> bool:
        msg_type = message.get("type")
        handlers = {
            "start": self._handle_start,
            "text": self._handle_text,
            "audio": self._handle_audio,
            "listen_start": self._handle_listen_start,
            "audio_chunk": self._handle_audio_chunk,
            "listen_stop": self._handle_listen_stop,
            "interrupt": self._handle_interrupt,
            "pause": self._handle_pause,
            "resume": self._handle_resume,
            "start_counting": self._handle_start_counting,
            "stop_counting": self._handle_stop_counting,
        }
        if msg_type == "end":
            await self._handle_end()
            return True
        handler = handlers.get(msg_type)
        if handler is None:
            await self._send_error(f"알 수 없는 메시지 유형입니다: {msg_type}")
            return False
        await handler(message)
        return False

    # -- handlers ---------------------------------------------------------

    async def _handle_start(self, message: dict) -> None:
        if self._orch is not None:
            await self._send_error("이미 세션이 시작되었습니다.")
            return
        try:
            mode = SessionMode(message.get("mode", SessionMode.c2c.value))
        except ValueError:
            await self._send_error("알 수 없는 세션 모드입니다.")
            return
        timeout_sec = self._config.llm.timeout_sec if self._config is not None else None
        classifier = (
            IntentClassifier(self._llm, timeout_sec=timeout_sec)  # type: ignore[arg-type]
            if timeout_sec is not None
            else IntentClassifier(self._llm)  # type: ignore[arg-type]
        )
        try:
            orch = SessionOrchestrator(
                intent=classifier,
                safety=SafetyGuard(),
                mode=mode,
                stt=self._stt,  # type: ignore[arg-type]
                tts=self._tts,  # type: ignore[arg-type]
                persister=self._session_repo,
                on_beat=self._on_beat,
            )
        except ValueError as e:
            logger.warning("Session rejected for mode %s: %s", mode.value, e)
            await self._send_error("이 모드에는 음성 어댑터가 필요합니다.")
            return
        async with self._op_lock:
            record = await self._session_repo.create(
                mode=mode.value, routine_id=message.get("routine_id")
            )
            self._orch = orch
            await orch.start_session(session_id=record.id)
        await self._send(
            {
                "type": "session_started",
                "session_id": record.id,
                "mode": mode.value,
                "state": orch.state.value,
            }
        )

    async def _handle_text(self, message: dict) -> None:
        if self._orch is None:
            await self._send_error("세션이 시작되지 않았습니다.")
            return
        text = message.get("text", "")
        if not text:
            await self._send_error("빈 메시지는 보낼 수 없습니다.")
            return
        task = asyncio.create_task(self._reply(text))
        self._handle_tasks.add(task)
        task.add_done_callback(self._handle_tasks.discard)

    async def _reply(self, text: str) -> None:
        try:
            async with self._op_lock:
                result = await self._orch.handle_text_input(text)  # type: ignore[union-attr]
            await self._send(self._serialize_result(result))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — surface failures to the client, keep socket alive
            logger.error("Coaching reply failed: %s", e)
            await self._send_error("코치 응답 중 오류가 발생했습니다.")

    async def _handle_audio(self, message: dict) -> None:
        """Voice input (s2s/s2c): base64 16kHz WAV → STT → coaching, like _handle_text."""
        if self._orch is None:
            await self._send_error("세션이 시작되지 않았습니다.")
            return
        audio_b64 = message.get("audio_b64")
        if not audio_b64:
            await self._send_error("빈 오디오는 보낼 수 없습니다.")
            return
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except ValueError:  # binascii.Error subclasses ValueError
            await self._send_error("오디오를 디코딩할 수 없습니다.")
            return
        sample_rate = message.get("sample_rate", 16000)
        task = asyncio.create_task(self._reply_voice(audio_bytes, sample_rate))
        self._handle_tasks.add(task)
        task.add_done_callback(self._handle_tasks.discard)

    async def _reply_voice(self, audio_bytes: bytes, sample_rate: int) -> None:
        try:
            async with self._op_lock:
                result = await self._orch.handle_voice_input(  # type: ignore[union-attr]
                    audio_bytes, sample_rate
                )
            await self._send(self._serialize_result(result))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — surface failures to the client, keep socket alive
            logger.error("Voice coaching reply failed: %s", e)
            await self._send_error("음성 인식 중 오류가 발생했습니다.")
        finally:
            self._reply_active = False

    # -- live S2S (streaming VAD) -----------------------------------------

    async def _handle_listen_start(self, _message: dict) -> None:
        if self._orch is None:
            await self._send_error("세션이 시작되지 않았습니다.")
            return
        if self._vad is None or self._stt is None:
            await self._send_error("라이브 모드에는 음성 어댑터(VAD/STT)가 필요합니다.")
            return
        self._vad_session = self._vad.new_stream()  # type: ignore[attr-defined]
        self._reply_active = False
        await self._send({"type": "vad", "event": "listening"})

    async def _handle_audio_chunk(self, message: dict) -> None:
        # Ignore until listening; ignore while the coach is responding (half-duplex).
        if self._vad_session is None or self._reply_active:
            return
        pcm_b64 = message.get("pcm_b64")
        if not pcm_b64:
            return
        try:
            raw = base64.b64decode(pcm_b64)
        except ValueError:
            return
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / _INT16_SCALE
        utterances = await asyncio.to_thread(self._vad_session.feed, pcm)  # type: ignore[attr-defined]
        for utterance in utterances:
            # One utterance per turn: take the first, drop the rest, go half-duplex.
            self._reply_active = True
            self._vad_session.reset()  # type: ignore[attr-defined]
            audio_bytes = (np.clip(utterance, -1.0, 1.0) * _INT16_SCALE).astype(np.int16).tobytes()
            await self._send({"type": "vad", "event": "speech_end"})
            task = asyncio.create_task(self._reply_voice(audio_bytes, _LIVE_SAMPLE_RATE))
            self._handle_tasks.add(task)
            task.add_done_callback(self._handle_tasks.discard)
            break

    async def _handle_listen_stop(self, _message: dict) -> None:
        if self._vad_session is not None:
            self._vad_session.reset()  # type: ignore[attr-defined]
            self._vad_session = None

    async def _handle_interrupt(self, _message: dict) -> None:
        if self._orch is not None:
            await self._orch.interrupt()

    async def _handle_pause(self, _message: dict) -> None:
        if self._orch is None:
            await self._send_error("세션이 시작되지 않았습니다.")
            return
        async with self._op_lock:
            await self._orch.pause()
        await self._send_state()

    async def _handle_resume(self, _message: dict) -> None:
        if self._orch is None:
            await self._send_error("세션이 시작되지 않았습니다.")
            return
        async with self._op_lock:
            await self._orch.resume()
        await self._send_state()

    async def _handle_start_counting(self, message: dict) -> None:
        if self._orch is None:
            await self._send_error("세션이 시작되지 않았습니다.")
            return
        if self._config is None:
            await self._send_error("설정을 불러올 수 없습니다.")
            return
        try:
            exercise_mode = ExerciseMode(message.get("mode", ExerciseMode.metronome.value))
        except ValueError:
            await self._send_error("알 수 없는 운동 모드입니다.")
            return
        try:
            async with self._op_lock:
                await self._orch.start_counting(
                    exercise_mode,
                    interval_sec=self._config.counting.beat_interval_sec,
                    max_reps=self._config.counting.max_reps,
                    target_duration_sec=message.get("target_duration_sec"),
                )
        except Exception as e:  # noqa: BLE001 — report to client, keep socket alive
            logger.error("start_counting failed: %s", e)
            await self._send_error("카운팅을 시작할 수 없습니다.")

    async def _handle_stop_counting(self, _message: dict) -> None:
        if self._orch is not None:
            async with self._op_lock:
                await self._orch.stop_counting()

    async def _handle_end(self) -> None:
        async with self._op_lock:
            if self._orch is not None and not is_terminal(self._orch.state):
                await self._orch.end_session()
            state = self._orch.state.value if self._orch is not None else None
        await self._send({"type": "session_ended", "state": state})

    # -- helpers ----------------------------------------------------------

    async def _on_beat(self, event: BeatEvent) -> None:
        await self._send(
            {
                "type": "beat",
                "rep": event.rep,
                "phase": event.phase,
                "elapsed_sec": round(event.elapsed_sec, 2),
            }
        )

    def _serialize_result(self, result: InteractionResult) -> dict:
        audio_b64 = (
            base64.b64encode(result.response_audio).decode("ascii")
            if result.response_audio is not None
            else None
        )
        return {
            "type": "response",
            "user_text": result.user_text,
            "response_text": result.response_text,
            "state": result.state.value,
            "intent": result.intent,
            "safety_triggered": result.safety_triggered,
            "safety_level": result.safety_level.value if result.safety_level else None,
            "audio_b64": audio_b64,
        }

    async def _send_state(self) -> None:
        if self._orch is not None:
            await self._send({"type": "state", "state": self._orch.state.value})

    async def _send_error(self, korean_message: str) -> None:
        await self._send({"type": "error", "message": korean_message})

    async def _send(self, payload: dict) -> None:
        async with self._send_lock:
            await self._ws.send_json(payload)

    async def _cleanup(self) -> None:
        self._vad_session = None
        tasks = list(self._handle_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._orch is None:
            return
        async with self._op_lock:
            try:
                await self._orch.stop_counting()
                if not is_terminal(self._orch.state):
                    await self._orch.end_session()
            except Exception as e:  # noqa: BLE001 — best-effort teardown
                logger.error("Session cleanup failed: %s", e)


@router.websocket("/ws/coach")
async def ws_coach(websocket: WebSocket, db_session: AsyncSession = Depends(get_session)) -> None:
    await websocket.accept()
    state = websocket.app.state
    llm = getattr(state, "llm", None)
    if llm is None:
        await websocket.send_json({"type": "error", "message": "코치를 사용할 수 없습니다."})
        await websocket.close()
        return
    connection = _CoachConnection(
        websocket,
        db_session,
        config=getattr(state, "config", None),
        llm=llm,
        stt=getattr(state, "stt", None),
        tts=getattr(state, "tts", None),
        vad=getattr(state, "vad", None),
    )
    await connection.run()
