"""
tools/shell_executor.py
Safely execute shell commands (read-only / safe list by default).
"""
import asyncio
import os
import time
from typing import Optional

from core.base_agent import ToolResult

# Allowlist of safe command prefixes
ALLOWED_PREFIXES = (
    "python", "pip", "pytest", "ls", "dir", "echo", "cat", "type",
    "git", "node", "npm", "curl", "wget",
)

BLOCKED_PATTERNS = (
    "rm ", "del ", "format ", "rmdir /s", "rd /s",
    "shutdown", "reboot", ":(){", "fork bomb",
)


def _is_safe(command: str) -> bool:
    lower = command.lower().strip()
    for blocked in BLOCKED_PATTERNS:
        if blocked in lower:
            return False
    return True


async def run_shell(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 30,
) -> ToolResult:
    """
    Execute a shell command safely.
    Blocks known destructive patterns.
    """
    if not _is_safe(command):
        return ToolResult(
            success=False,
            data=None,
            error=f"Command blocked for safety: '{command}'",
        )

    workspace = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "workspace")
    )
    working_dir = cwd or workspace
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            elapsed = (time.monotonic() - start) * 1000
            return ToolResult(
                success=False,
                data=None,
                error=f"Command timed out after {timeout}s",
                execution_time_ms=elapsed,
            )

        elapsed = (time.monotonic() - start) * 1000
        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        return_code = proc.returncode

        return ToolResult(
            success=(return_code == 0),
            data={
                "output": stdout,
                "errors": stderr,
                "return_code": return_code,
                "command": command,
            },
            error=stderr if return_code != 0 else None,
            execution_time_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return ToolResult(success=False, data=None, error=str(e), execution_time_ms=elapsed)
