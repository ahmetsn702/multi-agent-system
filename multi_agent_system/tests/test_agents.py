"""
tests/test_agents.py
Unit tests for BaseAgent behavior and individual agent logic.
Tests run with mock LLM responses to avoid actual API calls.
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.base_agent import AgentStatus, BaseAgent, Task, ThoughtProcess, ToolResult
from core.message_bus import MessageBus, MessageType


# --- Mock concrete agent for testing BaseAgent ---

class MockAgent(BaseAgent):
    """Minimal concrete agent for testing BaseAgent abstract methods."""

    def __init__(self):
        super().__init__(
            agent_id="mock_agent",
            name="Mock Agent",
            role="Testing",
            description="For unit tests",
            capabilities=["testing", "mocking"],
        )

    async def think(self, task: Task) -> ThoughtProcess:
        return ThoughtProcess(
            reasoning="Mock reasoning",
            plan=["step 1", "step 2"],
            tool_calls=[],
            confidence=0.9,
        )

    async def act(self, thought: ThoughtProcess, task: Task):
        from core.base_agent import AgentResponse
        return AgentResponse(content="Mock result", success=True)


# --- BaseAgent Tests ---

def test_agent_initialization():
    """Agent should initialize with correct defaults."""
    agent = MockAgent()
    assert agent.agent_id == "mock_agent"
    assert agent.status == AgentStatus.IDLE
    assert "testing" in agent.capabilities
    assert len(agent.short_term_memory) == 0


def test_register_tool():
    """Tools can be registered and are callable."""
    agent = MockAgent()
    mock_tool = AsyncMock(return_value=ToolResult(success=True, data="tool_output"))
    agent.register_tool("my_tool", mock_tool)
    assert "my_tool" in agent._tools


@pytest.mark.asyncio
async def test_use_tool_success():
    """Tool invocation returns ToolResult on success."""
    agent = MockAgent()
    async def good_tool(**kwargs):
        return ToolResult(success=True, data={"result": "ok"})
    agent.register_tool("good_tool", good_tool)
    result = await agent.use_tool("good_tool", param="value")
    assert result.success
    assert result.data["result"] == "ok"


@pytest.mark.asyncio
async def test_use_tool_not_found():
    """Calling non-existent tool returns failure ToolResult."""
    agent = MockAgent()
    result = await agent.use_tool("nonexistent_tool")
    assert not result.success
    assert "not available" in result.error


@pytest.mark.asyncio
async def test_agent_run_cycle():
    """Agent run() should go through THINKING -> ACTING -> IDLE states."""
    agent = MockAgent()
    status_history = []

    original_think = agent.think
    async def patched_think(task):
        status_history.append(agent.status)  # Should be THINKING
        return await original_think(task)

    agent.think = patched_think

    with patch.object(agent._llm, 'complete', new=AsyncMock(return_value="Looks good.")):
        task = Task("t1", "Test task", "mock_agent")
        response = await agent.run(task)

    assert response.success
    assert response.content == "Mock result"
    assert agent.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_agent_communicate():
    """Agent should send messages via message bus."""
    bus = MessageBus()
    agent = MockAgent()
    agent.set_bus(bus)
    bus.subscribe("other_agent", lambda m: None)

    await agent.communicate(
        target_agent_id="other_agent",
        content="Hello!",
        msg_type=MessageType.QUERY,
    )

    received = await bus.receive("other_agent", timeout=1.0)
    assert received is not None
    assert received.content == "Hello!"
    assert received.from_agent == "mock_agent"


def test_status_dict():
    """get_status_dict should return all required fields."""
    agent = MockAgent()
    status = agent.get_status_dict()
    required_keys = {"agent_id", "name", "role", "status", "capabilities", "memory_size"}
    assert required_keys.issubset(status.keys())


@pytest.mark.asyncio
async def test_short_term_memory_limit():
    """Short-term memory should not exceed 20 messages."""
    from core.memory import ShortTermMemory
    mem = ShortTermMemory("test_agent", max_size=20)
    for i in range(30):
        mem.add("user", f"Message {i}")
    assert len(mem) == 20
    # Most recent should be last 20
    messages = mem.get_messages()
    assert messages[-1]["content"] == "Message 29"


# --- Memory System Tests ---

@pytest.mark.asyncio
async def test_long_term_memory_store_retrieve(tmp_path):
    """Long-term memory should store and retrieve values."""
    from core.memory import LongTermMemory
    import core.memory as memory_module

    old_path = memory_module.SHARED_MEMORY_PATH
    memory_module.SHARED_MEMORY_PATH = str(tmp_path / "test_memory.json")

    try:
        mem = LongTermMemory()
        mem._path = str(tmp_path / "test_memory.json")
        await mem.store("my_key", {"data": 42}, agent_id="test")
        value = await mem.retrieve("my_key")
        assert value == {"data": 42}
    finally:
        memory_module.SHARED_MEMORY_PATH = old_path


@pytest.mark.asyncio
async def test_long_term_memory_missing_key(tmp_path):
    """Retrieving non-existent key returns None."""
    from core.memory import LongTermMemory
    mem = LongTermMemory()
    mem._path = str(tmp_path / "test_memory2.json")
    result = await mem.retrieve("nonexistent_key")
    assert result is None


# --- Tool Tests ---

@pytest.mark.asyncio
async def test_file_manager_write_read(tmp_path):
    """FileManager write then read should return the same content."""
    import tools.file_manager as fm
    old_workspace = fm.WORKSPACE_DIR
    fm.WORKSPACE_DIR = str(tmp_path)
    try:
        result = await fm.write_file("test.txt", "Hello, World!")
        assert result.success

        read_result = await fm.read_file("test.txt")
        assert read_result.success
        assert read_result.data["content"] == "Hello, World!"
    finally:
        fm.WORKSPACE_DIR = old_workspace


@pytest.mark.asyncio
async def test_file_manager_path_traversal(tmp_path):
    """Path traversal should be blocked."""
    import tools.file_manager as fm
    old_workspace = fm.WORKSPACE_DIR
    fm.WORKSPACE_DIR = str(tmp_path)
    try:
        result = await fm.read_file("../../etc/passwd")
        assert not result.success
        assert "traversal" in result.error.lower()
    finally:
        fm.WORKSPACE_DIR = old_workspace


@pytest.mark.asyncio
async def test_code_runner_simple():
    """Code runner should execute simple Python and return output."""
    from tools.code_runner import run_python_code
    result = await run_python_code('print("hello from sandbox")')
    assert result.success
    assert "hello from sandbox" in result.data["output"]


@pytest.mark.asyncio
async def test_code_runner_error():
    """Code runner should capture errors correctly."""
    from tools.code_runner import run_python_code
    result = await run_python_code("raise ValueError('test error')")
    assert not result.success
    assert result.data["return_code"] != 0
