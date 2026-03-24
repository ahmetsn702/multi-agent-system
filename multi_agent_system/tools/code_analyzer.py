"""
tools/code_analyzer.py
Mevcut projeleri derinlemesine analiz eden araç.
ZIP dosyası, GitHub URL veya yerel klasör alır;
bağımlılık grafiği, fonksiyon haritası ve olası bug'ları çıkarır.
"""
import ast
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".html", ".css", ".json", ".md", ".txt",
    ".yml", ".yaml", ".toml", ".env.example",
}

SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv",
    "venv", "env", "dist", "build", ".idea", ".vscode",
}

# Şüpheli kod kalıpları
SUSPICIOUS_PATTERNS = [
    (r"\bexcept\s*:", "Bare except — tüm hataları yakalar, gizler"),
    (r"TODO|FIXME|HACK|XXX", "Tamamlanmamış / geçici kod işareti"),
    (r'open\s*\(["\'][A-Z]:[\\\/]', "Hardcoded Windows yolu"),
    (r'open\s*\(["\']\/(?!tmp)', "Hardcoded Unix yolu"),
    (r"eval\s*\(", "eval() güvenlik riski"),
    (r"exec\s*\(", "exec() güvenlik riski"),
    (r"password\s*=\s*[\"'][^\"']+[\"']", "Hardcoded şifre"),
    (r"api_key\s*=\s*[\"'][^\"']+[\"']", "Hardcoded API anahtarı"),
    (r"print\s*\(", "Debug print ifadesi"),
    (r"import \*", "Wildcard import — isim çakışması riski"),
]


def _should_skip(path: Path) -> bool:
    """Taranmaması gereken klasörleri filtrele."""
    return any(skip in path.parts for skip in SKIP_DIRS)


def _extract_python_info(content: str, filepath: str) -> dict:
    """
    Python dosyasından AST ile fonksiyon/sınıf/import bilgisi çıkar.

    Args:
        content: Dosya içeriği
        filepath: Dosya yolu (hata mesajları için)

    Returns:
        dict: functions, classes, imports, has_main listesi
    """
    info = {
        "functions": [],
        "classes": [],
        "imports": [],
        "has_main": False,
    }
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                info["functions"].append(node.name)
            elif isinstance(node, ast.AsyncFunctionDef):
                info["functions"].append(f"async {node.name}")
            elif isinstance(node, ast.ClassDef):
                info["classes"].append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        info["imports"].append(alias.name)
                else:
                    module = node.module or ""
                    info["imports"].append(module)
        info["has_main"] = 'if __name__ == "__main__"' in content
    except SyntaxError:
        info["syntax_error"] = True
    return info


def _find_suspicious(content: str, filepath: str) -> list[dict]:
    """
    Şüpheli kod kalıplarını regex ile tara.

    Args:
        content: Dosya içeriği
        filepath: Dosya yolu

    Returns:
        list: Her bulunan sorun için {line, pattern, description} dict
    """
    issues = []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        for pattern, description in SUSPICIOUS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                issues.append({
                    "file": filepath,
                    "line": i,
                    "code": line.strip()[:120],
                    "description": description,
                })
    return issues


