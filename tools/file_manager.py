"""
tools/file_manager.py
Sandboxed file operations — all paths must be within ./workspace/.
"""
import os
import shutil
from typing import Optional

from core.base_agent import ToolResult

import asyncio
from pathlib import Path

WORKSPACE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "workspace")
)

_file_locks: dict = {}

def _safe_path(relative_path: str) -> Optional[str]:
    """Resolve path and verify it stays inside WORKSPACE_DIR."""
    abs_path = os.path.abspath(os.path.join(WORKSPACE_DIR, relative_path))
    if not abs_path.startswith(WORKSPACE_DIR):
        return None  # Path traversal attempt
    return abs_path


def _ensure_workspace():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)


async def read_file(path: str) -> ToolResult:
    """Read a file from the workspace."""
    _ensure_workspace()
    safe = _safe_path(path)
    if not safe:
        return ToolResult(success=False, data=None, error="Path traversal not allowed.")
    try:
        with open(safe, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResult(success=True, data={"path": path, "content": content, "size": len(content)})
    except FileNotFoundError:
        return ToolResult(success=False, data=None, error=f"File not found: {path}")
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


async def write_file(path: str, content: str, mode: str = "w") -> ToolResult:
    """Write or append to a file in the workspace using async locks."""
    _ensure_workspace()
    
    target = Path(path).resolve()
    workspace = Path(WORKSPACE_DIR).resolve()
    
    if not str(target).startswith(str(workspace)):
        # Fallback to _safe_path logic for relative paths
        safe = _safe_path(path)
        if not safe:
            return ToolResult(success=False, data=None, error=f"Güvenlik ihlali: {path} workspace dışında!")
        target = Path(safe)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return ToolResult(success=False, data=None, error=f"Klasör oluşturulamadı: {e}")

    lock_key = str(target)
    if lock_key not in _file_locks:
        _file_locks[lock_key] = asyncio.Lock()

    async with _file_locks[lock_key]:
        try:
            with open(str(target), mode, encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, data={"path": str(target), "size_bytes": target.stat().st_size})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

def ensure_project_structure(slug: str) -> dict:
    """Proje klasör yapısını garantile — her görev başında çağır"""
    base = Path(WORKSPACE_DIR) / "projects" / slug
    folders = [
        base / "src",
        base / "tests",
        base / "docs",
    ]
    created = []
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
        gitkeep = folder / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        created.append(str(folder))

    return {"success": True, "created": created, "project_root": str(base)}


async def append_file(path: str, content: str) -> ToolResult:
    """Append content to a file."""
    return await write_file(path, content, mode="a")


async def list_dir(path: str = "") -> ToolResult:
    """List contents of a directory in the workspace."""
    _ensure_workspace()
    safe = _safe_path(path) if path else WORKSPACE_DIR
    if not safe:
        return ToolResult(success=False, data=None, error="Path traversal not allowed.")
    try:
        entries = []
        for name in os.listdir(safe):
            full = os.path.join(safe, name)
            entries.append({
                "name": name,
                "type": "directory" if os.path.isdir(full) else "file",
                "size": os.path.getsize(full) if os.path.isfile(full) else None,
            })
        return ToolResult(success=True, data={"path": path or ".", "entries": entries})
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


async def create_dir(path: str) -> ToolResult:
    """Create a directory in the workspace."""
    _ensure_workspace()
    safe = _safe_path(path)
    if not safe:
        return ToolResult(success=False, data=None, error="Path traversal not allowed.")
    try:
        os.makedirs(safe, exist_ok=True)
        return ToolResult(success=True, data={"path": path})
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


async def delete_file(path: str, confirm: bool = False) -> ToolResult:
    """Delete a file or directory (requires confirm=True)."""
    if not confirm:
        return ToolResult(
            success=False,
            data=None,
            error="Deletion requires confirm=True for safety.",
        )
    _ensure_workspace()
    safe = _safe_path(path)
    if not safe:
        return ToolResult(success=False, data=None, error="Path traversal not allowed.")
    try:
        if os.path.isdir(safe):
            shutil.rmtree(safe)
        else:
            os.remove(safe)
        return ToolResult(success=True, data={"deleted": path})
    except FileNotFoundError:
        return ToolResult(success=False, data=None, error=f"Not found: {path}")
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def get_workspace_path() -> str:
    """Return the absolute workspace path."""
    _ensure_workspace()
    return WORKSPACE_DIR
