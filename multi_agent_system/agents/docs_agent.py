"""
agents/docs_agent.py
DocsAgent: Proje kodunu tarayip dokumantasyon dosyalari uretir.
"""
import ast
from pathlib import Path
from typing import Any, Optional

from core.base_agent import AgentResponse, BaseAgent, Task, ThoughtProcess
from core.message_bus import MessageBus


class DocsAgent(BaseAgent):
    """Uretilen proje kodundan README ve destekleyici dokumanlar olusturur."""

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="docs",
            name="Docs Ajani",
            role="Proje Dokumantasyonu",
            description="Proje dosyalarini tarar, README ve teknik dokumanlar uretir.",
            capabilities=["documentation", "readme_generation", "api_indexing"],
            bus=bus,
        )

    async def think(self, task: Task) -> ThoughtProcess:
        return ThoughtProcess(
            reasoning="Python dosyalarini, endpointleri ve bagimliliklari tarayip dokuman uretecegim.",
            plan=[
                "Proje dosyalarini topla",
                "Docstring ozetlerini cikar",
                "Endpointleri ve bagimliliklari listele",
                "README ve docs dosyalarini yaz",
            ],
            tool_calls=[],
            confidence=0.95,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        context = task.context or {}
        project_slug = str(context.get("project_slug", "default")).strip() or "default"
        project_dir = Path(context.get("project_dir") or (Path("workspace/projects") / project_slug))
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        py_files = self._collect_python_files(project_dir)
        doc_summaries = self._collect_docstring_summaries(py_files, project_dir)
        endpoints = self._collect_endpoints(py_files, project_dir)
        requirements = self._read_requirements(project_dir / "requirements.txt")
        goal = str(context.get("goal", task.description)).strip()

        readme_content = self._build_readme(
            project_slug=project_slug,
            goal=goal,
            py_files=py_files,
            doc_summaries=doc_summaries,
            endpoints=endpoints,
            requirements=requirements,
            project_dir=project_dir,
        )

        docstrings_md = self._build_docstrings_markdown(doc_summaries)
        endpoints_md = self._build_endpoints_markdown(endpoints)
        requirements_md = self._build_requirements_markdown(requirements)

        (docs_dir / "README.md").write_text(readme_content, encoding="utf-8")
        (docs_dir / "python_docstrings.md").write_text(docstrings_md, encoding="utf-8")
        (docs_dir / "api_endpoints.md").write_text(endpoints_md, encoding="utf-8")
        (docs_dir / "dependencies.md").write_text(requirements_md, encoding="utf-8")

        return AgentResponse(
            success=True,
            content={
                "readme_content": readme_content,
                "docs_dir": str(docs_dir),
                "py_file_count": len(py_files),
                "endpoint_count": len(endpoints),
                "requirements_count": len(requirements),
                "files_written": [
                    str(docs_dir / "README.md"),
                    str(docs_dir / "python_docstrings.md"),
                    str(docs_dir / "api_endpoints.md"),
                    str(docs_dir / "dependencies.md"),
                ],
            },
            metadata={"readme_lines": len(readme_content.splitlines())},
        )

    @staticmethod
    def _collect_python_files(project_dir: Path) -> list[Path]:
        files: list[Path] = []
        for base in (project_dir / "src", project_dir / "tests", project_dir):
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                if "__pycache__" in path.parts:
                    continue
                files.append(path)

        unique: list[Path] = []
        seen = set()
        for path in files:
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return sorted(unique, key=lambda p: str(p))

    @staticmethod
    def _collect_docstring_summaries(py_files: list[Path], project_dir: Path) -> list[dict[str, str]]:
        summaries: list[dict[str, str]] = []
        for py_file in py_files:
            rel = str(py_file.relative_to(project_dir))
            try:
                source = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source)
            except Exception:
                summaries.append({"file": rel, "summary": "Dosya parse edilemedi."})
                continue

            module_doc = (ast.get_docstring(tree) or "").strip()
            top_level_items: list[str] = []

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    doc = (ast.get_docstring(node) or "").strip()
                    one_liner = doc.splitlines()[0].strip() if doc else "Docstring yok."
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    top_level_items.append(f"- {kind} `{node.name}`: {one_liner}")

            module_line = module_doc.splitlines()[0].strip() if module_doc else "Modul docstring yok."
            summary = module_line
            if top_level_items:
                summary += "\n" + "\n".join(top_level_items[:12])
            summaries.append({"file": rel, "summary": summary})
        return summaries

    @staticmethod
    def _collect_endpoints(py_files: list[Path], project_dir: Path) -> list[dict[str, str]]:
        endpoints: list[dict[str, str]] = []
        method_attrs = {"get", "post", "put", "delete", "patch", "options", "head"}

        for py_file in py_files:
            rel = str(py_file.relative_to(project_dir))
            try:
                source = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source)
            except Exception:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for deco in node.decorator_list:
                    if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                        continue

                    attr = str(deco.func.attr).lower()
                    route_path = DocsAgent._extract_route_path(deco)
                    if not route_path:
                        continue

                    methods: list[str] = []
                    if attr in method_attrs:
                        methods = [attr.upper()]
                    elif attr == "route":
                        methods = DocsAgent._extract_route_methods(deco)
                    else:
                        continue

                    if not methods:
                        methods = ["GET"]

                    for method in methods:
                        endpoints.append(
                            {
                                "method": method,
                                "path": route_path,
                                "handler": node.name,
                                "file": rel,
                            }
                        )
        return endpoints

    @staticmethod
    def _extract_route_path(call_node: ast.Call) -> str:
        if call_node.args:
            first = call_node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value

        for kw in call_node.keywords:
            if kw.arg in {"path", "rule"} and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
        return ""

    @staticmethod
    def _extract_route_methods(call_node: ast.Call) -> list[str]:
        for kw in call_node.keywords:
            if kw.arg != "methods":
                continue
            val = kw.value
            if isinstance(val, (ast.List, ast.Tuple)):
                methods = []
                for el in val.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        methods.append(el.value.upper())
                return methods
        return ["GET"]

    @staticmethod
    def _read_requirements(req_path: Path) -> list[dict[str, str]]:
        if not req_path.exists():
            return []

        rows: list[dict[str, str]] = []
        for raw in req_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            package = line
            version = "-"
            for sep in ("==", ">=", "<=", "~=", ">", "<"):
                if sep in line:
                    left, right = line.split(sep, 1)
                    package = left.strip()
                    version = f"{sep}{right.strip()}"
                    break
            rows.append({"package": package, "version": version})
        return rows

    def _build_readme(
        self,
        project_slug: str,
        goal: str,
        py_files: list[Path],
        doc_summaries: list[dict[str, str]],
        endpoints: list[dict[str, str]],
        requirements: list[dict[str, str]],
        project_dir: Path,
    ) -> str:
        usage_cmd = self._detect_usage_command(project_dir)
        lines = [
            f"# {project_slug}",
            "",
            "## Proje Aciklamasi",
            goal if goal else "Bu proje multi-agent pipeline tarafindan olusturuldu.",
            "",
            "## Kurulum",
            "```bash",
            "python -m venv .venv",
            ".venv\\Scripts\\activate",
            "pip install -r requirements.txt",
            "```",
            "",
            "## Kullanim",
            "```bash",
            usage_cmd,
            "```",
            "",
            "## Python Dosya Ozetleri",
        ]

        if doc_summaries:
            for item in doc_summaries:
                lines.append(f"- `{item['file']}`: {item['summary'].splitlines()[0]}")
        else:
            lines.append("- Python dosyasi bulunamadi.")

        lines.extend(["", "## API Endpoint Listesi"])
        if endpoints:
            lines.extend(
                [
                    "| Method | Path | Handler | File |",
                    "|---|---|---|---|",
                ]
            )
            for ep in endpoints:
                lines.append(
                    f"| {ep.get('method', '-')} | {ep.get('path', '-')} | "
                    f"{ep.get('handler', '-')} | {ep.get('file', '-')} |"
                )
        else:
            lines.append("- Endpoint bulunamadi.")

        lines.extend(["", "## Bagimliliklar (requirements.txt)"])
        if requirements:
            lines.extend(["| Paket | Versiyon |", "|---|---|"])
            for row in requirements:
                lines.append(f"| {row['package']} | {row['version']} |")
        else:
            lines.append("- requirements.txt bulunamadi veya bos.")

        lines.extend(
            [
                "",
                "## Ek Dokumanlar",
                "- `docs/python_docstrings.md`",
                "- `docs/api_endpoints.md`",
                "- `docs/dependencies.md`",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _detect_usage_command(project_dir: Path) -> str:
        src_dir = project_dir / "src"
        candidates = [
            src_dir / "main.py",
            src_dir / "app.py",
            src_dir / "run.py",
            project_dir / "main.py",
        ]
        for path in candidates:
            if path.exists():
                rel = str(path.relative_to(project_dir)).replace("\\", "/")
                return f"python {rel}"
        return "python src/main.py"

    @staticmethod
    def _build_docstrings_markdown(doc_summaries: list[dict[str, str]]) -> str:
        lines = ["# Python Docstring Ozetleri", ""]
        if not doc_summaries:
            lines.append("Python dosyasi bulunamadi.")
            return "\n".join(lines)

        for item in doc_summaries:
            lines.append(f"## {item['file']}")
            lines.append(item["summary"])
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _build_endpoints_markdown(endpoints: list[dict[str, str]]) -> str:
        lines = ["# API Endpointleri", ""]
        if not endpoints:
            lines.append("Endpoint bulunamadi.")
            return "\n".join(lines)

        lines.extend(["| Method | Path | Handler | File |", "|---|---|---|---|"])
        for ep in endpoints:
            lines.append(
                f"| {ep.get('method', '-')} | {ep.get('path', '-')} | "
                f"{ep.get('handler', '-')} | {ep.get('file', '-')} |"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_requirements_markdown(requirements: list[dict[str, str]]) -> str:
        lines = ["# Bagimliliklar", ""]
        if not requirements:
            lines.append("requirements.txt bulunamadi veya bos.")
            return "\n".join(lines)

        lines.extend(["| Paket | Versiyon |", "|---|---|"])
        for row in requirements:
            lines.append(f"| {row['package']} | {row['version']} |")
        return "\n".join(lines)
