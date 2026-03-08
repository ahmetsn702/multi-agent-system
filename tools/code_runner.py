"""
tools/code_runner.py
Execute Python code in a subprocess sandbox with timeout and resource limits.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from core.base_agent import ToolResult

DEFAULT_TIMEOUT = 30


def _build_pythonpath(paths: list[Path], env: dict) -> str:
    existing_path = env.get("PYTHONPATH", "")
    resolved = [str(p.absolute()) for p in paths]
    return os.pathsep.join(resolved + ([existing_path] if existing_path else []))


async def _run_subprocess(
    args: list[str],
    cwd: str,
    env: dict,
    timeout: int,
) -> tuple[int, str, str, bool]:
    """
    Run subprocess in a worker thread.
    Using subprocess.run avoids Windows sandbox failures seen with
    asyncio.create_subprocess_exec named pipes.
    """
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return 124, stdout, stderr, True


async def run_code(file_path: str, project_slug: str = None) -> ToolResult:
    """Execute python file with proper PYTHONPATH resolution."""
    start = time.monotonic()
    file_path_obj = Path(file_path).resolve()

    if project_slug:
        project_root = Path("workspace/projects") / project_slug
    else:
        curr = file_path_obj.parent
        while curr.name not in ["src", "tests", "workspace"] and curr != curr.parent:
            curr = curr.parent
        project_root = curr.parent if curr.name in ["src", "tests"] else curr

    env = os.environ.copy()
    env["PYTHONPATH"] = _build_pythonpath(
        [project_root / "src", project_root / "tests", project_root, Path.cwd()],
        env,
    )

    return_code, stdout, stderr, timed_out = await _run_subprocess(
        [sys.executable, str(file_path_obj)],
        cwd=str(project_root.absolute()),
        env=env,
        timeout=DEFAULT_TIMEOUT,
    )

    elapsed = (time.monotonic() - start) * 1000
    if timed_out:
        return ToolResult(
            success=False,
            data=None,
            error="Timeout: 30 saniye aşıldı",
            execution_time_ms=elapsed,
        )

    return ToolResult(
        success=(return_code == 0),
        data={
            "output": stdout,
            "errors": stderr,
            "return_code": return_code,
            "execution_time_ms": elapsed,
        },
        error=stderr if return_code != 0 else None,
        execution_time_ms=elapsed,
    )


async def run_tests(project_slug: str) -> ToolResult:
    """Run pytest dynamically for the project."""
    start = time.monotonic()
    project_root = Path("workspace/projects") / project_slug
    test_dir = project_root / "tests"

    if not test_dir.exists():
        return ToolResult(success=False, data=None, error="tests/ klasörü bulunamadı")

    env = os.environ.copy()
    env["PYTHONPATH"] = _build_pythonpath(
        [project_root / "src", project_root, Path.cwd()],
        env,
    )

    return_code, stdout, stderr, timed_out = await _run_subprocess(
        [sys.executable, "-m", "pytest", str(test_dir.absolute()), "-v", "--tb=short"],
        cwd=str(project_root.absolute()),
        env=env,
        timeout=60,
    )

    elapsed = (time.monotonic() - start) * 1000
    if timed_out:
        return ToolResult(
            success=False,
            data=None,
            error="Test timeout: 60 saniye aşıldı",
            execution_time_ms=elapsed,
        )

    return ToolResult(
        success=(return_code == 0),
        data={
            "output": stdout,
            "errors": stderr,
            "return_code": return_code,
            "execution_time_ms": elapsed,
        },
        error=stderr if return_code != 0 else None,
        execution_time_ms=elapsed,
    )


async def run_python_code(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
    stdin_data: Optional[str] = None,
) -> ToolResult:
    """Run inline Python code by writing to a temporary file first."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="agent_code_", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(code)
        tmp.close()
        return await run_code(tmp.name)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
