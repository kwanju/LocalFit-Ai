"""Integration tests for the FastAPI layer (phase-4b).

Uses a temp SQLite DB (dependency override) and a mock LLM adapter so the suite
runs without GPU / Ollama. Covers one path per endpoint plus the C2C WebSocket
round-trip (the phase completion criterion).
"""

import asyncio
import base64
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.llm.protocol import LLMRequest
from app.adapters.stt.protocol import STTResult
from app.db.engine import get_session, init_db
from app.main import app

# Marker that appears only in the intent-classify prompt (app.prompts.coaching).
_CLASSIFY_MARKER = "JSON 형식"
_RESPONSE_TEXT = "좋아요! 천천히 호흡하면서 계속해봐요."


class MockLLM:
    """ADR-010 Protocol-compliant stub: classifies as 'general', echoes a reply."""

    async def generate(self, request: LLMRequest) -> str:
        content = request.messages[-1].content
        if _CLASSIFY_MARKER in content:
            return '{"intent": "general"}'
        return _RESPONSE_TEXT

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        yield await self.generate(request)

    async def health(self) -> bool:
        return True


class MockSTT:
    """ADR-010 Protocol-compliant stub: returns a fixed transcript for any audio."""

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> STTResult:
        return STTResult(text="스쿼트 폼 알려줘", language="ko", duration_ms=10)

    async def health(self) -> bool:
        return True


@pytest.fixture
def client(tmp_path) -> AsyncIterator[TestClient]:
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    asyncio.run(init_db(engine=engine))

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        app.state.llm = MockLLM()
        app.state.stt = None
        app.state.tts = None
        yield test_client
    app.dependency_overrides.clear()


def test_health_reports_adapter_status(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] is True
    assert body["adapters"]["llm"] is True
    assert body["adapters"]["stt"] is False
    assert body["adapters"]["tts"] is False
    assert body["status"] == "degraded"


def test_create_session(client: TestClient) -> None:
    response = client.post("/sessions", json={"mode": "c2c"})
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "c2c"
    assert body["status"] == "in_progress"
    assert body["id"] is not None


def test_routine_crud(client: TestClient) -> None:
    created = client.post(
        "/routines",
        json={"name": "테스트 루틴", "exercises": [{"exercise_id": 1, "sets": 3, "reps": 10}]},
    )
    assert created.status_code == 201
    routine_id = created.json()["routine"]["id"]
    assert len(created.json()["exercises"]) == 1

    fetched = client.get(f"/routines/{routine_id}")
    assert fetched.status_code == 200
    assert fetched.json()["routine"]["name"] == "테스트 루틴"
    assert len(fetched.json()["exercises"]) == 1


def test_onboarding_generates_first_routine(client: TestClient) -> None:
    response = client.post(
        "/onboarding",
        json={
            "name": "관주",
            "fitness_level": "beginner",
            "available_times": ["mon-19:00"],
            "goal": "근력 향상",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["profile"]["fitness_level"] == "beginner"
    assert body["profile"]["goal"] == "근력 향상"  # goal stored as profile data
    assert len(body["exercises"]) == 4  # 4 seeded exercises (부록 A-3 기본값)

    status = client.get("/onboarding")
    assert status.json()["onboarded"] is True
    assert status.json()["profile"]["goal"] == "근력 향상"


def test_ws_coach_c2c_roundtrip(client: TestClient) -> None:
    with client.websocket_connect("/ws/coach") as ws:
        ws.send_json({"type": "start", "mode": "c2c"})
        started = ws.receive_json()
        assert started["type"] == "session_started"
        assert started["state"] == "exercising"

        ws.send_json({"type": "text", "text": "스쿼트 폼 알려줘"})
        response = ws.receive_json()
        assert response["type"] == "response"
        assert response["response_text"] == _RESPONSE_TEXT
        assert response["audio_b64"] is None  # no TTS in C2C
        assert response["state"] == "exercising"

        ws.send_json({"type": "end"})
        ended = ws.receive_json()
        assert ended["type"] == "session_ended"


def test_ws_coach_s2c_audio_roundtrip(client: TestClient) -> None:
    # Voice input (s2c) needs an STT adapter; set it just for this test so the
    # /health adapter assertions elsewhere stay untouched.
    app.state.stt = MockSTT()
    audio_b64 = base64.b64encode(b"RIFFfake-wav-bytes").decode("ascii")
    with client.websocket_connect("/ws/coach") as ws:
        ws.send_json({"type": "start", "mode": "s2c"})
        started = ws.receive_json()
        assert started["type"] == "session_started"
        assert started["mode"] == "s2c"

        ws.send_json({"type": "audio", "audio_b64": audio_b64, "sample_rate": 16000})
        response = ws.receive_json()
        assert response["type"] == "response"
        assert response["user_text"] == "스쿼트 폼 알려줘"  # from MockSTT
        assert response["response_text"] == _RESPONSE_TEXT
        assert response["audio_b64"] is None  # s2c = text output

        ws.send_json({"type": "end"})
        assert ws.receive_json()["type"] == "session_ended"
