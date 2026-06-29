"""Live end-to-end eval for the web_search tool.

Opt-in only: hits the real LLM and the real Tavily API. Run with:

    RUN_LIVE_EVALS=1 uv run pytest -m eval -v

Asserts on tool usage and grounding (not exact weather values), so it stays
stable despite a live model and live web data.
"""

import json
import os

import pytest
from httpx import AsyncClient

from backend.config import settings

_RUN = os.environ.get("RUN_LIVE_EVALS") == "1"
_HAS_KEYS = bool(settings.llm_api_key) and bool(settings.tavily_api_key)

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not (_RUN and _HAS_KEYS),
        reason="Live eval: set RUN_LIVE_EVALS=1 and configure LLM_API_KEY + TAVILY_API_KEY",
    ),
]


def _web_search_calls(chat_data: dict) -> list[dict]:
    """Extract the parsed payloads of every web_search tool message in a thread."""
    return [
        json.loads(m["content"])
        for m in chat_data["messages"]
        if m["role"] == "tool" and m.get("tool_name") == "web_search"
    ]


@pytest.mark.asyncio
async def test_agent_searches_for_kabul_weather(client: AsyncClient):
    thread = (await client.post("/threads/", json={"title": "Eval"})).json()
    thread_id = thread["id"]

    # --- Turn 1: the target user prompt ---
    resp1 = await client.post(
        f"/threads/{thread_id}/chat",
        json={"message": "What's the weather in Kabul today?"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()

    calls1 = _web_search_calls(data1)
    # 1. The agent chose to search, unprompted.
    assert calls1, "agent did not call web_search for a live-weather question"
    # 2. It derived a sensible, on-topic query from the prompt.
    assert any("kabul" in (c.get("query") or "").lower() for c in calls1)
    # 3. The final answer is grounded in the question (loose check — no exact temp).
    assert data1["response"].strip()
    assert "kabul" in data1["response"].lower()

    # --- Turn 2: follow-up in the same thread requires fresh data ---
    resp2 = await client.post(
        f"/threads/{thread_id}/chat",
        json={"message": "What about tomorrow?"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()

    calls2 = _web_search_calls(data2)
    # The follow-up triggered at least one more search (multi-turn tool reuse).
    assert len(calls2) > len(calls1)
    assert data2["response"].strip()
