"""
Bug Condition Exploration Test for Critic Timeout and Cost Fixes

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

This test MUST FAIL on unfixed code to confirm the bugs exist.
The test verifies four bug conditions:
1. critic.route_by_score(6.5, 0) returns "CODER_REVISE" instead of "EXECUTOR"
2. orchestrator._enrich_task_context adds unbounded all_previous_results to revision tasks
3. task timeout is fixed at 180s regardless of revision count
4. multiple coder tasks targeting same domain infer identical file paths

EXPECTED OUTCOME: Test FAILS (this is correct - it proves the bugs exist)
"""
import pytest
from hypothesis import given, strategies as st, settings, Phase
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from multi_agent_system.agents.critic_agent import CriticAgent
from core.orchestrator import Orchestrator
from core.base_agent import Task, AgentResponse


class TestBugConditionExploration:
    """
    Bug condition exploration tests that MUST FAIL on unfixed code.
    These tests encode the EXPECTED behavior after the fix.
    """

    def test_bug_1_critic_threshold_6_5_routes_to_coder_revise(self):
        """
        **Property 1: Bug Condition** - Critic Threshold
        
        Bug: Score 6.5 routes to CODER_REVISE instead of EXECUTOR
        Expected (after fix): Score 6.5 should route to EXECUTOR
        
        This test will FAIL on unfixed code (proving bug exists).
        """
        critic = CriticAgent()
        
        # Test the specific failing case from the bug description
        routing = critic.route_by_score(6.5, 0)
        
        # EXPECTED BEHAVIOR (after fix): 6.5 should route to EXECUTOR
        # CURRENT BEHAVIOR (unfixed): 6.5 routes to CODER_REVISE
        assert routing == "EXECUTOR", (
            f"Bug detected: score 6.5 routes to {routing} instead of EXECUTOR. "
            f"This confirms the critic threshold bug exists."
        )

    @given(score=st.floats(min_value=6.0, max_value=6.9))
    @settings(max_examples=10, phases=[Phase.generate, Phase.target])
    def test_bug_1_critic_threshold_range_6_0_to_6_9(self, score):
        """
        **Property 1: Bug Condition** - Critic Threshold Range
        
        Property-based test: ANY score in [6.0, 6.9] should route to EXECUTOR
        Bug: Scores in this range route to CODER_REVISE
        
        This test will FAIL on unfixed code with counterexamples.
        """
        critic = CriticAgent()
        routing = critic.route_by_score(score, 0)
        
        # EXPECTED BEHAVIOR (after fix): scores >= 6.0 should route to EXECUTOR
        assert routing == "EXECUTOR", (
            f"Bug detected: score {score:.2f} routes to {routing} instead of EXECUTOR"
        )

    @pytest.mark.asyncio
    async def test_bug_2_revision_context_unbounded_growth(self):
        """
        **Property 2: Bug Condition** - Revision Context Growth
        
        Bug: Revision tasks receive unbounded all_previous_results
        Expected (after fix): Revision context should be capped at 3000 tokens
        
        This test will FAIL on unfixed code (proving bug exists).
        """
        # Create mock agents
        mock_agents = {
            "coder": Mock(agent_id="coder", name="Coder"),
            "executor": Mock(agent_id="executor", name="Executor"),
        }
        
        orchestrator = Orchestrator(agents=mock_agents)
        
        # Create a revision task (task_id contains "_rev")
        revision_task = Task(
            task_id="t1_rev1",
            description="Revise code based on critic feedback",
            assigned_to="coder",
            context={}
        )
        
        # Create large previous results (simulating 8000 tokens of context)
        large_results = [
            {
                "task_id": f"prev_task_{i}",
                "agent": "coder",
                "description": f"Previous task {i}",
                "result": {"code": "x" * 1000},  # ~1000 chars per result
                "success": True
            }
            for i in range(8)  # 8 results * 1000 chars = 8000 chars
        ]
        
        # Enrich the revision task context
        await orchestrator._enrich_task_context(revision_task, large_results)
        
        # Check if all_previous_results was added (bug behavior)
        context_str = str(revision_task.context)
        context_size = len(context_str)
        
        # EXPECTED BEHAVIOR (after fix): context should be <= 3000 tokens (~12000 chars)
        # CURRENT BEHAVIOR (unfixed): context includes all_previous_results, exceeding limit
        assert context_size <= 12000, (
            f"Bug detected: revision task context is {context_size} chars (>12000), "
            f"indicating unbounded all_previous_results was added. "
            f"Expected: context should be capped at ~3000 tokens (12000 chars max)."
        )

    @pytest.mark.asyncio
    async def test_bug_3_task_timeout_fixed_at_180s(self):
        """
        **Property 3: Bug Condition** - Task Timeout
        
        Bug: Task timeout is fixed at 180s regardless of revision count
        Expected (after fix): Timeout should be 360s or reset on revision
        
        This test verifies the timeout has been increased to 360s.
        """
        # Import the actual timeout constant from the orchestrator
        import sys
        from pathlib import Path
        
        # Add multi_agent_system to path if needed
        multi_agent_path = Path(__file__).parent.parent / "multi_agent_system"
        if str(multi_agent_path) not in sys.path:
            sys.path.insert(0, str(multi_agent_path))
        
        try:
            from core.orchestrator import TASK_TIMEOUT_SECONDS
        except ImportError:
            # Fallback: read the constant directly from the file
            orchestrator_path = Path(__file__).parent.parent / "multi_agent_system" / "core" / "orchestrator.py"
            content = orchestrator_path.read_text(encoding='utf-8')
            import re
            match = re.search(r'TASK_TIMEOUT_SECONDS\s*=\s*(\d+)', content)
            if match:
                TASK_TIMEOUT_SECONDS = int(match.group(1))
            else:
                pytest.fail("Could not find TASK_TIMEOUT_SECONDS in orchestrator.py")
        
        EXPECTED_TIMEOUT = 360  # seconds (after fix)
        
        # EXPECTED BEHAVIOR (after fix): timeout should be 360s
        # This test will PASS after the fix is applied
        assert TASK_TIMEOUT_SECONDS >= EXPECTED_TIMEOUT, (
            f"Bug detected: task timeout is {TASK_TIMEOUT_SECONDS}s, "
            f"expected {EXPECTED_TIMEOUT}s for revision tasks. "
            f"This confirms the timeout bug exists."
        )

    @pytest.mark.asyncio
    async def test_bug_4_file_routing_conflicts(self):
        """
        **Property 4: Bug Condition** - File Routing Conflicts
        
        Bug: Multiple coder tasks targeting same domain infer identical file paths
        Expected (after fix): Each task should have unique file routing hints
        
        This test will FAIL on unfixed code (proving bug exists).
        """
        # Create mock agents
        mock_planner = AsyncMock()
        mock_planner.agent_id = "planner"
        mock_planner.name = "Planner"
        
        # Create two tasks targeting the same domain ("todos")
        task1 = Task(
            task_id="t1",
            description="Create todos CRUD endpoints",
            assigned_to="coder",
            context={}
        )
        
        task2 = Task(
            task_id="t2",
            description="Add todos validation logic",
            assigned_to="coder",
            context={}
        )
        
        # Mock planner to return a plan with these two tasks
        mock_plan = {
            "tasks": [task1, task2]
        }
        mock_planner._call_llm = AsyncMock(return_value='{"tasks": []}')
        
        mock_agents = {
            "planner": mock_planner,
            "coder": Mock(agent_id="coder", name="Coder"),
        }
        
        orchestrator = Orchestrator(agents=mock_agents)
        
        # Simulate the plan being processed with routing hint injection
        orchestrator._inject_file_routing_hints(mock_plan)
        
        # Check if file_routing_hint is present in context after injection
        has_routing_hint_t1 = "file_routing_hint" in task1.context
        has_routing_hint_t2 = "file_routing_hint" in task2.context
        
        # EXPECTED BEHAVIOR (after fix): tasks should have unique file_routing_hint
        # CURRENT BEHAVIOR (unfixed): no file_routing_hint, both tasks write to same file
        assert has_routing_hint_t1 and has_routing_hint_t2, (
            f"Bug detected: tasks targeting same domain lack file_routing_hint. "
            f"Task1 has hint: {has_routing_hint_t1}, Task2 has hint: {has_routing_hint_t2}. "
            f"This confirms the file routing conflict bug exists."
        )
        
        # Verify hints are unique
        hint1 = task1.context.get("file_routing_hint", "")
        hint2 = task2.context.get("file_routing_hint", "")
        assert hint1 != hint2, (
            f"Bug detected: routing hints are not unique. "
            f"Task1 hint: {hint1}, Task2 hint: {hint2}"
        )


# Run the tests and document counterexamples
if __name__ == "__main__":
    print("=" * 70)
    print("BUG CONDITION EXPLORATION TEST")
    print("=" * 70)
    print("\nThese tests are EXPECTED TO FAIL on unfixed code.")
    print("Failures confirm the bugs exist and provide counterexamples.\n")
    
    pytest.main([__file__, "-v", "--tb=short"])
