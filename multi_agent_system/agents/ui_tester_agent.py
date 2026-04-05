"""
agents/ui_tester_agent.py
Playwright-based UI testing agent for web projects.

Automatically tests Flask/FastAPI apps and static HTML projects,
captures screenshots, and reports to CriticAgent.
Falls back to HTML analysis when Playwright is unavailable.
"""
import asyncio
import logging
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

from core.base_agent import BaseAgent, Task, ThoughtProcess, AgentResponse

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("Playwright not installed. Falling back to HTML analysis.")


class UITesterAgent(BaseAgent):
    """
    UI Testing Agent using Playwright.
    
    Responsibilities:
    - Detect web projects (Flask, FastAPI, static HTML)
    - Start servers if needed
    - Capture screenshots
    - Report to CriticAgent
    """
    
    def __init__(self, agent_id: str = "ui_tester", bus=None):
        super().__init__(
            agent_id=agent_id,
            name="UI Test Ajanı",
            role="Otomatik UI Testing ve Screenshot",
            description="Web projelerini (Flask, FastAPI, HTML) otomatik test eder ve screenshot alır",
            capabilities=["ui_testing", "screenshot", "browser_automation", "server_management"],
            bus=bus
        )
        self.playwright_available = PLAYWRIGHT_AVAILABLE
        self.server_process = None
    
    async def think(self, task: Task) -> ThoughtProcess:
        """Analyze if UI testing is needed."""
        project_dir = task.context.get("project_dir", "")
        files = task.context.get("files", [])
        
        # Check if project has frontend files
        has_html = any(f.endswith('.html') for f in files)
        has_css = any(f.endswith('.css') for f in files)
        has_js = any(f.endswith('.js') for f in files)
        has_flask = any('flask' in f.lower() or 'app.py' in f for f in files)
        has_fastapi = any('fastapi' in f.lower() or 'main.py' in f for f in files)
        
        is_web_project = has_html or has_flask or has_fastapi
        
        reasoning = (
            f"Project analysis:\n"
            f"- HTML files: {has_html}\n"
            f"- CSS files: {has_css}\n"
            f"- JS files: {has_js}\n"
            f"- Flask app: {has_flask}\n"
            f"- FastAPI app: {has_fastapi}\n"
            f"- Web project: {is_web_project}\n"
            f"- Playwright available: {self.playwright_available}"
        )
        
        if not is_web_project:
            return ThoughtProcess(
                reasoning="Not a web project, skipping UI test",
                plan=["Skip UI testing"],
                tool_calls=[],
                confidence=0.0
            )

        if not self.playwright_available and (has_flask or has_fastapi):
            return ThoughtProcess(
                reasoning="Playwright not installed and server app detected — need Playwright for server testing",
                plan=["Skip server UI testing, perform HTML analysis if HTML files exist"],
                tool_calls=[],
                confidence=0.4 if has_html else 0.0
            )

        # Determine test strategy
        if has_flask or has_fastapi:
            strategy = "Start server, capture screenshot, stop server"
        elif has_html and self.playwright_available:
            strategy = "Open HTML file directly, capture screenshot + analyze HTML"
        elif has_html:
            strategy = "Analyze HTML structure (no Playwright — fallback mode)"
        else:
            strategy = "Skip (no testable UI)"

        return ThoughtProcess(
            reasoning=reasoning,
            plan=[
                "Detect project type",
                strategy,
                "Save results to project folder",
                "Report to CriticAgent"
            ],
            tool_calls=[],
            confidence=0.9 if is_web_project else 0.0
        )
    
    async def act(self, thought: ThoughtProcess, task: Task) -> AgentResponse:
        """Execute UI testing."""
        if thought.confidence < 0.3:
            return AgentResponse(
                content="UI testing skipped (not a web project)",
                success=True,
                metadata={"skipped": True}
            )

        project_dir = Path(task.context.get("project_dir", ""))
        files = task.context.get("files", [])

        # Create screenshots directory (parents=True to avoid FileNotFoundError)
        screenshots_dir = project_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = None
        html_report = None

        try:
            # Detect project type
            has_flask = any('flask' in f.lower() or 'app.py' in f for f in files)
            has_fastapi = any('fastapi' in f.lower() or 'main.py' in f for f in files)
            has_html = any(f.endswith('.html') for f in files)

            if self.playwright_available and (has_flask or has_fastapi):
                screenshot_path = await self._test_server_app(
                    project_dir, files, screenshots_dir, is_flask=has_flask
                )
            elif self.playwright_available and has_html:
                screenshot_path = await self._test_static_html(
                    project_dir, files, screenshots_dir
                )

            # Always run HTML analysis if HTML files exist
            if has_html:
                html_report = self._analyze_html_files(project_dir, files)

            # Fallback: HTML analysis only (no Playwright)
            if not self.playwright_available and has_html and html_report:
                print(f"[UITester] 📄 HTML analysis completed (no Playwright)")
                return AgentResponse(
                    content=f"UI analysis completed (fallback mode):\n{self._format_html_report(html_report)}",
                    success=True,
                    metadata={
                        "screenshot_path": None,
                        "html_report": html_report,
                        "mode": "fallback_analysis",
                    }
                )

            if screenshot_path:
                print(f"[UITester] ✅ Screenshot saved: {screenshot_path}")
                return AgentResponse(
                    content=f"UI test completed. Screenshot: {screenshot_path}",
                    success=True,
                    metadata={
                        "screenshot_path": str(screenshot_path),
                        "screenshot_exists": screenshot_path.exists(),
                        "html_report": html_report,
                    }
                )
            else:
                return AgentResponse(
                    content="UI test completed but no screenshot captured",
                    success=True,
                    metadata={"screenshot_path": None, "html_report": html_report}
                )

        except Exception as e:
            error_msg = str(e)
            print(f"[UITester] ❌ UI test error: {error_msg}")
            return AgentResponse(
                content=f"UI test failed: {error_msg}",
                success=False,
                error=error_msg,
                metadata={"screenshot_path": None}
            )
        finally:
            if self.server_process:
                self._stop_server()
    
    async def _test_server_app(
        self,
        project_dir: Path,
        files: list,
        screenshots_dir: Path,
        is_flask: bool
    ) -> Optional[Path]:
        """Test Flask/FastAPI app by starting server and capturing screenshot."""
        # Find main file
        main_file = None
        if is_flask:
            for f in files:
                if 'app.py' in f or 'main.py' in f:
                    main_file = project_dir / "src" / Path(f).name
                    break
        else:  # FastAPI
            for f in files:
                if 'main.py' in f:
                    main_file = project_dir / "src" / Path(f).name
                    break
        
        if not main_file or not main_file.exists():
            print("[UITester] ⚠️  Main file not found, skipping server test")
            return None

        # Start server on a dynamically allocated free port
        port = self._find_free_port()
        if not self._start_server(main_file, port, is_flask):
            return None
        
        # Wait for server to start
        await asyncio.sleep(3)
        
        # Capture screenshot
        url = f"http://localhost:{port}"
        screenshot_path = screenshots_dir / "homepage.png"
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                await page.goto(url, timeout=10000)
                await page.screenshot(path=str(screenshot_path), full_page=True)
                
                await browser.close()
                
            return screenshot_path
            
        except Exception as e:
            self._log(f"⚠️  Screenshot capture failed: {e}")
            return None
        finally:
            self._stop_server()
    
    async def _test_static_html(
        self,
        project_dir: Path,
        files: list,
        screenshots_dir: Path
    ) -> Optional[Path]:
        """Test static HTML by opening file directly with Playwright."""
        html_file = self._find_html_file(project_dir, files)
        if not html_file:
            print("[UITester] ⚠️  HTML file not found")
            return None

        screenshot_path = screenshots_dir / "page.png"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                file_url = f"file://{html_file.absolute()}"
                await page.goto(file_url, timeout=10000)
                await page.screenshot(path=str(screenshot_path), full_page=True)

                await browser.close()

            return screenshot_path

        except Exception as e:
            self._log(f"⚠️  Screenshot capture failed: {e}")
            return None
    
    def _start_server(self, main_file: Path, port: int, is_flask: bool) -> bool:
        """Start Flask or FastAPI server in background."""
        try:
            if is_flask:
                # Flask: python app.py
                env = os.environ.copy()
                env['FLASK_APP'] = str(main_file)
                env['FLASK_RUN_PORT'] = str(port)
                
                self.server_process = subprocess.Popen(
                    ['python', str(main_file)],
                    cwd=str(main_file.parent),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                # FastAPI: uvicorn main:app
                self.server_process = subprocess.Popen(
                    ['uvicorn', f'{main_file.stem}:app', '--port', str(port)],
                    cwd=str(main_file.parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            
            print(f"[UITester] 🚀 Server started on port {port}")
            return True
            
        except Exception as e:
            print(f"[UITester] ❌ Failed to start server: {e}")
            return False
    
    def _stop_server(self):
        """Stop the running server."""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
                print("[UITester] 🛑 Server stopped")
            except Exception as e:
                print(f"[UITester] ⚠️  Error stopping server: {e}")
                try:
                    self.server_process.kill()
                except:
                    pass
            finally:
                self.server_process = None

    @staticmethod
    def _find_free_port() -> int:
        """Find a free TCP port using the OS."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def _find_html_file(self, project_dir: Path, files: list) -> Optional[Path]:
        """Find the best HTML file to test."""
        html_file = None
        # Prefer index.html or main.html
        for f in files:
            if f.endswith('.html') and ('index' in f.lower() or 'main' in f.lower()):
                html_file = project_dir / "src" / Path(f).name
                break
        # Fallback: any HTML file
        if not html_file:
            for f in files:
                if f.endswith('.html'):
                    html_file = project_dir / "src" / Path(f).name
                    break
        if html_file and html_file.exists():
            return html_file
        return None

    def _analyze_html_files(self, project_dir: Path, files: list) -> dict:
        """Analyze HTML files for quality checks without Playwright."""
        html_file = self._find_html_file(project_dir, files)
        if not html_file:
            return {"error": "No HTML file found"}

        try:
            content = html_file.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {"error": f"Cannot read {html_file.name}: {e}"}

        issues: list[str] = []
        checks_passed: list[str] = []

        # Title check
        title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if title_match and title_match.group(1).strip():
            checks_passed.append(f"Title: '{title_match.group(1).strip()}'")
        else:
            issues.append("Missing or empty <title> tag")

        # Charset check
        if re.search(r'<meta[^>]+charset\s*=', content, re.IGNORECASE):
            checks_passed.append("Charset meta tag present")
        else:
            issues.append("Missing charset meta tag")

        # Viewport check
        if re.search(r'<meta[^>]+name\s*=\s*["\']viewport["\']', content, re.IGNORECASE):
            checks_passed.append("Viewport meta tag present")
        else:
            issues.append("Missing viewport meta tag (not mobile-responsive)")

        # DOCTYPE check
        if content.strip().lower().startswith("<!doctype"):
            checks_passed.append("DOCTYPE declaration present")
        else:
            issues.append("Missing <!DOCTYPE html> declaration")

        # lang attribute
        if re.search(r'<html[^>]+lang\s*=', content, re.IGNORECASE):
            checks_passed.append("HTML lang attribute present")
        else:
            issues.append("Missing lang attribute on <html> tag (accessibility)")

        # Image alt attributes
        imgs = re.findall(r'<img\b([^>]*)>', content, re.IGNORECASE)
        imgs_without_alt = [i for i in imgs if 'alt=' not in i.lower()]
        if imgs:
            if imgs_without_alt:
                issues.append(f"{len(imgs_without_alt)}/{len(imgs)} <img> tags missing alt attribute")
            else:
                checks_passed.append(f"All {len(imgs)} images have alt attributes")

        # Broken href="#" links
        hash_links = re.findall(r'href\s*=\s*["\']#["\']', content, re.IGNORECASE)
        if hash_links:
            issues.append(f"{len(hash_links)} links with href='#' (placeholder links)")

        return {
            "file": html_file.name,
            "checks_passed": checks_passed,
            "issues": issues,
            "total_checks": len(checks_passed) + len(issues),
            "score": len(checks_passed) / max(len(checks_passed) + len(issues), 1),
        }

    @staticmethod
    def _format_html_report(report: dict) -> str:
        """Format HTML analysis report as readable text."""
        if "error" in report:
            return f"HTML Analysis Error: {report['error']}"

        lines = [f"HTML Analysis: {report.get('file', '?')}"]
        lines.append(f"Score: {report['score']:.0%} ({len(report['checks_passed'])} passed, {len(report['issues'])} issues)")

        if report["checks_passed"]:
            lines.append("\nPassed:")
            for check in report["checks_passed"]:
                lines.append(f"  + {check}")
        if report["issues"]:
            lines.append("\nIssues:")
            for issue in report["issues"]:
                lines.append(f"  - {issue}")

        return "\n".join(lines)

    def _log(self, message: str, level: str = "info"):
        """Log message with UITester prefix."""
        print(f"[UITester] {message}")
