"""
Bug Condition Exploration Test for app.py vs main.py Import Fix

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

This test MUST FAIL on unfixed code to confirm the bug exists.
"""
import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator
from core.base_agent import AgentResponse


@pytest.mark.asyncio
async def test_bug_app_py_without_main_py_causes_import_error():
    """
    Bug: When project has src/app.py but no src/main.py, test files
    import from main causing ImportError.
    
    Expected (after fix): main.py is created as re-export shim.
    This test will FAIL on unfixed code (proving bug exists).
    """
    temp_workspace = tempfile.mkdtemp(prefix="test_app_py_bug_")
    
    try:
        project_slug = "test-app-py-only"
        project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
        src_dir = project_dir / "src"
        tests_dir = project_dir / "tests"
        
        src_dir.mkdir(parents=True, exist_ok=True)
        tests_dir.mkdir(parents=True, exist_ok=True)
        
        # Create app.py (NOT main.py)
        app_py_path = src_dir / "app.py"
        app_py_path.write_text("""from fastapi import FastAPI
app = FastAPI(title="Test API")

@app.get("/")
def root():
    return {"message": "Hello from app.py"}
""", encoding='utf-8')
        
        # Simulate test file with hardcoded import from main
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
""", encoding='utf-8')
        
        original_cwd = os.getcwd()
        os.chdir(temp_workspace)
        
        try:
            # Call the orchestrator's _ensure_main_py() method to create the shim
            orchestrator = Orchestrator(agents={})
            await orchestrator._ensure_main_py(project_slug)
            
            # Verify main.py was created as shim
            main_py_path = src_dir / "main.py"
            assert main_py_path.exists(), "main.py should be created as re-export shim"
            content = main_py_path.read_text(encoding='utf-8')
            assert "from app import app" in content, "main.py should re-export from app"
            
            # Now run the test - it should pass
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # EXPECTED (after fix): Test passes
            assert result.returncode == 0, (
                f"Test failed after creating main.py shim. "
                f"Exit code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
            )
            
        finally:
            os.chdir(original_cwd)
        
    finally:
        shutil.rmtree(temp_workspace, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
