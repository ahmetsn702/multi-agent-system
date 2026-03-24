"""
Integration test to verify _ensure_main_py() is called after orchestrator execution.

**Validates: Requirements 2.1, 2.2**

This test verifies that the orchestrator calls _ensure_main_py() at the right points:
- After _react_loop() completes in run() method
- After phase execution loop completes in _run_phases() method
"""
import os
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from core.orchestrator import Orchestrator
from core.base_agent import Task


@pytest.mark.asyncio
async def test_ensure_main_py_called_in_run_method():
    """
    Test that _ensure_main_py() is called after _react_loop() completes in run() method.
    
    This is a code inspection test that verifies the method call is in the right place.
    """
    # Read the orchestrator.py file
    orchestrator_path = Path(__file__).parent.parent / "core" / "orchestrator.py"
    with open(orchestrator_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verify that _ensure_main_py is called after _react_loop in run() method
    # Look for the pattern: _react_loop followed by _ensure_main_py before _aggregate_results
    
    # Find the run() method
    run_method_start = content.find("async def run(self, user_goal: str) -> dict:")
    assert run_method_start != -1, "Could not find run() method"
    
    # Find _react_loop call in run() method
    react_loop_pos = content.find("await self._react_loop(tasks, user_goal)", run_method_start)
    assert react_loop_pos != -1, "Could not find _react_loop call in run() method"
    
    # Find _ensure_main_py call after _react_loop
    ensure_main_py_pos = content.find("await self._ensure_main_py(slug)", react_loop_pos)
    assert ensure_main_py_pos != -1, "Could not find _ensure_main_py call after _react_loop"
    
    # Find _aggregate_results call
    aggregate_pos = content.find("await self._aggregate_results(final_results, user_goal)", react_loop_pos)
    assert aggregate_pos != -1, "Could not find _aggregate_results call"
    
    # Verify _ensure_main_py is called BEFORE _aggregate_results
    assert ensure_main_py_pos < aggregate_pos, (
        "_ensure_main_py should be called before _aggregate_results"
    )
    
    print("✓ Verified: _ensure_main_py() is called after _react_loop() in run() method")


@pytest.mark.asyncio
async def test_ensure_main_py_called_in_run_phases_method():
    """
    Test that _ensure_main_py() is called after phase execution loop completes in _run_phases() method.
    
    This is a code inspection test that verifies the method call is in the right place.
    """
    # Read the orchestrator.py file
    orchestrator_path = Path(__file__).parent.parent / "core" / "orchestrator.py"
    with open(orchestrator_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verify that _ensure_main_py is called after phase loop in _run_phases() method
    
    # Find the _run_phases() method
    run_phases_start = content.find("async def _run_phases(")
    assert run_phases_start != -1, "Could not find _run_phases() method"
    
    # Find the end of the phase loop (marked by the comment "# Aggregate final output")
    aggregate_comment_pos = content.find("# Aggregate final output", run_phases_start)
    assert aggregate_comment_pos != -1, "Could not find '# Aggregate final output' comment"
    
    # Find _ensure_main_py call before aggregate comment
    # Search backwards from aggregate comment to find _ensure_main_py
    search_region = content[run_phases_start:aggregate_comment_pos]
    ensure_main_py_in_region = "await self._ensure_main_py(slug)" in search_region
    
    assert ensure_main_py_in_region, (
        "_ensure_main_py should be called before '# Aggregate final output' in _run_phases()"
    )
    
    # Find _aggregate_results call
    aggregate_pos = content.find("await self._aggregate_results(all_results, user_goal)", run_phases_start)
    assert aggregate_pos != -1, "Could not find _aggregate_results call in _run_phases()"
    
    # Find _ensure_main_py position
    ensure_main_py_pos = content.find("await self._ensure_main_py(slug)", run_phases_start)
    
    # Verify _ensure_main_py is called BEFORE _aggregate_results
    assert ensure_main_py_pos < aggregate_pos, (
        "_ensure_main_py should be called before _aggregate_results in _run_phases()"
    )
    
    print("✓ Verified: _ensure_main_py() is called after phase loop in _run_phases() method")


@pytest.mark.asyncio
async def test_ensure_main_py_functional_test():
    """
    Functional test to verify _ensure_main_py() creates main.py correctly.
    """
    temp_workspace = tempfile.mkdtemp(prefix="test_ensure_main_py_")
    
    try:
        original_cwd = os.getcwd()
        os.chdir(temp_workspace)
        
        # Create a minimal orchestrator
        orch = Orchestrator(agents={})
        
        # Test Case 1: Neither main.py nor app.py exists
        slug1 = "test-neither-exists"
        await orch._ensure_main_py(slug1)
        
        main_py_path1 = Path(temp_workspace) / "workspace" / "projects" / slug1 / "src" / "main.py"
        assert main_py_path1.exists(), "main.py should be created when neither file exists"
        content1 = main_py_path1.read_text(encoding='utf-8')
        assert "from fastapi import FastAPI" in content1, "Should contain FastAPI template"
        
        # Test Case 2: app.py exists but main.py doesn't
        slug2 = "test-app-exists"
        project_dir2 = Path(temp_workspace) / "workspace" / "projects" / slug2 / "src"
        project_dir2.mkdir(parents=True, exist_ok=True)
        
        app_py_path2 = project_dir2 / "app.py"
        app_py_path2.write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding='utf-8')
        
        await orch._ensure_main_py(slug2)
        
        main_py_path2 = project_dir2 / "main.py"
        assert main_py_path2.exists(), "main.py should be created as re-export shim"
        content2 = main_py_path2.read_text(encoding='utf-8')
        assert "from app import app" in content2, "Should contain re-export from app"
        
        # Test Case 3: main.py already exists (preservation)
        slug3 = "test-main-exists"
        project_dir3 = Path(temp_workspace) / "workspace" / "projects" / slug3 / "src"
        project_dir3.mkdir(parents=True, exist_ok=True)
        
        main_py_path3 = project_dir3 / "main.py"
        original_content = "# Original main.py\nprint('hello')\n"
        main_py_path3.write_text(original_content, encoding='utf-8')
        
        await orch._ensure_main_py(slug3)
        
        content3 = main_py_path3.read_text(encoding='utf-8')
        assert content3 == original_content, "main.py should be preserved when it already exists"
        
        os.chdir(original_cwd)
        print("✓ All functional tests passed")
        
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_workspace, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
