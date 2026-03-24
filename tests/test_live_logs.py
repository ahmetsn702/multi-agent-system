"""
tests/test_live_logs.py
Unit tests for live log queue behavior without starting SSE endpoint.
"""
import asyncio

import pytest

from core.base_agent import LOG_QUEUE, emit_log_event


def _drain_log_queue() -> None:
    """Clear any stale events so tests stay isolated."""
    while not LOG_QUEUE.empty():
        try:
            LOG_QUEUE.get_nowait()
        except asyncio.QueueEmpty:
            break


@pytest.mark.asyncio
async def test_emit_log_event_puts_item_in_log_queue():
    """emit_log_event should enqueue one structured event."""
    _drain_log_queue()

    await emit_log_event(
        agent_name="coder",
        stage="act",
        message="kod yaziliyor...",
        tokens_used=142,
    )

    event = await asyncio.wait_for(LOG_QUEUE.get(), timeout=3)

    assert event.agent_name == "coder"
    assert event.stage == "act"
    assert event.message == "kod yaziliyor..."
    assert event.tokens_used == 142
    assert isinstance(event.timestamp, str)

