import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from backend.agent.loop import MAX_ITERATIONS
from backend.agent.tools.web_search import web_search


# --- helpers to fake OpenAI-style completion responses ------------------------


def _tool_call(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(content=None, tool_calls=None):
    message = SimpleNamespace(role="assistant", content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _fake_llm(responses):
    fake = MagicMock()
    fake._model = "test-model"
    fake.chat.completions.create = AsyncMock(side_effect=responses)
    return fake


# --- web_search tool unit tests -----------------------------------------------


@pytest.mark.asyncio
async def test_web_search_returns_results(monkeypatch):
    fake_client = MagicMock()
    fake_client.search = AsyncMock(
        return_value={
            "results": [
                {"title": "Kabul Weather", "url": "https://example.com", "content": "Sunny, 20C"},
            ]
        }
    )
    monkeypatch.setattr(
        "backend.agent.tools.web_search.AsyncTavilyClient",
        MagicMock(return_value=fake_client),
    )
    monkeypatch.setattr("backend.agent.tools.web_search.settings.tavily_api_key", "test-key")

    result = await web_search("weather in Kabul today")

    assert result["query"] == "weather in Kabul today"
    assert result["results"][0]["title"] == "Kabul Weather"
    assert result["results"][0]["url"] == "https://example.com"
    fake_client.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_search_missing_key(monkeypatch):
    monkeypatch.setattr("backend.agent.tools.web_search.settings.tavily_api_key", "")
    result = await web_search("anything")
    assert "error" in result
    assert "TAVILY_API_KEY" in result["error"]


@pytest.mark.asyncio
async def test_web_search_handles_failure(monkeypatch):
    fake_client = MagicMock()
    fake_client.search = AsyncMock(side_effect=RuntimeError("network down"))
    monkeypatch.setattr(
        "backend.agent.tools.web_search.AsyncTavilyClient",
        MagicMock(return_value=fake_client),
    )
    monkeypatch.setattr("backend.agent.tools.web_search.settings.tavily_api_key", "test-key")

    result = await web_search("weather")
    assert "error" in result
    assert "network down" in result["error"]


# --- agent loop integration tests (LLM + Tavily mocked) -----------------------


@pytest.mark.asyncio
async def test_agent_uses_web_search(client: AsyncClient, monkeypatch):
    # Tavily mock
    fake_client = MagicMock()
    fake_client.search = AsyncMock(
        return_value={
            "results": [
                {"title": "Kabul Weather", "url": "https://wx.example", "content": "Clear, 18C"},
            ]
        }
    )
    monkeypatch.setattr(
        "backend.agent.tools.web_search.AsyncTavilyClient",
        MagicMock(return_value=fake_client),
    )
    monkeypatch.setattr("backend.agent.tools.web_search.settings.tavily_api_key", "test-key")

    # LLM: first turn requests a web_search, second turn gives the final answer
    responses = [
        _response(
            tool_calls=[
                _tool_call("c1", "web_search", json.dumps({"query": "weather in Kabul today"}))
            ]
        ),
        _response(content="It's clear and 18C in Kabul right now."),
    ]
    monkeypatch.setattr("backend.agent.loop.llm_client", _fake_llm(responses))

    thread = (await client.post("/threads/", json={"title": "T"})).json()
    resp = await client.post(
        f"/threads/{thread['id']}/chat",
        json={"message": "What's the weather in Kabul today?"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "Kabul" in data["response"]

    tool_msgs = [m for m in data["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_name"] == "web_search"
    payload = json.loads(tool_msgs[0]["content"])
    assert "Kabul" in payload["query"]
    assert payload["results"][0]["url"] == "https://wx.example"


@pytest.mark.asyncio
async def test_agent_stops_at_iteration_cap(client: AsyncClient, monkeypatch):
    # LLM always asks for a (real, network-free) calculator call, never stopping.
    # The loop must cap out and the forced final call returns text.
    always_tool = _response(
        tool_calls=[_tool_call("c", "calculator", json.dumps({"expression": "1+1"}))]
    )
    responses = [always_tool] * MAX_ITERATIONS + [_response(content="Final answer.")]
    fake = _fake_llm(responses)
    monkeypatch.setattr("backend.agent.loop.llm_client", fake)

    thread = (await client.post("/threads/", json={"title": "T"})).json()
    resp = await client.post(
        f"/threads/{thread['id']}/chat", json={"message": "loop forever"}
    )

    assert resp.status_code == 200
    assert resp.json()["response"] == "Final answer."
    # MAX_ITERATIONS tool-calling rounds + 1 forced final (tool_choice="none")
    assert fake.chat.completions.create.await_count == MAX_ITERATIONS + 1