"""
Unit tests for _ensure_main_py() method in orchestrator.

Tests the three cases:
1. main.py already exists - do nothing (preservation)
2. main.py does not exist AND app.py exists - create re-export shim
3. Neither exists - create full main.py using template
"""
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.orchestrator import Orchestrator


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    temp_dir = tempfile.mkdtemp()
    workspace_dir = os.path.join(temp_dir, "workspace", "projects")
    os.makedirs(workspace_dir, exist_ok=True)
    
    # Store original cwd
    original_cwd = os.getcwd()
    
    # Change to temp directory
    os.chdir(temp_dir)
    
    yield temp_dir
    
    # Restore original cwd and cleanup
    os.chdir(original_cwd)
    shutil.rmtree(temp_dir)


@pytest.fixture
def orchestrator():
    """Create a minimal orchestrator instance for testing."""
    # Create mock agents
    mock_agents = {}
    
    # Create orchestrator with mocked dependencies
    orch = Orchestrator(
        agents=mock_agents,
        message_bus=None,
        human_input_callback=None,
        status_callback=AsyncMock()
    )
    
    return orch


@pytest.mark.asyncio
async def test_ensure_main_py_when_main_exists(temp_workspace, orchestrator):
    """Test Case 1: main.py already exists - do nothing (preservation)."""
    slug = "test-project-1"
    project_dir = os.path.join("workspace", "projects", slug)
    src_dir = Path(project_dir) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    
    # Create existing main.py with custom content
    main_py_path = src_dir / "main.py"
    original_content = "# Original main.py content\nprint('hello')\n"
    with open(main_py_path, "w", encoding="utf-8") as f:
        f.write(original_content)
    
    # Call _ensure_main_py
    await orchestrator._ensure_main_py(slug)
    
    # Verify main.py still has original content (preservation)
    with open(main_py_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert content == original_content, "main.py content should be preserved"


@pytest.mark.asyncio
async def test_ensure_main_py_when_app_exists(temp_workspace, orchestrator):
    """Test Case 2: main.py does not exist AND app.py exists - create re-export shim."""
    slug = "test-project-2"
    project_dir = os.path.join("workspace", "projects", slug)
    src_dir = Path(project_dir) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    
    # Create app.py
    app_py_path = src_dir / "app.py"
    with open(app_py_path, "w", encoding="utf-8") as f:
        f.write("from fastapi import FastAPI\napp = FastAPI()\n")
    
    # Ensure main.py does not exist
    main_py_path = src_dir / "main.py"
    if main_py_path.exists():
        main_py_path.unlink()
    
    # Call _ensure_main_py
    await orchestrator._ensure_main_py(slug)
    
    # Verify main.py was created as re-export shim
    assert main_py_path.exists(), "main.py should be created"
    
    with open(main_py_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert content == 'from app import app  # noqa\n', "main.py should be a re-export shim"


@pytest.mark.asyncio
async def test_ensure_main_py_when_neither_exists(temp_workspace, orchestrator):
    """Test Case 3: Neither main.py nor app.py exists - create full main.py template."""
    slug = "test-project-3"
    project_dir = os.path.join("workspace", "projects", slug)
    src_dir = Path(project_dir) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure neither main.py nor app.py exists
    main_py_path = src_dir / "main.py"
    app_py_path = src_dir / "app.py"
    if main_py_path.exists():
        main_py_path.unlink()
    if app_py_path.exists():
        app_py_path.unlink()
    
    # Call _ensure_main_py
    await orchestrator._ensure_main_py(slug)
    
    # Verify main.py was created with full template
    assert main_py_path.exists(), "main.py should be created"
    
    with open(main_py_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verify template content
    assert "from fastapi import FastAPI" in content, "Should contain FastAPI import"
    assert "app = FastAPI" in content, "Should create FastAPI app"
    assert "@app.get" in content, "Should have root endpoint"
    assert 'return {"message": "API is running"}' in content, "Should have root response"


@pytest.mark.asyncio
async def test_ensure_main_py_creates_src_directory(temp_workspace, orchestrator):
    """Test that _ensure_main_py creates src/ directory if it doesn't exist."""
    slug = "test-project-4"
    project_dir = os.path.join("workspace", "projects", slug)
    src_dir = Path(project_dir) / "src"
    
    # Ensure src directory does not exist
    if src_dir.exists():
        shutil.rmtree(src_dir)
    
    # Call _ensure_main_py
    await orchestrator._ensure_main_py(slug)
    
    # Verify src directory was created
    assert src_dir.exists(), "src/ directory should be created"
    assert src_dir.is_dir(), "src/ should be a directory"
    
    # Verify main.py was created
    main_py_path = src_dir / "main.py"
    assert main_py_path.exists(), "main.py should be created"
