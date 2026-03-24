"""
tools/shell_executor.py
Safely execute shell commands (read-only / safe list by default).
"""
import asyncio
import logging
import os
import shlex
import subprocess
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

logger = logging.getLogger(__name__)


def _is_safe(command: str) -> bool:
    command = (command or "").strip()
    if not command:
        logger.warning("Blocked command (empty command).")
        return False

    try:
        tokens = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        logger.warning(f"Blocked command (parse error): {command[:80]}")
        return False

    if not tokens:
        logger.warning("Blocked command (no executable token).")
        return False

    executable = os.path.basename(tokens[0]).lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]

    if executable not in ALLOWED_PREFIXES:
        logger.warning(f"Blocked command (not in allowlist): {command[:80]}")
        return False

    # shell=False mode intentionally blocks shell chaining/pipe semantics by default.
    # If pipe/redirection support is required, implement a dedicated audited wrapper
    # for tightly-scoped command templates rather than enabling shell=True globally.
    if any(meta in command for meta in ("|", "&&", "||", ";", ">", "<")):
        logger.warning(f"Blocked command (shell metacharacter): {command[:80]}")
        return False

    lower = command.lower()
    for blocked in BLOCKED_PATTERNS:
        if blocked in lower:
            logger.warning(f"Blocked command (pattern match): {command[:80]}")
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
        cmd_list = shlex.split(command, posix=(os.name != "nt"))
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd_list,
            shell=False,
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=timeout,
        )

        elapsed = (time.monotonic() - start) * 1000
        stdout = proc.stdout
        stderr = proc.stderr
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
    except subprocess.TimeoutExpired:
        elapsed = (time.monotonic() - start) * 1000
        return ToolResult(
            success=False,
            data=None,
            error=f"Command timed out after {timeout}s",
            execution_time_ms=elapsed,
        )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return ToolResult(success=False, data=None, error=str(e), execution_time_ms=elapsed)
