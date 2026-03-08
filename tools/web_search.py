"""
tools/web_search.py
DuckDuckGo web search tool with 1-hour result caching.
"""
import hashlib
import json
import os
import time
from typing import Optional

from core.base_agent import ToolResult
from tools.tool_registry import register_tool

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "workspace", "cache")
CACHE_TTL_HOURS = 24
CACHE_TTL = CACHE_TTL_HOURS * 3600

# Global dashboard stats
cache_stats = {"total_queries": 0, "hits": 0}

def _cache_path(query: str) -> str:
    key = hashlib.md5(query.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.json")


def _load_cache(query: str) -> Optional[list[dict]]:
    from datetime import datetime, timezone
    cache_stats["total_queries"] += 1
    path = _cache_path(query)
    
    if os.path.exists(path):
        try:
            with open(path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                
                # Support both old and new formats
                if "cached_at" in data:
                    timestamp_sec = data["cached_at"]
                else:
                    isoformat_str = data.get("timestamp", datetime.now(timezone.utc).isoformat())
                    try:
                        dt = datetime.fromisoformat(isoformat_str.replace("Z", "+00:00"))
                        timestamp_sec = dt.timestamp()
                    except ValueError:
                        timestamp_sec = time.time()
                
                if time.time() - timestamp_sec < CACHE_TTL:
                    # Update hit count
                    data["hit_count"] = data.get("hit_count", 0) + 1
                    f.seek(0)
                    json.dump(data, f)
                    f.truncate()
                    
                    cache_stats["hits"] += 1
                    return data.get("results", [])
        except Exception:
            pass
    return None


def _save_cache(query: str, results: list[dict]):
    from datetime import datetime, timezone
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(query)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "query": query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": results,
                "hit_count": 0
            }, f, ensure_ascii=False)
    except Exception:
        pass


async def web_search(query: str, max_results: int = 5) -> ToolResult:
    """
    Search the web using DuckDuckGo.
    Returns top results with title, url, and snippet.
    """
    # Check cache first
    cached = _load_cache(query)
    if cached:
        return ToolResult(
            success=True,
            data={"results": cached, "source": "cache", "query": query},
        )

    try:
        import urllib.parse
        from ddgs import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
                if len(results) >= max_results:
                    break

        _save_cache(query, results)
        return ToolResult(
            success=True,
            data={"results": results, "source": "live", "query": query},
        )
    except ImportError:
        return ToolResult(
            success=False,
            data=None,
            error="duckduckgo-search package not installed. Run: pip install duckduckgo-search",
        )
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


# Register with the global tool registry
_schema = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query"},
        "max_results": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
    },
    "required": ["query"],
}

# We keep the function as-is and register separately
tool_registry_entry = {
    "name": "web_search",
    "func": web_search,
    "description": "Search the web using DuckDuckGo. Returns top results with title, URL, and snippet.",
    "parameters_schema": _schema,
}
