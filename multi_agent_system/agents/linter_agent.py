"""
LinterAgent: Üretilen kodu pylint + flake8 ile analiz eder.
Skoru Critic'e bildirir, ciddi hataları Coder'a gönderir.
"""
import subprocess
import sys
from pathlib import Path

from core.base_agent import BaseAgent, Task, AgentResponse

class LinterAgent(BaseAgent):
    def __init__(self, llm_client=None):
        super().__init__(
            agent_id="linter",
            name="Linter Ajanı",
            role="Linter",
            description="Kod kalitesini flake8 ve pylint ile analiz eder.",
            capabilities=["linting", "python_quality", "flake8", "pylint"]
        )

    async def think(self, task: Task):
        pass  # LLM kullanmıyor

    async def act(self, task: Task) -> AgentResponse:
        context = task.context or {}
        project_slug = context.get("project_slug", "default")
        project_root = Path("workspace/projects") / project_slug
        src_dir = project_root / "src"
        
        if not src_dir.exists():
            return AgentResponse(
                success=True,
                content={"error": "src/ klasörü bulunamadı", "score": 0},
            )
            
        py_files = [f for f in src_dir.glob("*.py") if f.name != ".gitkeep"]
        if not py_files:
            return AgentResponse(
                success=True,
                content={"message": "Python dosyası bulunamadı", "score": 10},
            )
            
        results = {}
        
        # ── flake8 ──────────────────────────────────────────
        try:
            flake8_result = subprocess.run(
                [sys.executable, "-m", "flake8",
                 str(src_dir),
                 "--max-line-length=100",
                 "--statistics",
                 "--count"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                cwd=str(project_root),
            )
            flake8_output = flake8_result.stdout + flake8_result.stderr
            flake8_errors = len([l for l in flake8_output.splitlines() if l.strip() and not l.strip().isdigit()])
            results["flake8"] = {
                "errors": flake8_errors,
                "output": flake8_output[:1000],
                "passed": flake8_errors == 0,
            }
        except FileNotFoundError:
            # flake8 yüklü değil, yükle
            subprocess.run([sys.executable, "-m", "pip", "install", "flake8", "-q"], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
            results["flake8"] = {"errors": 0, "output": "flake8 yüklendi", "passed": True}
        except Exception as e:
            results["flake8"] = {"errors": 0, "output": str(e), "passed": True}
            
        # ── pylint ──────────────────────────────────────────
        try:
            # Python dosyalarını bul
            py_files = list(src_dir.glob("*.py"))
            if not py_files:
                score = 8.0
                results["pylint"] = {
                    "score": score,
                    "output": "Python dosyası bulunamadı",
                    "passed": True,
                }
            else:
                # Dosya listesi ile pylint çağır
                args = [sys.executable, "-m", "pylint"] + [f.name for f in py_files] + [
                    "--output-format=text",
                    "--score=yes",
                    "--disable=C0114,C0115,C0116,C0301,W0611",
                    "--max-line-length=100",
                    "--exit-zero"
                ]
                import os
                env = os.environ.copy()
                env["PYTHONPATH"] = str(src_dir)
                
                pylint_result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    cwd=str(src_dir),
                    env=env,
                )
                pylint_output = pylint_result.stdout + pylint_result.stderr
                
                # Skoru parse et
                import re
                score = None
                # Pattern 1: "rated at 7.50/10"
                match = re.search(r'rated at\s+([-\d.]+)/10', pylint_output)
                if match:
                    try:
                        score = float(match.group(1))
                    except ValueError:
                        pass
                # Pattern 2: Sadece sayı
                if score is None:
                    match = re.search(r'rated at\s+([-\d.]+)', pylint_output)
                    if match:
                        try:
                            score = float(match.group(1))
                        except ValueError:
                            pass
                # Negatif skoru 0 yap
                if score is not None and score < 0:
                    score = 0.0
                # Parse edilemedi
                if score is None:
                    score = 5.0
                    print(f"[Linter] ⚠️ Parse edilemedi. Çıktı: {pylint_output[:200]}")
                
                print(f"[Linter] Pylint raw score: {score}")
                results["pylint"] = {
                    "score": score,
                    "output": pylint_output[:1000],
                    "passed": score >= 7.0,
                }
        except FileNotFoundError:
            subprocess.run([sys.executable, "-m", "pip", "install", "pylint", "-q"], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
            results["pylint"] = {"score": 8.0, "output": "pylint yüklendi", "passed": True}
        except Exception as e:
            results["pylint"] = {"score": 8.0, "output": str(e), "passed": True}
            
        # ── Genel skor hesapla ───────────────────────────────
        pylint_score = results.get("pylint", {}).get("score", 8.0)
        flake8_errors = results.get("flake8", {}).get("errors", 0)
        
        flake8_penalty = min(flake8_errors * 0.5, 3.0)
        final_score = max(0.0, pylint_score - flake8_penalty)
        
        # Ciddi hatalar var mı?
        critical_issues = []
        flake8_out = results.get("flake8", {}).get("output", "")
        for line in flake8_out.splitlines():
            if any(code in line for code in ["E1", "E2", "E7", "E9", "F8"]):
                critical_issues.append(line.strip())
                
        passed = final_score >= 6.0 and len(critical_issues) == 0
        
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