def analyze_project(project_path: str) -> dict:
    """
    Proje klasörünü derinlemesine analiz et.

    Args:
        project_path: Analiz edilecek klasör yolu

    Returns:
        dict: summary, structure, file_map, dependencies, issues, stats
    """
    root = Path(project_path).resolve()

    if not root.exists():
        return {"error": f"Klasör bulunamadı: {project_path}"}

    files_content: dict[str, str] = {}
    structure_lines: list[str] = []
    file_map: dict[str, dict] = {}
    all_issues: list[dict] = []

    def build_tree(directory: Path, prefix: str = "", depth: int = 0):
        """Dizin ağacını oluştur ve dosyaları oku."""
        if depth > 5 or len(files_content) >= 80:
            return
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda x: (x.is_file(), x.name),
            )
        except PermissionError:
            return

        for i, entry in enumerate(entries):
            if _should_skip(entry):
                continue
            connector = "└── " if i == len(entries) - 1 else "├── "
            structure_lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                ext = "    " if i == len(entries) - 1 else "│   "
                build_tree(entry, prefix + ext, depth + 1)
            elif entry.is_file() and entry.suffix in SUPPORTED_EXTENSIONS:
                if entry.stat().st_size <= 150 * 1024:  # 150 KB limit
                    try:
                        content = entry.read_text(encoding="utf-8", errors="ignore")
                        rel = str(entry.relative_to(root))
                        files_content[rel] = content

                        # Python dosyaları için derin analiz
                        if entry.suffix == ".py":
                            py_info = _extract_python_info(content, rel)
                            file_map[rel] = py_info
                            issues = _find_suspicious(content, rel)
                            all_issues.extend(issues)
                        else:
                            file_map[rel] = {"type": entry.suffix}
                    except Exception:
                        pass

    build_tree(root)

    # Bağımlılık grafiği: hangi modül kimi import ediyor
    dependency_graph: dict[str, list[str]] = {}
    for rel, info in file_map.items():
        if "imports" in info:
            module_name = Path(rel).stem
            dependency_graph[module_name] = info["imports"]

    # İstatistikler
    total_lines = sum(len(c.splitlines()) for c in files_content.values())
    py_files = [k for k in files_content if k.endswith(".py")]
    total_functions = sum(
        len(v.get("functions", [])) for v in file_map.values()
    )
    total_classes = sum(
        len(v.get("classes", [])) for v in file_map.values()
    )
    syntax_errors = [
        k for k, v in file_map.items() if v.get("syntax_error")
    ]

    summary = (
        f"{root.name} | {len(files_content)} dosya | "
        f"{len(py_files)} Python | {total_lines} satır | "
        f"{total_functions} fonksiyon | {total_classes} sınıf | "
        f"{len(all_issues)} potansiyel sorun"
    )

    return {
        "path": str(root),
        "project_name": root.name,
        "structure": f"{root.name}/\n" + "\n".join(structure_lines),
        "files": files_content,
        "file_map": file_map,
        "dependency_graph": dependency_graph,
        "issues": all_issues[:50],  # max 50 sorun
        "syntax_errors": syntax_errors,
        "stats": {
            "file_count": len(files_content),
            "python_files": len(py_files),
            "total_lines": total_lines,
            "total_functions": total_functions,
            "total_classes": total_classes,
            "issue_count": len(all_issues),
        },
        "summary": summary,
    }


def read_zip(zip_path: str) -> dict:
    """
    ZIP dosyasını geçici klasöre aç ve analiz et.

    Args:
        zip_path: ZIP dosyasının yolu

    Returns:
        dict: analyze_project() çıktısı
    """
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return {"error": f"ZIP dosyası bulunamadı: {zip_path}"}
    if not zipfile.is_zipfile(zip_path):
        return {"error": f"Geçerli bir ZIP dosyası değil: {zip_path}"}

    tmp_dir = tempfile.mkdtemp(prefix="mas_analyze_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
        result = analyze_project(tmp_dir)
        result["source"] = f"zip:{zip_path.name}"
        return result
    except Exception as e:
        return {"error": f"ZIP açma hatası: {e}"}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def read_github(url: str, branch: str = "main") -> dict:
    """
    GitHub reposunu shallow clone ile indir ve analiz et.

    Args:
        url: GitHub repo URL'i (https://github.com/...)
        branch: Klonlanacak branch (varsayılan: main)

    Returns:
        dict: analyze_project() çıktısı
    """
    if not url.startswith("http"):
        return {"error": "Geçerli bir GitHub URL'i değil"}

    # git komutu mevcut mu kontrol et
    if shutil.which("git") is None:
        return {"error": "git komutu bulunamadı. Git yüklü mü?"}

    tmp_dir = tempfile.mkdtemp(prefix="mas_github_")
    try:
        print(f"[CodeAnalyzer] GitHub'dan klonlanıyor: {url}")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", branch, url, tmp_dir],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # Branch adı yanlış olabilir, master dene
            result2 = subprocess.run(
                ["git", "clone", "--depth", "1", url, tmp_dir],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result2.returncode != 0:
                return {"error": f"Git clone hatası: {result2.stderr[:300]}"}

        analysis = analyze_project(tmp_dir)
        analysis["source"] = f"github:{url}"
        return analysis
    except subprocess.TimeoutExpired:
        return {"error": "Git clone timeout (60s). Repo çok büyük olabilir."}
    except Exception as e:
        return {"error": f"GitHub clone hatası: {e}"}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def analyze_from_source(source: str) -> dict:
    """
    Kaynak tipini otomatik tespit et ve uygun analiz fonksiyonunu çağır.

    Args:
        source: Klasör yolu, ZIP yolu veya GitHub URL'i

    Returns:
        dict: Analiz sonucu
    """
    source = source.strip().strip('"').strip("'")

    if source.startswith("https://github.com") or source.startswith("git@github.com"):
        return read_github(source)
    elif source.endswith(".zip") and Path(source).exists():
        return read_zip(source)
    elif Path(source).is_dir():
        return analyze_project(source)
    else:
        return {"error": f"Tanınamayan kaynak: '{source}'. Klasör yolu, ZIP veya GitHub URL girin."}
