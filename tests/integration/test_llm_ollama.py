import pytest

from app.adapters.llm.ollama_client import LLMMessage, LLMRequest, OllamaClient
from app.config import load_config

pytestmark = pytest.mark.ollama


@pytest.fixture
def config():
    try:
        return load_config()
    except FileNotFoundError:
        pytest.skip("config.yaml not found — copy config.example.yaml to config.yaml")


@pytest.fixture
def adapter(config):
    return OllamaClient(config)


@pytest.fixture(autouse=True)
async def skip_if_unavailable(adapter):
    if not await adapter.health():
        pytest.skip("Ollama not running")


async def test_health(adapter):
    assert await adapter.health() is True


async def test_generate_korean(adapter):
    request = LLMRequest(
        messages=[
            LLMMessage(role="system", content="당신은 친절한 피트니스 코치입니다. 한국어로만 답해주세요."),  # noqa: E501
            LLMMessage(role="user", content="안녕하세요"),
        ],
        max_tokens=100,
    )
    response = await adapter.generate(request)
    assert isinstance(response, str)
    assert len(response) > 0


async def test_stream_korean(adapter):
    request = LLMRequest(
        messages=[LLMMessage(role="user", content="안녕이라고만 짧게 답해줘")],
        max_tokens=30,
    )
    chunks: list[str] = []
    async for chunk in adapter.stream(request):
        chunks.append(chunk)
    assert len(chunks) > 0
    assert "".join(chunks).strip() != ""


async def test_keep_alive_override(adapter):
    request = LLMRequest(
        messages=[LLMMessage(role="user", content="안녕")],
        max_tokens=20,
        keep_alive="5m",
    )
    response = await adapter.generate(request)
    assert isinstance(response, str)
    assert len(response) > 0
