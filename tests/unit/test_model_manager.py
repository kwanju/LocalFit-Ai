"""Unit tests for the on-demand ModelManager (ADR-030) — no GPU required.

The adapter factories are monkeypatched with fakes so we exercise the
load/unload/idempotency/rollback logic without loading real models. Actual VRAM
return is a GPU smoke (scripts/spike_vram_lifecycle.py), not a unit test.
"""

from __future__ import annotations

import asyncio

import pytest

import app.adapters.llm as llm_mod
import app.adapters.stt as stt_mod
import app.adapters.tts as tts_mod
from app.adapters.model_manager import MSG_LOAD_FAILED, MSG_VRAM_FULL, ModelLoadError, ModelManager


class _FakeLLM:
    def __init__(self) -> None:
        self.warmups = 0
        self.unloads = 0

    async def warmup(self, keep_alive: str | None = None) -> None:
        self.warmups += 1

    async def unload(self) -> None:
        self.unloads += 1


class _FakeExecutor:
    def __init__(self) -> None:
        self.shutdowns = 0

    def shutdown(self, wait: bool = True) -> None:
        self.shutdowns += 1


class _FakeTTS:
    def __init__(self) -> None:
        self._executor = _FakeExecutor()
        self._model = object()
        self.released = False

    def release(self) -> None:
        # 실제 어댑터처럼: executor 종료 + 무거운 모델 드롭(VRAM 회수 — in-process 누수 fix).
        self._executor.shutdown(wait=True)
        self._model = None
        self.released = True


class _FakeSTT:
    def __init__(self) -> None:
        self._model = object()
        self.released = False

    def release(self) -> None:
        self._model = None
        self.released = True


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict:
    state: dict = {"llm": None, "stt": None, "tts": None, "stt_calls": 0}

    def fake_llm(config: object) -> _FakeLLM:
        state["llm"] = _FakeLLM()
        return state["llm"]

    def fake_stt(config: object) -> _FakeSTT:
        state["stt_calls"] += 1
        state["stt"] = _FakeSTT()
        return state["stt"]

    def fake_tts(config: object) -> _FakeTTS:
        state["tts"] = _FakeTTS()
        return state["tts"]

    monkeypatch.setattr(llm_mod, "get_llm_adapter", fake_llm)
    monkeypatch.setattr(stt_mod, "get_stt_adapter", fake_stt)
    monkeypatch.setattr(tts_mod, "get_tts_adapter", fake_tts)
    return state


def _manager() -> ModelManager:
    # config is opaque to the fakes — a sentinel is fine.
    return ModelManager(config=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_load_sets_adapters_and_warms_llm(fakes: dict) -> None:
    mgr = _manager()
    assert mgr.loaded is False

    await mgr.load()

    assert mgr.loaded is True
    assert mgr.stt is fakes["stt"]
    assert mgr.tts is fakes["tts"]
    assert mgr.llm is fakes["llm"]
    assert fakes["llm"].warmups == 1


@pytest.mark.asyncio
async def test_load_is_idempotent(fakes: dict) -> None:
    mgr = _manager()
    await mgr.load()
    await mgr.load()  # no-op — must not re-construct STT or re-warm
    assert fakes["stt_calls"] == 1
    assert fakes["llm"].warmups == 1


@pytest.mark.asyncio
async def test_concurrent_load_loads_once(fakes: dict) -> None:
    mgr = _manager()
    await asyncio.gather(mgr.load(), mgr.load(), mgr.load())
    assert fakes["stt_calls"] == 1
    assert fakes["llm"].warmups == 1


@pytest.mark.asyncio
async def test_unload_reclaims_and_resets(fakes: dict) -> None:
    mgr = _manager()
    await mgr.load()
    llm, tts, stt = fakes["llm"], fakes["tts"], fakes["stt"]

    await mgr.unload()

    assert mgr.loaded is False
    assert mgr.stt is None and mgr.tts is None and mgr.llm is None
    assert llm.unloads == 1  # Ollama keep_alive=0
    assert tts._executor.shutdowns == 1  # CUDA-graph thread shut down
    # ★ 누수 fix: 어댑터 내부 모델까지 release 로 드롭(참조가 남아도 VRAM 회수).
    assert tts.released and tts._model is None
    assert stt.released and stt._model is None


@pytest.mark.asyncio
async def test_overlapping_sessions_do_not_early_unload(fakes: dict) -> None:
    """겹친 세션 보호(refcount): 두 세션 중 하나가 끝나도 다른 세션의 모델을 unload 하면
    안 된다(이중 연결 → TTS executor shutdown 'cannot schedule new futures' 회귀)."""
    mgr = _manager()
    await mgr.load()
    mgr.session_begin()  # 세션 #1
    mgr.session_begin()  # 세션 #2 (겹침)

    # #1 종료 — 아직 #2 활성이므로 unload 보류.
    remaining = mgr.session_end()
    assert remaining == 1
    if remaining == 0:  # 호출부(ws_voice) 규약 모사
        await mgr.unload()
    assert mgr.loaded is True
    assert fakes["tts"].released is False  # 모델 살아있음

    # #2 종료 — 마지막 세션이므로 unload.
    remaining = mgr.session_end()
    assert remaining == 0
    await mgr.unload()
    assert mgr.loaded is False
    assert fakes["tts"].released is True


@pytest.mark.asyncio
async def test_unload_when_idle_is_noop(fakes: dict) -> None:
    mgr = _manager()
    await mgr.unload()  # never loaded — must not raise
    assert mgr.loaded is False


@pytest.mark.asyncio
async def test_oom_raises_vram_message_and_rolls_back(
    fakes: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def oom_stt(config: object) -> _FakeSTT:
        raise RuntimeError("CUDA out of memory: tried to allocate ...")

    monkeypatch.setattr(stt_mod, "get_stt_adapter", oom_stt)
    mgr = _manager()

    with pytest.raises(ModelLoadError) as exc:
        await mgr.load()

    assert str(exc.value) == MSG_VRAM_FULL
    assert mgr.loaded is False
    assert mgr.stt is None and mgr.tts is None and mgr.llm is None
    # The successfully-warmed LLM must be unloaded during rollback (no VRAM leak).
    assert fakes["llm"].unloads == 1


@pytest.mark.asyncio
async def test_generic_load_failure_uses_generic_message(
    fakes: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    def bad_tts(config: object) -> _FakeTTS:
        raise FileNotFoundError("ref_voice.wav missing")

    monkeypatch.setattr(tts_mod, "get_tts_adapter", bad_tts)
    mgr = _manager()

    with pytest.raises(ModelLoadError) as exc:
        await mgr.load()
    assert str(exc.value) == MSG_LOAD_FAILED
    assert mgr.loaded is False
