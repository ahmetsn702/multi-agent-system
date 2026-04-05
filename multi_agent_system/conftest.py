"""
conftest.py
Pytest configuration and shared fixtures.
"""
import sys
import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Get the absolute path to the multi_agent_system directory
project_root = os.path.abspath(os.path.dirname(__file__))

# Add project root at the beginning of sys.path for absolute imports
if project_root in sys.path:
    sys.path.remove(project_root)
sys.path.insert(0, project_root)


@pytest.fixture
def mock_llm():
    """Mock LLMClient that returns a fixed response without API calls."""
    mock = AsyncMock()
    mock.complete = AsyncMock(return_value='{"plan": ["step1"], "files_to_create": ["main.py"]}')
    return mock


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with standard project structure."""
    workspace = tmp_path / "workspace" / "projects" / "test-project"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir(parents=True)
    (workspace / "docs").mkdir(parents=True)
    yield workspace
    # Cleanup handled by tmp_path


@pytest.fixture
def mock_chromadb():
    """In-memory dict that mimics ChromaDB collection interface."""
    class FakeCollection:
        def __init__(self):
            self._store: dict[str, dict] = {}

        def upsert(self, ids, embeddings=None, documents=None, metadatas=None):
            for i, id_ in enumerate(ids):
                self._store[id_] = {
                    "document": documents[i] if documents else "",
                    "metadata": metadatas[i] if metadatas else {},
                }

        def query(self, query_embeddings=None, n_results=3):
            ids = list(self._store.keys())[:n_results]
            return {
                "ids": [ids],
                "documents": [[self._store[k]["document"] for k in ids]],
                "metadatas": [[self._store[k]["metadata"] for k in ids]],
                "distances": [[0.1] * len(ids)],
            }

        def count(self):
            return len(self._store)

        def delete(self, ids):
            for id_ in ids:
                self._store.pop(id_, None)

    return FakeCollection()
