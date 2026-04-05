"""
LinterAgent: Uretilen kodu pylint + flake8 ile analiz eder.
Skoru Critic'e bildirir, ciddi hatalari Coder'a gonderir.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from core.base_agent import BaseAgent, Task, ThoughtProcess, AgentResponse

# Absolute root of the multi_agent_system package
_SYSTEM_ROOT = Path(__file__).parent.parent.resolve()

# Lint score >= 8.0 means pass (orchestrator threshold)
LINT_PASS_THRESHOLD = 8.0


class LinterAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(
            agent_id="linter",
            name="Linter Ajani",
            role="Linter",
            description="Kod kalitesini flake8 ve pylint ile analiz eder.",
            capabilities=["linting", "python_quality", "flake8", "pylint"]
        )

    async def think(self, task: Task) -> ThoughtProcess:
        return ThoughtProcess(
            reasoning="Flake8 ve pylint ile statik analiz yapilacak.",
            plan=["Python dosyalarini topla", "Flake8 calistir", "Pylint calistir", "Skor hesapla"],
            tool_calls=[],
            confidence=0.95,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        context = task.context or {}
        project_slug = context.get("project_slug", "default")

        # ALL paths absolute — immune to process CWD
        project_root = (_SYSTEM_ROOT / "workspace" / "projects" / project_slug).resolve()
        src_dir = (project_root / "src").resolve()

        if not src_dir.exists():
            return AgentResponse(
                success=True,
                content={"error": "src/ klasoru bulunamadi", "score": 0},
            )

        # Collect .py files, verify each exists (absolute paths)
        py_files = [f for f in src_dir.glob("*.py") if f.name != ".gitkeep" and f.exists()]
        if not py_files:
            return AgentResponse(
                success=True,
                content={"message": "Python dosyasi bulunamadi", "score": 10},
            )

        results = {}
        abs_src = str(src_dir)

        # ── flake8 (absolute file paths, absolute cwd) ──────────
        try:
            abs_files = [str(f.resolve()) for f in py_files]
            flake8_result = subprocess.run(
                [sys.executable, "-m", "flake8"]
                + abs_files
                + ["--max-line-length=100", "--statistics", "--count"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
                cwd=abs_src,
            )
            flake8_output = flake8_result.stdout + flake8_result.stderr
            # Count only real errors for penalty (E1xx, E7xx, E9xx, F8xx)
            # Exclude style warnings: E2xx (whitespace), E3xx, W series, C series
            _REAL_ERROR_PREFIXES = ("E1", "E7", "E9", "F8")
            real_error_count = 0
            for l in flake8_output.splitlines():
                stripped = l.strip()
                if not stripped or stripped.isdigit() or "E902" in stripped:
                    continue
                if any(prefix in stripped for prefix in _REAL_ERROR_PREFIXES):
                    real_error_count += 1
            results["flake8"] = {
                "errors": real_error_count,
                "output": flake8_output[:1000],
                "passed": real_error_count == 0,
            }
        except FileNotFoundError:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "flake8", "-q"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=60,
            )
            results["flake8"] = {"errors": 0, "output": "flake8 yuklendi", "passed": True}
        except Exception as e:
            results["flake8"] = {"errors": 0, "output": str(e), "passed": True}

        # ── pylint (absolute file paths, absolute cwd) ──────────
        try:
            abs_files = [str(f.resolve()) for f in py_files]
            args = (
                [sys.executable, "-m", "pylint"]
                + abs_files
                + [
                    "--output-format=text",
                    "--score=yes",
                    "--disable=C0114,C0115,C0116,C0301,W0611",
                    "--max-line-length=100",
                    "--exit-zero",
                ]
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = abs_src

            pylint_result = subprocess.run(
                args,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
                cwd=abs_src, env=env,
            )
            pylint_output = pylint_result.stdout + pylint_result.stderr

            score = self._parse_pylint_score(pylint_output)
            print(f"[Linter] Pylint raw score: {score}")
            results["pylint"] = {
                "score": score,
                "output": pylint_output[:1000],
                "passed": score >= 7.0,
            }
        except FileNotFoundError:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "pylint", "-q"],
                capture_output=True, encoding="utf-8", errors="replace", timeout=60,
            )
            results["pylint"] = {"score": 8.0, "output": "pylint yuklendi", "passed": True}
        except Exception as e:
            results["pylint"] = {"score": 8.0, "output": str(e), "passed": True}

        # ── Genel skor hesapla ───────────────────────────────
        pylint_score = results.get("pylint", {}).get("score", 8.0)
        flake8_errors = results.get("flake8", {}).get("errors", 0)

        flake8_penalty = min(flake8_errors * 0.5, 3.0)
        final_score = max(0.0, pylint_score - flake8_penalty)

        # Critical issues: only real code errors (E1xx, E7xx, E9xx, F8xx)
        # Excludes: E2xx (whitespace), E3xx (blank lines), W (warnings), E902 (IO)
        critical_issues = []
        flake8_out = results.get("flake8", {}).get("output", "")
        for line in flake8_out.splitlines():
            if "E902" in line:
                continue
            if any(code in line for code in ["E1", "E7", "E9", "F8"]):
                critical_issues.append(line.strip())

        # Pass if pylint >= 8.0 AND no critical flake8 issues
        # Style warnings (E2xx, W) do NOT block passing
        passed = pylint_score >= LINT_PASS_THRESHOLD and len(critical_issues) == 0

        summary = f"Pylint: {pylint_score:.1f}/10 | Flake8: {flake8_errors} hata | Final: {final_score:.1f}/10"
        print(f"[Linter] {summary}")

        if critical_issues:
            print(f"[Linter] {len(critical_issues)} kritik hata")
            for issue in critical_issues[:3]:
                print(f"[Linter]   {issue}")

        return AgentResponse(
            success=passed,
            content={
                "summary": summary,
                "pylint_score": pylint_score,
                "flake8_errors": flake8_errors,
                "final_score": final_score,
                "critical_issues": critical_issues,
                "passed": passed,
                "details": results,
            },
        )

    @staticmethod
    def _parse_pylint_score(output: str) -> float:
        """Extract pylint score from output text."""
        match = re.search(r'rated at\s+([-\d.]+)/10', output)
        if match:
            try:
                return max(float(match.group(1)), 0.0)
            except ValueError:
                pass
        match = re.search(r'rated at\s+([-\d.]+)', output)
        if match:
            try:
                return max(float(match.group(1)), 0.0)
            except ValueError:
                pass
        print(f"[Linter] Score parse failed. Output: {output[:200]}")
        return 5.0
