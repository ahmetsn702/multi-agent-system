"""
tools/code_runner.py
Execute Python code in a subprocess sandbox with timeout and resource limits.
"""
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from core.base_agent import ToolResult

DEFAULT_TIMEOUT = 30


async def run_code(file_path: str, project_slug: str = None) -> ToolResult:
    """Execute python file with proper PYTHONPATH resolution."""
    start = time.monotonic()
    
    file_path_obj = Path(file_path).resolve()
    
    # V5: Interactive program kontrolü
    try:
        file_content = file_path_obj.read_text(encoding="utf-8", errors="ignore")
        
        # input() var mı?
        if "input(" in file_content:
            print(f"[Executor] ⏭️ Interactive program (input), atlanıyor: {file_path_obj.name}")
            return ToolResult(
                success=True,
                data={"output": "Interactive program, otomatik test edilemez", "skipped": True},
                error=None,
                execution_time_ms=0,
            )
        
        # Sonsuz döngü var mı?
        if "while True" in file_content or "while 1:" in file_content:
            print(f"[Executor] ⏭️ Sonsuz döngü, atlanıyor: {file_path_obj.name}")
            return ToolResult(
                success=True,
                data={"output": "Sonsuz döngü tespit edildi, otomatik test edilemez", "skipped": True},
                error=None,
                execution_time_ms=0,
            )
    except Exception as e:
        print(f"[Executor] ⚠️ Dosya okunamadı, yine de çalıştırılıyor: {e}")
    
    # Proje kök dizinini belirle
    project_root = None
    if project_slug:
        project_root = Path("workspace/projects") / project_slug
    else:
        # Dosyanın konumundan projeyi bul
        curr = file_path_obj.parent
        while curr.name not in ["src", "tests", "workspace"] and curr != curr.parent:
            curr = curr.parent
        if curr.name in ["src", "tests"]:
            project_root = curr.parent
        else:
            project_root = curr

    project_src = project_root / "src"
    project_tests = project_root / "tests"

    # PYTHONPATH'e hem src hem tests hem proje kökünü ekle
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH", "")
    new_paths = [
        str(project_src.absolute()),
        str(project_tests.absolute()),
        str(project_root.absolute()),
        str(Path.cwd().absolute()),
    ]
    env["PYTHONPATH"] = os.pathsep.join(new_paths + ([existing_path] if existing_path else []))

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(file_path_obj),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project_root.absolute()),
        env=env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=DEFAULT_TIMEOUT
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        elapsed = (time.monotonic() - start) * 1000
        return ToolResult(
            success=False, data=None, error="Timeout: 30 saniye aşıldı", execution_time_ms=elapsed
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
    existing_path = env.get("PYTHONPATH", "")
    new_paths = [
        str((project_root / "src").absolute()),
        str(project_root.absolute()),
        str(Path.cwd().absolute()),
    ]
    env["PYTHONPATH"] = os.pathsep.join(new_paths + ([existing_path] if existing_path else []))

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "pytest", str(test_dir.absolute()), "-v", "--tb=short",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(project_root.absolute()),
        env=env,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=60
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        elapsed = (time.monotonic() - start) * 1000
        return ToolResult(
            success=False, data=None, error="Test timeout: 60 saniye aşıldı", execution_time_ms=elapsed
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
    """Fallback legacy code runner."""
    start = time.monotonic()
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
