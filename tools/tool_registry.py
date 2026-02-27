"""
tools/tool_registry.py
Central registry for all tools using @register_tool decorator.
Tools register their name, description, and parameter schema.
Agents discover tools via tool_registry.list_tools().
"""
import functools
import inspect
import time
from typing import Any, Callable, Optional

from core.base_agent import ToolResult


class ToolInfo:
    """Metadata about a registered tool."""

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters_schema: dict,
        async_support: bool = True,
    ):
        self.name = name
        self.func = func
        self.description = description
        self.parameters_schema = parameters_schema
        self.async_support = async_support

    def to_openai_format(self) -> dict:
        """Return tool definition in OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


class ToolRegistry:
    """Global registry of all available tools."""

    def __init__(self):
        self._tools: dict[str, ToolInfo] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters_schema: Optional[dict] = None,
        async_support: bool = True,
    ):
        """Decorator factory — registers the decorated function as a tool."""
        def decorator(func: Callable) -> Callable:
            schema = parameters_schema or {
                "type": "object",
                "properties": {},
                "required": [],
            }
            info = ToolInfo(
                name=name,
                func=func,
                description=description,
                parameters_schema=schema,
                async_support=async_support,
            )
            self._tools[name] = info

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                start = time.monotonic()
                try:
                    if inspect.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                    elapsed = (time.monotonic() - start) * 1000
                    if isinstance(result, ToolResult):
                        result.execution_time_ms = elapsed
                        return result
                    return ToolResult(success=True, data=result, execution_time_ms=elapsed)
                except Exception as e:
                    elapsed = (time.monotonic() - start) * 1000
                    return ToolResult(success=False, data=None, error=str(e), execution_time_ms=elapsed)

            return wrapper

        return decorator

    def list_tools(self) -> list[ToolInfo]:
        """Return all registered tools."""
        return list(self._tools.values())

    def list_tools_openai(self) -> list[dict]:
        """Return all tools in OpenAI function-calling format."""
        return [t.to_openai_format() for t in self._tools.values()]

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        return self._tools.get(name)

    def get_callable(self, name: str) -> Optional[Callable]:
        info = self._tools.get(name)
        return info.func if info else None

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


# Global registry instance
tool_registry = ToolRegistry()

# Convenience alias for the decorator
def register_tool(name: str, description: str, parameters_schema: Optional[dict] = None, async_support: bool = True):
    return tool_registry.register(name, description, parameters_schema, async_support)
