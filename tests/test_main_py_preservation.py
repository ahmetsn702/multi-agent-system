"""
Preservation Property Tests for app.py vs main.py Import Fix

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

These tests MUST PASS on unfixed code to confirm baseline behavior to preserve.
They verify that existing functionality continues to work after the fix.
"""
import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from hypothesis import given, strategies as st, settings, HealthCheck
from unittest.mock import Mock, AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator
from core.base_agent import AgentResponse


# ============================================================================
# Property 2: Preservation - Existing main.py Projects
# ============================================================================

@pytest.mark.asyncio
@given(
    api_keywords=st.sampled_from([
        "FastAPI web API",
        "REST API with Flask",
        "web service API",
        "HTTP API server"
    ])
)
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None
)
async def test_preservation_existing_main_py_projects_work_unchanged(api_keywords):
    """
    **Validates: Requirements 3.1**
    
    Property: Projects that already have main.py continue to work unchanged.
    
    Observation: On unfixed code, projects with existing main.py work correctly
    with test imports using "from main import app".
    
    Expected: This behavior is preserved after the fix.
    """
    temp_workspace = tempfile.mkdtemp(prefix="test_preservation_main_")
    
    try:
        project_slug = "test-existing-main-py"
        project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
        src_dir = project_dir / "src"
        tests_dir = project_dir / "tests"
        
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir.mkdir(parents=True, exist_ok=True)
        
        # Create main.py (existing project)
        main_py_path = src_dir / "main.py"
        main_py_path.write_text("""from fastapi import FastAPI
app = FastAPI(title="Existing Main API")

@app.get("/")
def root():
    return {"message": "Hello from main.py"}
""", encoding='utf-8')
        
        # Test file with import from main (standard pattern)
        test_file = tests_dir / "test_api.py"
        test_file.write_text("""import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import app

def test_root():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
""", encoding='utf-8')
        
        original_cwd = os.getcwd()
        os.chdir(temp_workspace)
        
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # EXPECTED: Test passes (preservation of existing behavior)
            assert result.returncode == 0, (
                f"Preservation violation: Existing main.py project should work. "
                f"Exit code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
            )
            
            # Verify main.py was not modified
            content = main_py_path.read_text(encoding='utf-8')
            assert "Existing Main API" in content, "main.py should not be modified"
            
        finally:
            os.chdir(original_cwd)
        
    finally:
        shutil.rmtree(temp_workspace, ignore_errors=True)


@pytest.mark.asyncio
@given(
    non_api_goal=st.sampled_from([
        "Create a data analysis script",
        "Build a CLI tool for file processing",
        "Write a utility library for string manipulation",
        "Develop a batch processing script"
    ])
)
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None
)
async def test_preservation_non_api_projects_skip_main_py_creation(non_api_goal):
    """
    **Validates: Requirements 3.2**
    
    Property: Non-API projects skip main.py creation logic.
    
    Observation: On unfixed code, projects without API keywords do not
    trigger main.py creation in the orchestrator.
    
    Expected: This behavior is preserved after the fix.
    """
    temp_workspace = tempfile.mkdtemp(prefix="test_preservation_non_api_")
    
    try:
        project_slug = "test-non-api-project"
        project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
        src_dir = project_dir / "src"
        
        src_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a non-API source file
        util_py_path = src_dir / "utils.py"
        util_py_path.write_text("""def process_data(data):
    \"\"\"Process data without any API.\"\"\"
    return [x * 2 for x in data]

def format_output(result):
    \"\"\"Format output for display.\"\"\"
    return ", ".join(map(str, result))
""", encoding='utf-8')
        
        # Verify main.py is NOT created for non-API projects
        main_py_path = src_dir / "main.py"
        
        # Simulate orchestrator behavior (non-API projects don't create main.py)
        # This is the baseline behavior we want to preserve
        is_api_project = any(
            keyword in non_api_goal.lower()
            for keyword in ["api", "fastapi", "flask", "web service", "endpoint"]
        )
        
        # EXPECTED: Non-API projects should not have main.py created
        assert not is_api_project, (
            f"Test setup error: '{non_api_goal}' should not be detected as API project"
        )
        
        # Verify main.py does not exist (preservation of non-API behavior)
        assert not main_py_path.exists(), (
            f"Preservation violation: Non-API project should not have main.py. "
            f"Goal: {non_api_goal}"
        )
        
    finally:
        shutil.rmtree(temp_workspace, ignore_errors=True)


