"""
tools/project_indexer.py
ProjectIndexer: Mevcut projeyi okur, ajan sistemine bağlam verir.
"""
from pathlib import Path
from typing import Optional


SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".json", ".md", ".txt", ".yml", ".yaml", ".toml"
}

SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv",
    "venv", "env", "dist", "build", ".idea", ".vscode"
}


def index_project(project_path: str) -> dict:
    """Proje klasörünü tara, dosya yapısını ve içeriklerini döndür."""
    root = Path(project_path).resolve()

    if not root.exists():
        return {"error": f"Klasör bulunamadı: {project_path}"}

    files = {}
    structure_lines = []

    def should_skip(path: Path) -> bool:
        return any(skip in path.parts for skip in SKIP_DIRS)

    def build_tree(directory: Path, prefix: str = "", depth: int = 0):
        if depth > 4 or len(files) >= 50:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            if should_skip(entry):
                continue
            connector = "└── " if i == len(entries) - 1 else "├── "
            structure_lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                ext = "    " if i == len(entries) - 1 else "│   "
                build_tree(entry, prefix + ext, depth + 1)
            elif entry.is_file() and entry.suffix in SUPPORTED_EXTENSIONS:
                if entry.stat().st_size <= 100 * 1024:  # 100KB limit
                    try:
                        content = entry.read_text(encoding="utf-8", errors="ignore")
                        files[str(entry.relative_to(root))] = content
                    except Exception:
                        pass

    build_tree(root)

    total_lines = sum(len(c.splitlines()) for c in files.values())
    summary = f"{root.name} | {len(files)} dosya | {total_lines} satır"

    return {
        "path": str(root),
        "project_name": root.name,
        "structure": f"{root.name}/\n" + "\n".join(structure_lines),
        "files": files,
        "summary": summary,
        "file_count": len(files),
        "total_lines": total_lines,
    }


def find_in_project(project_path: str, search_term: str) -> list:
    """Projede metin ara, bulunan satırları döndür."""
    index = index_project(project_path)
    results = []
    for rel_path, content in index.get("files", {}).items():
        for i, line in enumerate(content.splitlines(), 1):
            if search_term.lower() in line.lower():
                results.append({"file": rel_path, "line": i, "content": line.strip()})
    return results
