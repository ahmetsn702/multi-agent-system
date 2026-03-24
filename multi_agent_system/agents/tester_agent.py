"""
agents/tester_agent.py
TesterAgent: Coder'in yazdigi testleri calistirir,
basarisiz olanlari Coder'a geri gonderir.
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional

from core.base_agent import BaseAgent, Task, AgentResponse, ThoughtProcess
from core.message_bus import MessageBus


class TesterAgent(BaseAgent):
    """
    Proje test klasorundeki pytest testlerini calistirir.
    LLM kullanmaz — sadece subprocess ile pytest.
    """

    def __init__(self, bus: Optional[MessageBus] = None):
        super().__init__(
            agent_id="tester",
            name="Test Ajani",
            role="Otomatik Test Calistirma",
            description="Coder'in yazdigi pytest testlerini calistirir, basarisiz olanlari raporlar.",
            capabilities=["test_execution", "pytest", "test_reporting"],
            bus=bus,
        )

    async def think(self, task: Task) -> ThoughtProcess:
        """LLM kullanmiyor, dogrudan act() cagrilir."""
        return ThoughtProcess(
            reasoning="Testleri pytest ile calistiracagim.",
            plan=["Test klasorunu bul", "pytest calistir", "Sonuclari raporla"],
            tool_calls=[],
            confidence=1.0,
        )

    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Pytest testlerini calistir ve sonuclari dondur."""
        context = task.context or {}
        project_slug = context.get("project_slug", "default")
        # Mutlak yol kullan — relative path + cwd karisikligi engellemek icin
        project_root = (Path.cwd() / "workspace" / "projects" / project_slug).resolve()
        src_dir = project_root / "src"

        # Testleri 3 farklı yerde ara
        possible_test_dirs = [
            project_root / "tests",
            project_root / "src" / "tests",
            project_root / "src",
        ]
        tests_dir = None
        for candidate in possible_test_dirs:
            if candidate.exists():
                test_files_check = [f for f in candidate.glob("test_*.py") if f.name != ".gitkeep"]
                if test_files_check:
                    tests_dir = candidate
                    print(f"[Tester] Test klasörü bulundu: {tests_dir}")
                    break
        
        if tests_dir is None:
            return AgentResponse(
                success=True,
                content={
                    "summary": "Test dosyası bulunamadı.",
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "status": "no_tests",
                },
            )

        test_files = [f for f in tests_dir.glob("test_*.py") if f.name != ".gitkeep"]
        if not test_files:
            return AgentResponse(
                success=True,
                content={
                    "summary": "Test dosyasi bulunamadi.",
                    "passed": 0,
                    "failed": 0,
                    "errors": 0,
                    "failed_tests": [],
                    "status": "no_tests",
                },
            )

        import os
        env = os.environ.copy()
        src_path = str(project_root / "src")
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_path + os.pathsep + existing if existing else src_path

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(tests_dir),  # mutlak yol
                 "-v", "--tb=short", "--no-header", "-q"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                cwd=str(project_root),  # proje kökü, src/ değil
                env=env,
            )
            output = result.stdout + result.stderr

            # Sonuclari parse et
            passed = output.count(" passed")
            failed = output.count(" failed")
            errors = output.count(" error")

            # Basarisiz testleri ve hata detaylarını cikar
            failed_tests = []
            capture_next = 0
            current_fail = []
            
            for line in output.splitlines():
                if "FAILED" in line or "ERROR" in line:
                    if current_fail:
                        failed_tests.append("\n".join(current_fail))
                    current_fail = [line.strip()]
                    capture_next = 10  # Hata başlığından sonraki 10 satırı da al (full stack traces için)
                elif capture_next > 0:
                    if line.strip() and not line.startswith("==="):
                        current_fail.append("    " + line.strip())
                    capture_next -= 1
                    
            if current_fail:
                failed_tests.append("\n".join(current_fail))

            success = result.returncode == 0
            summary = f"{passed} test gecti"
            if failed:
                summary += f", {failed} basarisiz"
            if errors:
                summary += f", {errors} hata"

            print(f"[Tester] {summary}")
            if failed_tests:
                for ft in failed_tests[:3]: # Log kalabalığı olmaması için ilk 3 hatayı bas
                    error_lines = ft.splitlines()[:5]  # First 5 lines of error
                    for line in error_lines:
                        print(f"[Tester]   {line}")

            return AgentResponse(
                success=success,
                content={
                    "summary": summary,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "failed_tests": failed_tests,  # Coder bu listeyi context'ten alıp okuyacak
                    "output": output[:2000],
                    "status": "passed" if success else "failed",
                    "return_code": result.returncode,
                },
            )

        except subprocess.TimeoutExpired:
            return AgentResponse(
                success=False,
                content={"error": "Test timeout (120s)", "status": "timeout"},
            )
        except Exception as e:
            return AgentResponse(
                success=False,
                content={"error": str(e), "status": "error"},
            )