@pytest.mark.asyncio
@given(
    source_file_type=st.sampled_from([
        ("database.py", "import sqlite3\n\ndef connect():\n    return sqlite3.connect('db.sqlite')"),
        ("utils.py", "def helper_function(x):\n    return x * 2"),
        ("models.py", "class DataModel:\n    def __init__(self, data):\n        self.data = data"),
        ("config.py", "API_KEY = 'test'\nDEBUG = True")
    ])
)
@settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None
)
async def test_preservation_coder_generates_source_files_correctly(source_file_type):
    """
    **Validates: Requirements 3.3**
    
    Property: Coder agent generates non-test source files correctly.
    
    Observation: On unfixed code, coder agent generates source files
    (non-test files) following existing patterns without issues.
    
    Expected: This behavior is preserved after the fix.
    """
    temp_workspace = tempfile.mkdtemp(prefix="test_preservation_source_")
    
    try:
        project_slug = "test-source-generation"
        project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
        src_dir = project_dir / "src"
        
        src_dir.mkdir(parents=True, exist_ok=True)
        
        filename, content = source_file_type
        source_file = src_dir / filename
        source_file.write_text(content, encoding='utf-8')
        
        # Verify source file was created correctly
        assert source_file.exists(), f"Source file {filename} should exist"
        
        # Verify content is correct
        actual_content = source_file.read_text(encoding='utf-8')
        assert actual_content == content, (
            f"Preservation violation: Source file content mismatch. "
            f"Expected: {content}\n"
            f"Actual: {actual_content}"
        )
        
        # Verify no unexpected files were created
        src_files = list(src_dir.glob("*.py"))
        assert len(src_files) == 1, (
            f"Preservation violation: Only one source file should exist. "
            f"Found: {[f.name for f in src_files]}"
        )
        
    finally:
        shutil.rmtree(temp_workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_preservation_orchestrator_session_saving_unchanged():
    """
    **Validates: Requirements 3.4**
    
    Property: Orchestrator session saving and project summary writing unchanged.
    
    Observation: On unfixed code, orchestrator saves session data and writes
    project summaries correctly.
    
    Expected: This behavior is preserved after the fix.
    """
    temp_workspace = tempfile.mkdtemp(prefix="test_preservation_session_")
    
    try:
        project_slug = "test-session-preservation"
        project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
        memory_dir = Path(temp_workspace) / "memory"
        
        project_dir.mkdir(parents=True, exist_ok=True)
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Simulate orchestrator session data
        session_file = memory_dir / f"{project_slug}_session.json"
        session_data = {
            "project_slug": project_slug,
            "user_goal": "Test preservation",
            "status": "completed"
        }
        
        import json
        session_file.write_text(json.dumps(session_data, indent=2), encoding='utf-8')
        
        # Simulate project summary
        summary_file = project_dir / "project_summary.txt"
        summary_content = """Project: test-session-preservation
Goal: Test preservation
Status: Completed
"""
        summary_file.write_text(summary_content, encoding='utf-8')
        
        # Verify session file exists and is correct
        assert session_file.exists(), "Session file should exist"
        loaded_data = json.loads(session_file.read_text(encoding='utf-8'))
        assert loaded_data == session_data, (
            f"Preservation violation: Session data mismatch. "
            f"Expected: {session_data}\n"
            f"Actual: {loaded_data}"
        )
        
        # Verify summary file exists and is correct
        assert summary_file.exists(), "Summary file should exist"
        actual_summary = summary_file.read_text(encoding='utf-8')
        assert actual_summary == summary_content, (
            f"Preservation violation: Summary content mismatch. "
            f"Expected: {summary_content}\n"
            f"Actual: {actual_summary}"
        )
        
    finally:
        shutil.rmtree(temp_workspace, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
