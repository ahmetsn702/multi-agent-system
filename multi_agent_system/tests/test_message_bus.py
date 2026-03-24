"""
tests/test_message_bus.py
Unit tests for the MessageBus: publish, receive, priority, dead letter queue.
"""
import asyncio
import pytest

from core.message_bus import Message, MessageBus, MessageType, Priority


@pytest.fixture
def fresh_bus():
    """Create a fresh MessageBus for each test."""
    return MessageBus()


@pytest.mark.asyncio
async def test_publish_and_receive(fresh_bus):
    """Test basic publish and receive."""
    fresh_bus.subscribe("agent_a", lambda m: None)
    fresh_bus.subscribe("agent_b", lambda m: None)

    msg = Message(
        from_agent="agent_a",
        to_agent="agent_b",
        msg_type=MessageType.TASK,
        content="Test task",
    )
    await fresh_bus.publish(msg)

    received = await fresh_bus.receive("agent_b", timeout=1.0)
    assert received is not None
    assert received.content == "Test task"
    assert received.type == MessageType.TASK


@pytest.mark.asyncio
async def test_priority_ordering(fresh_bus):
    """High-priority messages should be received before low-priority."""
    fresh_bus.subscribe("agent_x", lambda m: None)

    low_msg = Message("a", "agent_x", MessageType.TASK, "low", Priority.LOW)
    high_msg = Message("a", "agent_x", MessageType.TASK, "high", Priority.CRITICAL)

    await fresh_bus.publish(low_msg)
    await fresh_bus.publish(high_msg)

    first = await fresh_bus.receive("agent_x", timeout=1.0)
    assert first is not None
    assert first.content == "high"


@pytest.mark.asyncio
async def test_broadcast(fresh_bus):
    """Broadcast should reach all agents except sender."""
    fresh_bus.subscribe("sender", lambda m: None)
    fresh_bus.subscribe("receiver_1", lambda m: None)
    fresh_bus.subscribe("receiver_2", lambda m: None)

    msg = Message("sender", "broadcast", MessageType.BROADCAST, "Hello all")
    await fresh_bus.publish(msg)

    r1 = await fresh_bus.receive("receiver_1", timeout=1.0)
    r2 = await fresh_bus.receive("receiver_2", timeout=1.0)
    sender_msg = await fresh_bus.receive("sender", timeout=0.2)

    assert r1 is not None
    assert r2 is not None
    assert sender_msg is None  # sender shouldn't receive own broadcast


@pytest.mark.asyncio
async def test_dead_letter_queue(fresh_bus):
    """Message to non-existent agent should go to dead letter queue."""
    msg = Message("a", "nonexistent_agent", MessageType.TASK, "lost message")
    await fresh_bus.publish(msg)

    dead_letters = fresh_bus.get_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0]["to_agent"] == "nonexistent_agent"


@pytest.mark.asyncio
async def test_receive_timeout(fresh_bus):
    """Receive should return None after timeout if no messages."""
    fresh_bus.subscribe("empty_agent", lambda m: None)
    result = await fresh_bus.receive("empty_agent", timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_message_history(fresh_bus):
    """All messages should be recorded in history."""
    fresh_bus.subscribe("a", lambda m: None)
    fresh_bus.subscribe("b", lambda m: None)

    for i in range(3):
        await fresh_bus.publish(Message("a", "b", MessageType.QUERY, f"msg_{i}"))

    history = fresh_bus.get_history()
    assert len(history) == 3


@pytest.mark.asyncio
async def test_correlation_id(fresh_bus):
    """Messages should have unique correlation IDs."""
    msg1 = Message("a", "b", MessageType.TASK, "task1")
    msg2 = Message("a", "b", MessageType.TASK, "task2")
    assert msg1.correlation_id != msg2.correlation_id


def test_message_types_exist():
    """All required message types must be defined."""
    types = {m.value for m in MessageType}
    required = {"TASK", "RESULT", "QUERY", "FEEDBACK", "BROADCAST", "HANDOFF"}
    assert required.issubset(types)


def test_priority_values():
    """Priority values must follow correct ordering."""
    assert Priority.LOW < Priority.NORMAL < Priority.HIGH < Priority.CRITICAL
