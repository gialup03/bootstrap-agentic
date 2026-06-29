from tavily import AsyncTavilyClient

from backend.agent.tools import register_tool
from backend.config import settings

MAX_RESULTS = 5


@register_tool(
    name="web_search",
    description=(
        "Search the live web for current, real-world information such as weather, "
        "news, recent events, prices, or any fact that may have changed recently. "
        "Returns a list of relevant sources with titles, URLs, and content snippets. "
        "Read the snippets and cite the sources in your answer."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, e.g. 'weather in Kabul today'",
            }
        },
        "required": ["query"],
    },
)
async def web_search(query: str) -> dict:
    """Search the web via Tavily and return raw source snippets."""
    if not settings.tavily_api_key:
        return {
            "query": query,
            "error": "Web search is unavailable: TAVILY_API_KEY is not configured.",
        }

    try:
        client = AsyncTavilyClient(api_key=settings.tavily_api_key)
        response = await client.search(
            query,
            search_depth="basic",
            max_results=MAX_RESULTS,
            include_answer=False,
        )
    except Exception as e:
        return {"query": query, "error": f"Web search failed: {e}"}

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        }
        for r in response.get("results", [])
    ]

    if not results:
        return {"query": query, "error": "No results found.", "results": []}

    return {"query": query, "results": results}
