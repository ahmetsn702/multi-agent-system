"""
tools/file_editor.py
FileEditor: Mevcut dosyaları satır bazında düzenler.
Tüm düzenlemeler workspace dizini içinde sandbox'lanmıştır.
"""
import os
from pathlib import Path
from typing import Optional

WORKSPACE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "workspace")
)


def _safe_path(file_path: str) -> Optional[str]:
    """Resolve path and verify it stays inside WORKSPACE_DIR."""
    resolved = os.path.abspath(file_path)
    if not resolved.startswith(WORKSPACE_DIR):
        return None
    return resolved


def replace_in_file(file_path: str, old_text: str, new_text: str) -> dict:
    """Dosyada metin bul ve değiştir. Yedek (.bak) oluşturur."""
    safe = _safe_path(file_path)
    if not safe:
        return {"success": False, "error": f"Güvenlik hatası: {file_path} workspace dışında, düzenleme engellendi."}

    path = Path(safe)
    if not path.exists():
        return {"success": False, "error": f"Dosya bulunamadı: {file_path}"}

    content = path.read_text(encoding="utf-8")
    if old_text not in content:
        return {"success": False, "error": f"Metin bulunamadı: '{old_text[:50]}'"}

    # Yedek oluştur
    backup = Path(str(path) + ".bak")
    backup.write_text(content, encoding="utf-8")

    # Değiştir (sadece ilk eşleşme)
    path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
    return {"success": True, "file": str(path), "backup": str(backup)}


def replace_lines(file_path: str, start_line: int, end_line: int, new_content: str) -> dict:
    """Belirtilen satır aralığını yeni içerikle değiştir. Yedek (.bak) oluşturur."""
    safe = _safe_path(file_path)
    if not safe:
        return {"success": False, "error": f"Güvenlik hatası: {file_path} workspace dışında, düzenleme engellendi."}

    path = Path(safe)
    if not path.exists():
        return {"success": False, "error": f"Dosya bulunamadı: {file_path}"}

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    # Yedek oluştur
    backup = Path(str(path) + ".bak")
    backup.write_text("".join(lines), encoding="utf-8")

    # Satırları değiştir
    new_lines = lines[:start_line - 1] + [new_content + "\n"] + lines[end_line:]
    path.write_text("".join(new_lines), encoding="utf-8")
    return {"success": True, "replaced_lines": f"{start_line}-{end_line}"}
