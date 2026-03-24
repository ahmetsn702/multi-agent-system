"""
tests/test_orchestrator_integration.py
Integration tests for critical orchestrator flows with mocked LLM responses.
"""
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agents.critic_agent import CriticAgent
from agents.planner_agent import PlannerAgent
from core.base_agent import AgentResponse
from core.memory import memory_manager
from core.orchestrator import Orchestrator


@pytest.fixture
def mock_llm():
    """Mock LLMClient.complete and return per-agent scripted responses."""
    scripted = {"responses": {}, "calls": defaultdict(int)}

    async def _side_effect(self, *args, **kwargs):
        agent_id = getattr(self, "agent_id", "system")
        idx = scripted["calls"][agent_id]
        scripted["calls"][agent_id] += 1
        response_def = scripted["responses"].get(agent_id, "{}")

        if callable(response_def):
            return response_def(idx, *args, **kwargs)
        if isinstance(response_def, list):
            return response_def[min(idx, len(response_def) - 1)]
        return response_def

    with patch("core.llm_client.LLMClient.complete", autospec=True, side_effect=_side_effect):
        yield scripted


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    """Isolate workspace/session artifacts per test using tmp_path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(memory_manager, "get_last_sessions", lambda limit=3: [])

    def _save_session(session_data: dict, slug: str = "default"):
        project_dir = tmp_path / "workspace" / "projects" / slug
        project_dir.mkdir(parents=True, exist_ok=True)
        idx = len(list(project_dir.glob("session_*.json"))) + 1
        path = project_dir / f"session_{idx:03d}.json"
        path.write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(memory_manager, "save_session", _save_session)
    return tmp_path


class DummyCoderAgent:
    def __init__(self, events: list):
        self.name = "Dummy Coder"
        self.capabilities = ["code_generation"]
        self._llm = SimpleNamespace(model_key="dummy/coder")
        self.events = events
        self.run_count = 0
        self.revision_descriptions = []

    async def run(self, task):
        self.run_count += 1
        self.events.append(("coder", task.task_id))
        if "Revision required:" in task.description:
            self.revision_descriptions.append(task.description)
        return AgentResponse(
            content={
                "code": f"print('run-{self.run_count}')",
                "filename": "main.py",
                "saved_files": [f"projects/{task.context.get('project_slug', 'default')}/src/main.py"],
            },
            success=True,
        )


class DummyExecutorAgent:
    def __init__(self, events: list):
        self.name = "Dummy Executor"
        self.capabilities = ["shell_execution"]
        self._llm = SimpleNamespace(model_key="dummy/executor")
        self.events = events

    async def run(self, task):
        self.events.append(("executor", task.task_id))
        return AgentResponse(content={"done": task.task_id}, success=True)


def _flat_plan_json():
    return json.dumps(
        {
            "mode": "flat",
            "analysis": "flat test plan",
            "tasks": [
                {
                    "task_id": "t1",
                    "description": "Generate code",
                    "assigned_to": "coder",
                    "dependencies": [],
                    "priority": "high",
                    "expected_output": "code",
                },
                {
                    "task_id": "t2",
                    "description": "Execute result",
                    "assigned_to": "executor",
                    "dependencies": ["t1"],
                    "priority": "normal",
                    "expected_output": "run output",
                },
            ],
            "execution_order": ["t1", "t2"],
            "parallel_groups": [["t1"], ["t2"]],
        }
    )


def _phased_plan_json():
    return json.dumps(
        {
            "mode": "phased",
            "analysis": "phased test plan",
            "phases": [
                {
                    "phase_id": "phase_1",
                    "name": "Phase 1",
                    "tasks": [
                        {
                            "task_id": "p1_t1",
                            "description": "Phase1 code task A",
                            "assigned_to": "coder",
                            "dependencies": [],
                            "priority": "high",
                            "expected_output": "a",
                        },
                        {
                            "task_id": "p1_t2",
                            "description": "Phase1 execute task B",
                            "assigned_to": "executor",
                            "dependencies": ["p1_t1"],
                            "priority": "normal",
                            "expected_output": "b",
                        },
                    ],
                },
                {
                    "phase_id": "phase_2",
                    "name": "Phase 2",
                    "depends_on_phase": "phase_1",
                    "tasks": [
                        {
                            "task_id": "p2_t1",
                            "description": "Phase2 code task C",
                            "assigned_to": "coder",
                            "dependencies": [],
                            "priority": "high",
                            "expected_output": "c",
                        },
                        {
                            "task_id": "p2_t2",
                            "description": "Phase2 execute task D",
                            "assigned_to": "executor",
                            "dependencies": ["p2_t1"],
                            "priority": "normal",
                            "expected_output": "d",
                        },
                    ],
                },
            ],
        }
    )


def _critic_high_json():
    return json.dumps(
        {
            "scores": {
                "correctness": 9,
                "quality": 8,
                "test_coverage": 8,
                "architecture": 8,
                "security": 9,
            },
            "average": 8.4,
            "approved": True,
            "issues": [],
            "suggestions": [],
            "summary": "good",
        }
    )


def _critic_low_json(use_key: str = "suggestions"):
    payload = {
        "scores": {
            "correctness": 5,
            "quality": 5,
            "test_coverage": 4,
            "architecture": 5,
            "security": 5,
        },
        "average": 4.8,
        "approved": False,
        "issues": ["edge case missing"],
        "summary": "needs revision",
    }
    payload[use_key] = ["optimize naming"]
    return json.dumps(payload)


@pytest.mark.asyncio
async def test_flat_plan_happy_path(mock_llm, isolated_workspace):
    """Flat plan should complete all tasks, aggregate output, and persist a session file."""
    events = []
    planner = PlannerAgent()
    critic = CriticAgent()
    coder = DummyCoderAgent(events)
    executor = DummyExecutorAgent(events)

    mock_llm["responses"]["planner"] = _flat_plan_json()
    mock_llm["responses"]["critic"] = _critic_high_json()
    mock_llm["responses"]["orchestrator"] = "Final aggregated output"

    orch = Orchestrator(
        agents={
            "planner": planner,
            "critic": critic,
            "coder": coder,
            "executor": executor,
        }
    )

    result = await orch.run("Build a simple script")
    assert result["success"] is True
    assert "Final aggregated output" in result["output"]
    assert ("coder", "t1") in events
    assert ("executor", "t2") in events

    slug = "build-a-simple-script"
    session_files = list((isolated_workspace / "workspace" / "projects" / slug).glob("session_*.json"))
    assert session_files, "Expected session_*.json to be created"


@pytest.mark.asyncio
async def test_phased_plan_execution(mock_llm, isolated_workspace):
    """Phased plan should execute phase 1 fully before phase 2 starts."""
    events = []
    planner = PlannerAgent()
    critic = CriticAgent()
    coder = DummyCoderAgent(events)
    executor = DummyExecutorAgent(events)

    mock_llm["responses"]["planner"] = _phased_plan_json()
    mock_llm["responses"]["critic"] = _critic_high_json()
    mock_llm["responses"]["orchestrator"] = "Phased aggregate"

    orch = Orchestrator(
        agents={
            "planner": planner,
            "critic": critic,
            "coder": coder,
            "executor": executor,
        }
    )

    result = await orch.run("Build phased project")
    assert result["success"] is True

    order = [task_id for _, task_id in events]
    phase1_last = max(order.index("p1_t1"), order.index("p1_t2"))
    phase2_first = min(order.index("p2_t1"), order.index("p2_t2"))
    assert phase2_first > phase1_last


@pytest.mark.asyncio
async def test_critic_revision_loop(mock_llm, isolated_workspace):
    """Low critic score should trigger one revision, then stop after high score."""
    events = []
    planner = PlannerAgent()
    critic = CriticAgent()
    coder = DummyCoderAgent(events)
    executor = DummyExecutorAgent(events)

    mock_llm["responses"]["planner"] = _flat_plan_json()
    mock_llm["responses"]["critic"] = [_critic_low_json("suggestions"), _critic_high_json()]
    mock_llm["responses"]["orchestrator"] = "Revised aggregate"

    orch = Orchestrator(
        agents={
            "planner": planner,
            "critic": critic,
            "coder": coder,
            "executor": executor,
        }
    )

    result = await orch.run("Build with review")
    assert result["success"] is True
    assert coder.run_count >= 2, "Coder should be re-invoked after critic requests revision"
    assert any("Revision required:" in d for d in coder.revision_descriptions)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_key", ["improvements", "suggestions"])
async def test_critic_schema_compatibility(mock_llm, isolated_workspace, legacy_key):
    """Critic schema compatibility should keep revision instructions non-empty for both keys."""
    events = []
    planner = PlannerAgent()
    critic = CriticAgent()
    coder = DummyCoderAgent(events)
    executor = DummyExecutorAgent(events)

    mock_llm["responses"]["planner"] = _flat_plan_json()
    mock_llm["responses"]["critic"] = [_critic_low_json(legacy_key), _critic_high_json()]
    mock_llm["responses"]["orchestrator"] = "Compat aggregate"

    orch = Orchestrator(
        agents={
            "planner": planner,
            "critic": critic,
            "coder": coder,
            "executor": executor,
        }
    )

    result = await orch.run(f"Compat test {legacy_key}")
    assert result["success"] is True
    assert coder.revision_descriptions, "Expected at least one revision instruction"
    revision_text = coder.revision_descriptions[0]
    assert "Suggestions:" in revision_text
    assert "optimize naming" in revision_text


@pytest.mark.asyncio
async def test_task_dependency_ordering(mock_llm, isolated_workspace):
    """A dependent task must not execute before its prerequisite task completes."""
    events = []
    planner = PlannerAgent()
    critic = CriticAgent()
    coder = DummyCoderAgent(events)
    executor = DummyExecutorAgent(events)

    dependency_plan = json.dumps(
        {
            "mode": "flat",
            "analysis": "dependency plan",
            "tasks": [
                {
                    "task_id": "A",
                    "description": "First task",
                    "assigned_to": "executor",
                    "dependencies": [],
                    "priority": "normal",
                    "expected_output": "A done",
                },
                {
                    "task_id": "B",
                    "description": "Second task",
                    "assigned_to": "executor",
                    "dependencies": ["A"],
                    "priority": "normal",
                    "expected_output": "B done",
                },
            ],
            "execution_order": ["A", "B"],
            "parallel_groups": [["A"], ["B"]],
        }
    )

    mock_llm["responses"]["planner"] = dependency_plan
    mock_llm["responses"]["critic"] = _critic_high_json()
    mock_llm["responses"]["orchestrator"] = "Dependency aggregate"

    orch = Orchestrator(
        agents={
            "planner": planner,
            "critic": critic,
            "coder": coder,
            "executor": executor,
        }
    )

    result = await orch.run("Dependency ordering check")
    assert result["success"] is True
    ordered = [task_id for agent, task_id in events if agent == "executor"]
    assert ordered.index("A") < ordered.index("B")
