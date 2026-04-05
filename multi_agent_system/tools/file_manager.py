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

_file_locks: dict[str, asyncio.Lock] = {}
_MAX_LOCKS = 200


def _get_lock(key: str) -> asyncio.Lock:
    """Get or create a file lock, cleaning up stale unlocked entries when too many."""
    if key not in _file_locks:
        if len(_file_locks) > _MAX_LOCKS:
            stale = [k for k, v in _file_locks.items() if not v.locked()]
            for k in stale:
                del _file_locks[k]
        _file_locks[key] = asyncio.Lock()
    return _file_locks[key]

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
            print(f"[FileManager] ❌ Güvenlik ihlali: {path} workspace dışında!")
            return ToolResult(success=False, data=None, error=f"Güvenlik ihlali: {path} workspace dışında!")
        target = Path(safe)

    lock = _get_lock(str(target))

    async with lock:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"[FileManager] ❌ Klasör oluşturulamadı: {target.parent} — {e}")
            return ToolResult(success=False, data=None, error=f"Klasör oluşturulamadı: {e}")

        try:
            with open(str(target), mode, encoding="utf-8") as f:
                f.write(content)
            print(f"[FileManager] ✅ Kaydedildi: {target} ({len(content)} karakter)")
            return ToolResult(success=True, data={"path": str(target), "size_bytes": target.stat().st_size})
        except Exception as e:
            print(f"[FileManager] ❌ HATA: {target} — {e}")
            raise

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


def bulk_edit(project_path: str, operation: str, **kwargs) -> dict:
    """
    Proje genelinde toplu degisiklik yap.

    Operasyonlar:
    - replace_all: Projede bir metni her yerde degistir
    - add_encoding: Tum dosyalara # -*- coding: utf-8 -*- ekle
    - fix_imports: Goreli importlari duzelt

    Args:
        project_path: Proje kok dizini
        operation: Yapilacak operasyon
        **kwargs: Operasyona ozgu parametreler (old_text, new_text vb.)

    Returns:
        Sonuc dict'i
    """
    import re
    from pathlib import Path

    root = Path(project_path)
    src_dir = root / "src"
    results = []

    if not src_dir.exists():
        return {"success": False, "error": "src/ klasoru bulunamadi"}

    py_files = [f for f in src_dir.glob("*.py") if f.name != ".gitkeep"]

    if operation == "replace_all":
        old = kwargs.get("old_text", "")
        new = kwargs.get("new_text", "")
        for f in py_files:
            content = f.read_text(encoding="utf-8")
            if old in content:
                f.write_text(content.replace(old, new), encoding="utf-8")
                results.append(f.name)

    elif operation == "add_encoding":
        # Her dosyanin basina # -*- coding: utf-8 -*- ekle
        for f in py_files:
            content = f.read_text(encoding="utf-8")
            if "# -*- coding" not in content:
                f.write_text("# -*- coding: utf-8 -*-\n" + content, encoding="utf-8")
                results.append(f.name)

    elif operation == "fix_imports":
        # Goreli importlari duzelt
        for f in py_files:
            content = f.read_text(encoding="utf-8")
            fixed = re.sub(
                r'^import (\w+)$',
                r'from src import \1',
                content,
                flags=re.MULTILINE
            )
            if fixed != content:
                f.write_text(fixed, encoding="utf-8")
                results.append(f.name)

    else:
        return {"success": False, "error": f"Bilinmeyen operasyon: {operation}"}

    return {
        "success": True,
        "operation": operation,
        "modified_files": results,
        "count": len(results),
    }


async def patch_file(path: str, old_text: str, new_text: str) -> ToolResult:
    """
    Büyük dosyalarda LLM'in Context aşımını engellemek için, dosyanın tamamını baştan 
    yazmak yerine sadece belirli bir metin bloğunu arayıp değiştiren spesifik "patch" aracı.
    """
    _ensure_workspace()
    
    target = Path(path).resolve()
    workspace = Path(WORKSPACE_DIR).resolve()
    
    if not str(target).startswith(str(workspace)):
        safe = _safe_path(path)
        if not safe:
            return ToolResult(success=False, data=None, error=f"Güvenlik ihlali: {path} workspace dışında!")
        target = Path(safe)

    if not target.exists():
        return ToolResult(success=False, data=None, error=f"Dosya bulunamadı: {path}")

    lock = _get_lock(str(target))

    async with lock:
        try:
            with open(str(target), "r", encoding="utf-8") as f:
                content = f.read()
            
            if old_text not in content:
                # LLM'in gönderdiği metinde boşluk hataları olabileceği için basit kontrol
                return ToolResult(
                    success=False, 
                    data=None, 
                    error=f"Bulunamadı (Tam eşleşme sağlanamadı). 'old_text' bloğu dosyada yok veya fazladan boşluk içeriyor."
                )
            
            new_content = content.replace(old_text, new_text, 1) # Sadece ilk eşleşmeyi değiştir
            
            with open(str(target), "w", encoding="utf-8") as f:
                f.write(new_content)
                
            return ToolResult(
                success=True, 
                data={"path": str(target), "action": "patched", "replaced_chars": len(old_text)}
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

