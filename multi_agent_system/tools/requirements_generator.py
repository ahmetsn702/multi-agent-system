"""
tools/requirements_generator.py
RequirementsGenerator: Proje kodlarini tarayip
requirements.txt otomatik uretir.
"""
import re
import subprocess
import sys
from pathlib import Path

STDLIB = {
    "os", "sys", "re", "json", "time", "datetime", "math",
    "random", "pathlib", "subprocess", "asyncio", "threading",
    "collections", "itertools", "functools", "typing", "abc",
    "io", "csv", "sqlite3", "hashlib", "base64", "urllib",
    "http", "email", "logging", "unittest", "copy", "string",
    "struct", "socket", "shutil", "tempfile", "contextlib",
    "dataclasses", "enum", "queue", "weakref", "gc", "inspect",
    "traceback", "warnings", "platform", "signal", "glob",
    "fnmatch", "pickle", "shelve", "gzip", "zipfile", "tarfile",
    "configparser", "argparse", "getpass", "pprint", "textwrap",
    "uuid", "decimal", "fractions", "statistics", "bisect",
    "heapq", "array", "cmath", "numbers", "operator",
}

PACKAGE_MAP = {
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "wx": "wxPython",
    "gi": "PyGObject",
    "Crypto": "pycryptodome",
    "jwt": "PyJWT",
    "attr": "attrs",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "requests": "requests",
    "pydantic": "pydantic",
    "sqlalchemy": "SQLAlchemy",
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "pytest": "pytest",
    "rich": "rich",
    "click": "click",
    "typer": "typer",
    "tkinter": None,  # stdlib, atla
}


def generate(project_path: str) -> dict:
    """Projedeki tum .py dosyalarini tara, requirements.txt uret."""
    root = Path(project_path)
    src_dir = root / "src"
    tests_dir = root / "tests"
    all_imports = set()

    for directory in [src_dir, tests_dir, root]:
        if not directory.exists():
            continue
        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("."):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                # Single-line: import foo / from foo import bar
                imports = re.findall(
                    r'^(?:from)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
                    content, re.MULTILINE
                )
                all_imports.update(imports)
                # Comma-separated: import foo, bar, baz
                for m in re.finditer(
                    r'^import\s+([a-zA-Z_][\w]*(?:\s*,\s*[a-zA-Z_][\w]*)*)',
                    content, re.MULTILINE
                ):
                    for pkg in m.group(1).split(","):
                        name = pkg.strip().split(".")[0]
                        if name:
                            all_imports.add(name)
            except Exception:
                pass

    # Stdlib ve yerel modulleri filtrele
    local_modules = set()
    if src_dir.exists():
        local_modules = {f.stem for f in src_dir.glob("*.py")}

    third_party = []
    for pkg in all_imports:
        if pkg in STDLIB:
            continue
        if pkg in local_modules:
            continue
        pip_name = PACKAGE_MAP.get(pkg)
        if pip_name is None:
            continue  # tkinter gibi stdlib ama farkli import
        if pip_name:
            third_party.append(pip_name)
        else:
            third_party.append(pkg)

    third_party = sorted(set(third_party))
    if not third_party:
        return {"success": True, "packages": [], "message": "Dis bagimlilik yok"}

    # Yuklu versiyonlari al
    requirements = []
    for pkg in third_party:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", pkg],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Version:"):
                        version = line.split(": ")[1].strip()
                        requirements.append(f"{pkg}>={version}")
                        break
            else:
                requirements.append(pkg)
        except Exception:
            requirements.append(pkg)

    req_content = "\n".join(requirements) + "\n"
    req_path = root / "requirements.txt"
    req_path.write_text(req_content, encoding="utf-8")
    print(f"[Requirements] {len(requirements)} paket -> requirements.txt")
    for r in requirements:
        print(f"[Requirements]   + {r}")

    return {
        "success": True,
        "packages": requirements,
        "path": str(req_path),
    }
