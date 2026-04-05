"""
tests/test_tools.py
Unit tests for tool modules: shell_executor, file_editor, requirements_generator,
interactive_shell, project_indexer, telegram _safe_slug.
"""
import pytest


# ── shell_executor: _is_safe ─────────────────────────────────────────────────

def test_shell_safe_allowed_command():
    from tools.shell_executor import _is_safe
    assert _is_safe("python main.py") is True
    assert _is_safe("pip install requests") is True
    assert _is_safe("git status") is True
    assert _is_safe("pytest -v") is True


def test_shell_safe_blocked_pattern():
    from tools.shell_executor import _is_safe
    assert _is_safe("rm -rf /") is False
    assert _is_safe("shutdown -s") is False


def test_shell_safe_unknown_command():
    from tools.shell_executor import _is_safe
    # Commands not in ALLOWED_PREFIXES should be blocked
    assert _is_safe("malicious_binary --steal-data") is False


# ── file_editor: _safe_path ──────────────────────────────────────────────────

def test_file_editor_safe_path():
    from tools.file_editor import _safe_path, WORKSPACE_DIR
    import os
    # Build a path that is inside the workspace
    safe_rel = os.path.join(WORKSPACE_DIR, "projects", "test", "src", "main.py")
    result = _safe_path(safe_rel)
    assert result is not None
    assert result.startswith(WORKSPACE_DIR)


def test_file_editor_path_traversal():
    from tools.file_editor import _safe_path
    assert _safe_path("../../etc/passwd") is None
    assert _safe_path("../../../windows/system32") is None


# ── file_manager: _get_lock ──────────────────────────────────────────────────

def test_file_manager_get_lock():
    import asyncio
    from tools.file_manager import _get_lock
    lock1 = _get_lock("/some/path")
    lock2 = _get_lock("/some/path")
    assert lock1 is lock2  # Same path returns same lock
    lock3 = _get_lock("/other/path")
    assert lock1 is not lock3  # Different path returns different lock


# ── requirements_generator: import detection ──────────────────────────────────

def test_requirements_stdlib_filter():
    from tools.requirements_generator import STDLIB
    assert "os" in STDLIB
    assert "sys" in STDLIB
    assert "requests" not in STDLIB


def test_requirements_package_map():
    from tools.requirements_generator import PACKAGE_MAP
    assert PACKAGE_MAP["cv2"] == "opencv-python"
    assert PACKAGE_MAP["PIL"] == "Pillow"
    assert PACKAGE_MAP["sklearn"] == "scikit-learn"
    assert PACKAGE_MAP["tkinter"] is None  # stdlib, skip


# ── interactive_shell: cd parsing ─────────────────────────────────────────────

def test_interactive_shell_init(tmp_path):
    from tools.interactive_shell import InteractiveShell
    shell = InteractiveShell(str(tmp_path), "test")
    assert shell.cwd == tmp_path.resolve()
    assert "PYTHONPATH" in shell.env


def test_interactive_shell_banned_command(tmp_path):
    from tools.interactive_shell import InteractiveShell
    shell = InteractiveShell(str(tmp_path), "test")
    result = shell.run("rm -rf /")
    assert result["success"] is False
    assert "GUVENLIK" in result["stderr"] or "engellendi" in result["stderr"]


# ── project_indexer: symlink skip ─────────────────────────────────────────────

def test_project_indexer_basic(tmp_path):
    from tools.project_indexer import index_project
    # Create a simple project structure
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "utils.py").write_text("def foo(): pass", encoding="utf-8")

    result = index_project(str(tmp_path))
    assert "error" not in result
    assert result["file_count"] == 2
    assert result["total_lines"] > 0


def test_project_indexer_nonexistent():
    from tools.project_indexer import index_project
    result = index_project("/nonexistent/path/xyz")
    assert "error" in result


# ── telegram: _safe_slug ──────────────────────────────────────────────────────

def test_safe_slug_normal():
    from telegram_bot.bot import _safe_slug
    assert _safe_slug("my-project-123") == "my-project-123"
    assert _safe_slug("hello_world") == "hello_world"


def test_safe_slug_traversal():
    from telegram_bot.bot import _safe_slug
    assert ".." not in _safe_slug("../../etc/passwd")
    assert "/" not in _safe_slug("path/to/evil")
    assert "\\" not in _safe_slug("path\\to\\evil")


def test_safe_slug_empty():
    from telegram_bot.bot import _safe_slug
    assert _safe_slug("") == "invalid-slug"
    assert _safe_slug("///") == "invalid-slug"
