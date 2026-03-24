"""
Bug Condition Exploration Test for main.py and Test Collection Fixes

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

This test MUST FAIL on unfixed code to confirm the bugs exist.
The test verifies two bug conditions:
1. API projects do NOT have src/main.py created after orchestrator.run()
2. Pytest errors with ImportError only log first line, hiding details
3. Multi-line SyntaxError details are truncated

EXPECTED OUTCOME: Test FAILS (this is correct - it proves the bugs exist)
"""
import pytest
from hypothesis import given, strategies as st, settings, Phase
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestrator import Orchestrator
from core.base_agent import Task, AgentResponse
from multi_agent_system.agents.tester_agent import TesterAgent


class TestBugConditionExploration:
    """
    Bug condition exploration tests that MUST FAIL on unfixed code.
    These tests encode the EXPECTED behavior after the fix.
    """

    @pytest.mark.asyncio
    async def test_bug_1_api_project_missing_main_py(self):
        """
        **Property 1: Bug Condition** - Missing main.py Creation
        
        Bug: API projects do NOT have src/main.py created after orchestrator.run()
        Expected (after fix): src/main.py should exist with FastAPI app
        
        This test will FAIL on unfixed code (proving bug exists).
        """
        # Create a temporary workspace for testing
        temp_workspace = tempfile.mkdtemp(prefix="test_workspace_")
        
        try:
            # Create mock agents (minimal setup)
            mock_planner = AsyncMock()
            mock_planner.agent_id = "planner"
            mock_planner.name = "Planner"
            mock_planner._llm = Mock()
            mock_planner._llm.model_key = "test-model"
            
            # Mock planner to return empty plan (we only care about project setup)
            mock_planner._call_llm = AsyncMock(return_value='{"tasks": [], "mode": "flat"}')
            mock_planner.run = AsyncMock(return_value=AgentResponse(
                success=True,
                content={"tasks": [], "mode": "flat"}
            ))
            
            mock_agents = {
                "planner": mock_planner,
            }
            
            orchestrator = Orchestrator(agents=mock_agents)
            
            # Override workspace path to use temp directory
            original_cwd = os.getcwd()
            os.chdir(temp_workspace)
            
            # Test with API-related user goal
            user_goal = "Create a FastAPI todo app with CRUD endpoints"
            
            # Run orchestrator (only project setup phase matters)
            result = await orchestrator.run(user_goal)
            
            # Get the project slug
            project_slug = orchestrator.current_project_slug
            project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
            main_py_path = project_dir / "src" / "main.py"
            
            # EXPECTED BEHAVIOR (after fix): src/main.py should exist
            # CURRENT BEHAVIOR (unfixed): src/main.py does NOT exist
            assert main_py_path.exists(), (
                f"Bug detected: src/main.py does NOT exist at {main_py_path}. "
                f"API project was created but main.py was not generated. "
                f"This confirms the missing main.py bug exists."
            )
            
            # Verify main.py contains FastAPI app
            if main_py_path.exists():
                content = main_py_path.read_text(encoding='utf-8')
                assert "FastAPI" in content, "main.py should contain FastAPI import"
                assert "app = FastAPI" in content, "main.py should initialize FastAPI app"
                assert "@app.get" in content, "main.py should have at least one endpoint"
            
        finally:
            # Cleanup
            os.chdir(original_cwd)
            shutil.rmtree(temp_workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_bug_2_pytest_import_error_truncated(self):
        """
        **Property 2: Bug Condition** - Truncated ImportError Output
        
        Bug: Pytest ImportError only logs first line, hiding import path details
        Expected (after fix): Full error output with stack trace should be logged
        
        This test will FAIL on unfixed code (proving bug exists).
        """
        # Create a temporary project with a test file that has ImportError
        temp_workspace = tempfile.mkdtemp(prefix="test_pytest_")
        
        try:
            project_dir = Path(temp_workspace) / "workspace" / "projects" / "test-project"
            src_dir = project_dir / "src"
            tests_dir = project_dir / "tests"
            
            src_dir.mkdir(parents=True, exist_ok=True)
            tests_dir.mkdir(parents=True, exist_ok=True)
            
            # Create a test file with ImportError (importing non-existent module)
            test_file = tests_dir / "test_import_error.py"
            test_file.write_text("""
import pytest
from src.main import app  # This will cause ImportError

def test_example():
    assert True
""", encoding='utf-8')
            
            # Create TesterAgent and run tests
            tester = TesterAgent()
            
            task = Task(
                task_id="test_task",
                description="Run tests",
                assigned_to="tester",
                context={"project_slug": "test-project"}
            )
            
            # Override cwd to temp workspace
            original_cwd = os.getcwd()
            os.chdir(temp_workspace)
            
            # Capture print output to check what gets logged
            from io import StringIO
            import sys
            captured_output = StringIO()
            original_stdout = sys.stdout
            sys.stdout = captured_output
            
            try:
                response = await tester.act(Mock(), task)
            finally:
                sys.stdout = original_stdout
                os.chdir(original_cwd)
            
            logged_output = captured_output.getvalue()
            
            # EXPECTED BEHAVIOR (after fix): logged output should contain multiple lines
            # showing the full ImportError with module path and details
            # CURRENT BEHAVIOR (unfixed): only first line is logged
            
            # Count lines in logged output that are from [Tester] and contain error details
            # After fix, we should see multiple lines of error context being logged
            tester_lines = [line for line in logged_output.split('\n') if line.strip().startswith('[Tester]')]
            
            # After fix, we should see at least 5 lines of [Tester] output (including error details)
            assert len(tester_lines) >= 5, (
                f"Bug detected: only {len(tester_lines)} [Tester] line(s) logged. "
                f"Expected at least 5 lines showing full ImportError context. "
                f"Logged output:\n{logged_output}\n"
                f"This confirms the truncated error output bug exists."
            )
            
        finally:
            # Cleanup
            shutil.rmtree(temp_workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_bug_3_pytest_syntax_error_truncated(self):
        """
        **Property 3: Bug Condition** - Truncated SyntaxError Output
        
        Bug: Multi-line SyntaxError details are truncated to first line only
        Expected (after fix): Full error with line numbers and context should be logged
        
        This test will FAIL on unfixed code (proving bug exists).
        """
        # Create a temporary project with a test file that has SyntaxError
        temp_workspace = tempfile.mkdtemp(prefix="test_syntax_")
        
        try:
            project_dir = Path(temp_workspace) / "workspace" / "projects" / "test-syntax"
            src_dir = project_dir / "src"
            tests_dir = project_dir / "tests"
            
            src_dir.mkdir(parents=True, exist_ok=True)
            tests_dir.mkdir(parents=True, exist_ok=True)
            
            # Create a test file with SyntaxError
            test_file = tests_dir / "test_syntax_error.py"
            test_file.write_text("""
import pytest

def test_example():
    # This line has a syntax error (missing closing parenthesis)
    result = some_function(arg1, arg2
    assert result == True
""", encoding='utf-8')
            
            # Create TesterAgent and run tests
            tester = TesterAgent()
            
            task = Task(
                task_id="test_task",
                description="Run tests",
                assigned_to="tester",
                context={"project_slug": "test-syntax"}
            )
            
            # Override cwd to temp workspace
            original_cwd = os.getcwd()
            os.chdir(temp_workspace)
            
            # Capture print output to check what gets logged
            from io import StringIO
            import sys
            captured_output = StringIO()
            original_stdout = sys.stdout
            sys.stdout = captured_output
            
            try:
                response = await tester.act(Mock(), task)
            finally:
                sys.stdout = original_stdout
                os.chdir(original_cwd)
            
            logged_output = captured_output.getvalue()
            
            # EXPECTED BEHAVIOR (after fix): logged output should contain multiple lines
            # showing line numbers, error context, and the problematic line
            # CURRENT BEHAVIOR (unfixed): only first line is logged
            
            # Count lines in logged output that are from [Tester] and contain error details
            tester_lines = [line for line in logged_output.split('\n') if line.strip().startswith('[Tester]')]
            
            # After fix, we should see at least 5 lines of [Tester] output showing error context
            assert len(tester_lines) >= 5, (
                f"Bug detected: only {len(tester_lines)} [Tester] line(s) logged. "
                f"Expected at least 5 lines showing full SyntaxError context with line numbers. "
                f"Logged output:\n{logged_output}\n"
                f"This confirms the truncated SyntaxError output bug exists."
            )
            
        finally:
            # Cleanup
            shutil.rmtree(temp_workspace, ignore_errors=True)

    @given(api_keyword=st.sampled_from(["fastapi", "api", "web", "rest", "backend"]))
    @settings(max_examples=5, phases=[Phase.generate])
    @pytest.mark.asyncio
    async def test_bug_1_property_any_api_keyword_missing_main_py(self, api_keyword):
        """
        **Property 1: Bug Condition** - Missing main.py for ANY API keyword
        
        Property-based test: ANY user goal containing API keywords should create main.py
        Bug: main.py is NOT created regardless of keyword
        
        This test will FAIL on unfixed code with counterexamples.
        """
        # Create a temporary workspace for testing
        temp_workspace = tempfile.mkdtemp(prefix=f"test_api_{api_keyword}_")
        
        try:
            # Create mock agents (minimal setup)
            mock_planner = AsyncMock()
            mock_planner.agent_id = "planner"
            mock_planner.name = "Planner"
            mock_planner._llm = Mock()
            mock_planner._llm.model_key = "test-model"
            
            # Mock planner to return empty plan
            mock_planner._call_llm = AsyncMock(return_value='{"tasks": [], "mode": "flat"}')
            mock_planner.run = AsyncMock(return_value=AgentResponse(
                success=True,
                content={"tasks": [], "mode": "flat"}
            ))
            
            mock_agents = {
                "planner": mock_planner,
            }
            
            orchestrator = Orchestrator(agents=mock_agents)
            
            # Override workspace path to use temp directory
            original_cwd = os.getcwd()
            os.chdir(temp_workspace)
            
            # Test with user goal containing the API keyword
            user_goal = f"Create a {api_keyword} application for task management"
            
            # Run orchestrator
            result = await orchestrator.run(user_goal)
            
            # Get the project slug
            project_slug = orchestrator.current_project_slug
            project_dir = Path(temp_workspace) / "workspace" / "projects" / project_slug
            main_py_path = project_dir / "src" / "main.py"
            
            # EXPECTED BEHAVIOR (after fix): src/main.py should exist for ANY API keyword
            assert main_py_path.exists(), (
                f"Bug detected: src/main.py does NOT exist for keyword '{api_keyword}'. "
                f"This confirms the bug exists for this API keyword."
            )
            
        finally:
            # Cleanup
            os.chdir(original_cwd)
            shutil.rmtree(temp_workspace, ignore_errors=True)


# Run the tests and document counterexamples
if __name__ == "__main__":
    print("=" * 70)
    print("BUG CONDITION EXPLORATION TEST")
    print("=" * 70)
    print("\nThese tests are EXPECTED TO FAIL on unfixed code.")
    print("Failures confirm the bugs exist and provide counterexamples.\n")
    
    pytest.main([__file__, "-v", "--tb=short"])
