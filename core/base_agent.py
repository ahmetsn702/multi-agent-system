"""
core/base_agent.py
Abstract BaseAgent class that all agents inherit from.
Provides think/act/communicate/use_tool interface, memory, and status tracking.
"""
import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from core.llm_client import LLMClient
from core.memory import memory_manager
from core.message_bus import Message, MessageBus, MessageType, Priority


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    THINKING = "THINKING"
    ACTING = "ACTING"
    WAITING = "WAITING"
    ERROR = "ERROR"


class Task:
    """Represents a task assigned to an agent."""

    def __init__(
        self,
        task_id: str,
        description: str,
        assigned_to: str,
        dependencies: Optional[list[str]] = None,
        context: Optional[dict] = None,
        priority: Priority = Priority.NORMAL,
    ):
        self.task_id = task_id
        self.description = description
        self.assigned_to = assigned_to
        self.dependencies = dependencies or []
        self.context = context or {}
        self.priority = priority
        self.created_at = datetime.now(timezone.utc).isoformat()


class ThoughtProcess:
    """The result of an agent thinking about a task."""

    def __init__(
        self,
        reasoning: str,
        plan: list[str],
        tool_calls: list[dict],
        confidence: float = 0.8,
    ):
        self.reasoning = reasoning
        self.plan = plan
        self.tool_calls = tool_calls
        self.confidence = confidence


class AgentResponse:
    """The result of an agent acting on a thought process."""

    def __init__(
        self,
        content: Any,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[dict] = None,
        self_reflection: Optional[str] = None,
    ):
        self.content = content
        self.success = success
        self.error = error
        self.metadata = metadata or {}
        self.self_reflection = self_reflection
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
            "self_reflection": self.self_reflection,
            "timestamp": self.timestamp,
        }


class ToolResult:
    """Result of a tool invocation."""

    def __init__(
        self,
        success: bool,
        data: Any,
        error: Optional[str] = None,
        execution_time_ms: float = 0.0,
    ):
        self.success = success
        self.data = data
        self.error = error
        self.execution_time_ms = execution_time_ms

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all agents in the multi-agent system.
    Each agent has a unique identity, capabilities, memory, and status.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        description: str,
        capabilities: list[str],
        bus: Optional[MessageBus] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.description = description
        self.capabilities = capabilities

        self.status = AgentStatus.IDLE
        self._llm = LLMClient(agent_id=agent_id)
        self._bus = bus
        self._memory = memory_manager
        self._tools: dict[str, Any] = {}

        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0

        # Register with bus
        if self._bus:
            self._bus.subscribe(self.agent_id, self._handle_message)

    def set_bus(self, bus: MessageBus):
        """Attach message bus after construction if needed."""
        self._bus = bus
        bus.subscribe(self.agent_id, self._handle_message)

    @property
    def short_term_memory(self):
        return self._memory.get_short_term(self.agent_id)

    async def _handle_message(self, message: Message):
        """Default message handler — subclasses can override."""
        pass

    @abstractmethod
    async def think(self, task: Task) -> ThoughtProcess:
        """
        Reason about the given task and produce a plan.
        Must be implemented by each agent subclass.
        """
        pass

    @abstractmethod
    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """
        Execute the plan from think() and return a response.
        Must be implemented by each agent subclass.
        """
        pass

    async def run(self, task: Task) -> AgentResponse:
        """
        Full think-act cycle with self-reflection.
        This is the main entry point for assigning a task to an agent.
        """
        self.status = AgentStatus.THINKING
        self._memory.add_to_short_term(
            self.agent_id, "user", f"Task: {task.description}", {"task_id": task.task_id}
        )

        try:
            thought = await self.think(task)
            self.status = AgentStatus.ACTING
            response = await self.act(thought, task)

            # Self-reflection
            reflection = await self._reflect(task, response)
            response.self_reflection = reflection

            self._memory.add_to_short_term(
                self.agent_id,
                "assistant",
                str(response.content),
                {"task_id": task.task_id, "success": response.success},
            )

            self.status = AgentStatus.IDLE
            return response

        except Exception as e:
            self.status = AgentStatus.ERROR
            return AgentResponse(
                content=None,
                success=False,
                error=str(e),
            )

    async def _reflect(self, task: Task, response: AgentResponse) -> str:
        """Post-task self-reflection: evaluate own output quality."""
        try:
            reflection_prompt = (
                f"Task: {task.description}\n\n"
                f"My response: {str(response.content)[:500]}\n\n"
                "In 1-2 sentences: Was this response complete and accurate? "
                "What could I improve?"
            )
            reflection = await self._call_llm(
                messages=[{"role": "user", "content": reflection_prompt}],
                system_prompt="You are self-reflecting on your own output. Be honest and concise.",
                temperature=0.3,
                max_tokens=150,
            )
            return reflection
        except Exception:
            return "Reflection unavailable."

    async def communicate(
        self,
        target_agent_id: str,
        content: Any,
        msg_type: MessageType = MessageType.QUERY,
        priority: Priority = Priority.NORMAL,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Send a message to another agent via the message bus."""
        if not self._bus:
            raise RuntimeError(f"Agent {self.agent_id} has no message bus attached.")
        message = Message(
            from_agent=self.agent_id,
            to_agent=target_agent_id,
            msg_type=msg_type,
            content=content,
            priority=priority,
            correlation_id=correlation_id,
        )
        await self._bus.publish(message)

    async def use_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """Invoke a registered tool by name."""
        if tool_name not in self._tools:
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool '{tool_name}' not available for agent '{self.agent_id}'",
            )
        import time
        start = time.monotonic()
        try:
            self.status = AgentStatus.ACTING
            result = await self._tools[tool_name](**kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000
            if isinstance(result, ToolResult):
                result.execution_time_ms = elapsed_ms
                return result
            return ToolResult(success=True, data=result, execution_time_ms=elapsed_ms)
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            return ToolResult(success=False, data=None, error=str(e), execution_time_ms=elapsed_ms)
        finally:
            self.status = AgentStatus.IDLE

    def register_tool(self, name: str, func):
        """Register a callable tool for this agent."""
        self._tools[name] = func

    async def _call_llm(
        self,
        messages: list[dict],
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        """Helper to call LLM and parse JSON if possible."""
        result = await self._llm.complete(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )
        
        from core.llm_client import token_tracker
        usage = token_tracker.get(self.agent_id)
        self.total_input_tokens = usage.get("prompt_tokens", 0)
        self.total_output_tokens = usage.get("completion_tokens", 0)
        self.total_cost_usd = usage.get("total_cost", 0.0)
        
        return result

    def _parse_json_response(self, text: str) -> dict:
        """Attempt to parse JSON from LLM response, stripping markdown fences."""
        import re
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = text[start:end+1]
            else:
                json_str = text
                
        try:
            return json.loads(json_str)
        except Exception:
            return {"raw": text}

    def get_status_dict(self) -> dict:
        """Return agent status as a dict (for UI display)."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "memory_size": len(self.short_term_memory),
        }
