"""
core/message_bus.py
Async pub/sub message bus for inter-agent communication.
Priority queue based, logs all messages to messages.jsonl.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

MESSAGES_LOG = os.path.join(os.path.dirname(__file__), "..", "messages.jsonl")


class MessageType(str, Enum):
    TASK = "TASK"
    RESULT = "RESULT"
    QUERY = "QUERY"
    FEEDBACK = "FEEDBACK"
    BROADCAST = "BROADCAST"
    HANDOFF = "HANDOFF"


class Priority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class Message:
    """A message passed between agents."""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,  # agent_id or 'broadcast'
        msg_type: MessageType,
        content: Any,
        priority: Priority = Priority.NORMAL,
        correlation_id: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.type = msg_type
        self.content = content
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.priority = priority
        self.correlation_id = correlation_id or str(uuid.uuid4())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "type": self.type.value,
            "content": self.content if isinstance(self.content, (str, int, float, bool, list, dict)) else str(self.content),
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
        }

    def __lt__(self, other: "Message") -> bool:
        """For priority queue ordering (higher priority = processed first)."""
        return self.priority.value > other.priority.value


class MessageBus:
    """
    Central async pub/sub message bus.
    Each agent subscribes with a handler; messages are dispatched asynchronously.
    """

    def __init__(self):
        self._queues: dict[str, asyncio.PriorityQueue] = {}
        self._subscribers: dict[str, Callable] = {}
        self._dead_letter: list[dict] = []
        self._running = False
        self._log_path = os.path.abspath(MESSAGES_LOG)
        self._history: list[dict] = []

    def subscribe(self, agent_id: str, handler: Callable):
        """Register an agent to receive messages."""
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.PriorityQueue()
        self._subscribers[agent_id] = handler

    async def publish(self, message: Message):
        """Send a message to a specific agent or broadcast to all."""
        msg_dict = message.to_dict()
        self._history.append(msg_dict)
        await self._log_message(msg_dict)

        if message.to_agent == "broadcast":
            for agent_id, queue in self._queues.items():
                if agent_id != message.from_agent:
                    # Priority queue stores (negated priority, message) so highest priority goes first
                    await queue.put((-message.priority.value, message))
        else:
            if message.to_agent in self._queues:
                await self._queues[message.to_agent].put((-message.priority.value, message))
            else:
                # Dead letter
                self._dead_letter.append(msg_dict)
                print(f"[MessageBus] Dead letter: {message.to_agent} not registered. Message: {message.id}")

    async def receive(self, agent_id: str, timeout: float = 30.0) -> Optional[Message]:
        """Wait for and return the next message for agent_id."""
        if agent_id not in self._queues:
            return None
        try:
            _, message = await asyncio.wait_for(
                self._queues[agent_id].get(), timeout=timeout
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def send_and_wait(
        self,
        message: Message,
        sender_id: str,
        timeout: float = 60.0,
    ) -> Optional[Message]:
        """Send a message and wait for a correlated response."""
        await self.publish(message)
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            response = await self.receive(sender_id, timeout=2.0)
            if response and response.correlation_id == message.correlation_id:
                return response
        return None

    async def _log_message(self, msg_dict: dict):
        """Append message to messages.jsonl log."""
        try:
            async with asyncio.timeout(2.0):
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(msg_dict) + "\n")
        except Exception:
            pass  # logging should never crash the system

    def get_history(self) -> list[dict]:
        return list(self._history)

    def get_dead_letters(self) -> list[dict]:
        return list(self._dead_letter)

    def get_queue_sizes(self) -> dict[str, int]:
        return {agent_id: q.qsize() for agent_id, q in self._queues.items()}


# Singleton bus instance
bus = MessageBus()
