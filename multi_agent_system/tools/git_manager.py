"""
tools/git_manager.py
GitManager: Proje basinda repo init eder,
her basarili gorev sonrasi commit atar.
"""
import subprocess
from pathlib import Path


def _run_git(command: list, cwd: str) -> dict:
    """Git komutu calistir, sonucu dict olarak dondur."""
    try:
        result = subprocess.run(
            ["git"] + command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "output": (result.stdout or "").strip(),
            "error": (result.stderr or "").strip(),
        }
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


def init_repo(project_path: str) -> dict:
    """Proje klasorunde git repo baslatir."""
    path = Path(project_path)
    result = _run_git(["init"], str(path))
    if not result["success"]:
        return result

    # .gitignore olustur
    gitignore = path / ".gitignore"
    gitignore.write_text(
        "__pycache__/\n*.pyc\n*.pyo\n.env\n*.bak\n.pytest_cache/\n",
        encoding="utf-8",
    )

    # Kullanici kimligini ayarla (git config yoksa)
    _run_git(["config", "user.email", "agent@multi-agent.local"], str(path))
    _run_git(["config", "user.name", "Multi-Agent System"], str(path))

    # Ilk commit
    _run_git(["add", "."], str(path))
    _run_git(["commit", "-m", "init: Proje baslatildi (Multi-Agent)"], str(path))
    print(f"[Git] Repo baslatildi: {path.name}")
    return {"success": True, "path": str(path)}


def commit(project_path: str, message: str) -> dict:
    """Degisiklikleri commit et."""
    path = str(project_path)
    git_dir = Path(project_path) / ".git"
    if not git_dir.exists():
        init_repo(project_path)

    _run_git(["add", "."], path)

    # Degisiklik var mi kontrol et
    status = _run_git(["status", "--porcelain"], path)
    if not status.get("output"):
        return {"success": True, "message": "Degisiklik yok"}

    result = _run_git(["commit", "-m", message], path)
    if result["success"]:
        print(f"[Git] Commit: {message}")
    else:
        print(f"[Git] Commit hatasi: {result.get('error', 'Bilinmeyen hata')}")
    return result


def revert_last(project_path: str) -> dict:
    """Son commit'i geri al."""
    result = _run_git(["revert", "HEAD", "--no-edit"], str(project_path))
    if result["success"]:
        print("[Git] Son commit geri alindi")
    return result


def get_log(project_path: str, limit: int = 5) -> list:
    """Son N commit'i listele."""
    result = _run_git(
        ["log", f"-{limit}", "--oneline", "--no-decorate"],
        str(project_path),
    )
    if result["success"]:
        return result["output"].splitlines()
    return []
