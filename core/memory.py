"""
core/memory.py
Two-tier memory system:
- Short-term: per-agent sliding window of last 20 interactions
- Long-term: shared persistent key-value store (JSON on disk)
"""
import asyncio
import json
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "memory")
SHARED_MEMORY_PATH = os.path.join(MEMORY_DIR, "shared_memory.json")


class ShortTermMemory:
    """Per-agent sliding window of last N interactions."""

    def __init__(self, agent_id: str, max_size: int = 10):
        self.agent_id = agent_id
        self.max_size = max_size
        self._window: deque[dict] = deque(maxlen=max_size)

    def add(self, role: str, content: str, metadata: Optional[dict] = None):
        """Add a message to short-term memory."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._window.append(entry)

    def get_messages(self) -> list[dict]:
        """Return messages in OpenAI format (role + content only)."""
        return [{"role": m["role"], "content": m["content"]} for m in self._window]

    def get_full(self) -> list[dict]:
        """Return full entries with timestamps and metadata."""
        return list(self._window)

    def clear(self):
        self._window.clear()

    def __len__(self):
        return len(self._window)


class LongTermMemory:
    """
    Shared key-value store persisted to disk.
    Thread-safe via asyncio lock.
    """

    def __init__(self):
        self._store: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._path = SHARED_MEMORY_PATH
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self._load()

    def _load(self):
        """Load existing memory from disk."""
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._store = json.load(f)
            except Exception:
                self._store = {}

    async def _save(self):
        """Persist current store to disk."""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            print(f"[LongTermMemory] Failed to save: {e}")

    async def store(self, key: str, value: Any, agent_id: str = "system"):
        """Store a key-value pair with metadata."""
        async with self._lock:
            self._store[key] = {
                "value": value,
                "agent_id": agent_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._save()

    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a value by key."""
        async with self._lock:
            entry = self._store.get(key)
            return entry["value"] if entry else None

    async def retrieve_full(self, key: str) -> Optional[dict]:
        """Retrieve full entry including metadata."""
        async with self._lock:
            return self._store.get(key)

    async def delete(self, key: str):
        """Remove a key."""
        async with self._lock:
            self._store.pop(key, None)
            await self._save()

    async def list_keys(self) -> list[str]:
        """List all stored keys."""
        async with self._lock:
            return list(self._store.keys())

    async def search(self, query: str) -> dict[str, Any]:
        """Simple substring search over keys."""
        async with self._lock:
            return {
                k: v for k, v in self._store.items()
                if query.lower() in k.lower()
            }

    def __len__(self):
        return len(self._store)


class MemoryManager:
    """
    Central memory manager.
    Provides both short-term (per-agent) and long-term (shared) memory.
    """

    def __init__(self):
        self._short_term: dict[str, ShortTermMemory] = {}
        self.long_term = LongTermMemory()

    def get_short_term(self, agent_id: str) -> ShortTermMemory:
        """Get or create short-term memory for an agent."""
        if agent_id not in self._short_term:
            self._short_term[agent_id] = ShortTermMemory(agent_id)
        return self._short_term[agent_id]

    async def store(self, key: str, value: Any, agent_id: str = "system"):
        await self.long_term.store(key, value, agent_id)

    async def retrieve(self, key: str) -> Optional[Any]:
        return await self.long_term.retrieve(key)

    def add_to_short_term(self, agent_id: str, role: str, content: str, metadata: Optional[dict] = None):
        self.get_short_term(agent_id).add(role, content, metadata)

    def get_context_messages(self, agent_id: str) -> list[dict]:
        return self.get_short_term(agent_id).get_messages()

    def save_session(self, session_data: dict, slug: str = "default"):
        import os, json
        from datetime import datetime, timezone
        workspace_mem = os.path.join(os.path.dirname(__file__), "..", "workspace", "projects", slug)
        os.makedirs(workspace_mem, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filepath = os.path.join(workspace_mem, f"session_{ts}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[MemoryManager] Failed to save session: {e}")

    def get_last_sessions(self, limit: int = 3) -> list[dict]:
        import os, json
        workspace_projects = os.path.join(os.path.dirname(__file__), "..", "workspace", "projects")
        if not os.path.exists(workspace_projects):
            return []
            
        files = []
        for root, _, filenames in os.walk(workspace_projects):
            for f in filenames:
                if f.startswith("session_") and f.endswith(".json"):
                    files.append(os.path.join(root, f))
                    
        files.sort(key=os.path.getmtime, reverse=True)
        
        sessions = []
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    sessions.append(json.load(file))
            except Exception:
                pass
        return sessions


# Singleton memory manager
memory_manager = MemoryManager()
