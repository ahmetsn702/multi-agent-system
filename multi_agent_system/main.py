"""
main.py — Multi-Agent Orchestration System Entry Point

Usage:
  python main.py              -> Interactive mode
  python main.py --demo       -> Run Hacker News demo
  python main.py "your goal"  -> Run a single goal directly
"""
import argparse
import asyncio
import atexit
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import dotenv_values, load_dotenv

# Load environment variables from .env
load_dotenv()


PID_FILE_ENV = "MULTI_AGENT_PID_FILE"
_ACTIVE_LLM_PROVIDER = None
VERTEX_FALLBACK_ROUTING = {
    "planner": {"model": "blackboxai/anthropic/claude-sonnet-4.6", "provider": "blackbox"},
    "architect": {"model": "blackboxai/anthropic/claude-haiku-4.5", "provider": "blackbox"},
    "coder": {"model": "blackboxai/anthropic/claude-haiku-4.5", "provider": "blackbox"},
    "coder_fast": {"model": "blackboxai/anthropic/claude-haiku-4.5", "provider": "blackbox"},
    "critic": {"model": "blackboxai/anthropic/claude-sonnet-4.6", "provider": "blackbox"},
    "researcher": {"model": "blackboxai/anthropic/claude-haiku-4.5", "provider": "blackbox"},
    "executor": {"model": "blackboxai/anthropic/claude-haiku-4.5", "provider": "blackbox"},
    "optimizer": {"model": "blackboxai/anthropic/claude-haiku-4.5", "provider": "blackbox"},
    "orchestrator": {"model": "blackboxai/anthropic/claude-sonnet-4.6", "provider": "blackbox"},
}


def get_logs_dir() -> Path:
    """Return the runtime logs directory relative to the current working directory."""
    logs_dir = Path.cwd() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _load_vertex_project_from_env_file() -> str:
    project = os.getenv("VERTEX_PROJECT", "").strip()
    if project:
        return project

    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return ""

    env_values = dotenv_values(env_path)
    project = str(env_values.get("VERTEX_PROJECT") or "").strip()
    if project:
        os.environ["VERTEX_PROJECT"] = project
    return project


def configure_llm_provider() -> str:
    global _ACTIVE_LLM_PROVIDER

    if _ACTIVE_LLM_PROVIDER:
        return _ACTIVE_LLM_PROVIDER

    project = _load_vertex_project_from_env_file()
    if project:
        os.environ.setdefault("VERTEX_LOCATION", "us-central1")
        print(f"[LLM] Vertex AI etkin: project={project}, location={os.getenv('VERTEX_LOCATION')}")
        _ACTIVE_LLM_PROVIDER = "vertex"
        return _ACTIVE_LLM_PROVIDER

    from config.settings import MODEL_ROUTING

    for agent_id, fallback in VERTEX_FALLBACK_ROUTING.items():
        current = MODEL_ROUTING.get(agent_id)
        if isinstance(current, dict) and current.get("provider") == "vertex":
            MODEL_ROUTING[agent_id] = dict(fallback)

    print("[LLM] VERTEX_PROJECT bulunamadi; Blackbox fallback etkin.")
    _ACTIVE_LLM_PROVIDER = "blackbox"
    return _ACTIVE_LLM_PROVIDER


def generate_session_id() -> str:
    """Create a short session identifier for background jobs."""
    return uuid.uuid4().hex[:8]


def cleanup_pid_file() -> None:
    """Remove the current background pid file on shutdown if one was registered."""
    pid_file = os.getenv(PID_FILE_ENV, "").strip()
    if not pid_file:
        return

    try:
        Path(pid_file).unlink(missing_ok=True)
    except OSError:
        pass


def register_background_cleanup() -> None:
    """Register exit handlers for background child processes."""
    pid_file = os.getenv(PID_FILE_ENV, "").strip()
    if not pid_file:
        return

    atexit.register(cleanup_pid_file)
    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, lambda *_args: sys.exit(0))
        except (OSError, RuntimeError, ValueError):
            continue


def is_pid_running(pid: int) -> bool:
    """Check whether a PID is still alive."""
    if pid <= 0:
        return False

    if os.name == "nt":
        try:
            import ctypes

            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False

            try:
                exit_code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def get_background_python_executable() -> str:
    """Use the current Python interpreter for background processes."""
    return sys.executable


def start_background_goal(args: argparse.Namespace) -> None:
    """Launch the current goal in a detached subprocess and return immediately."""
    if not args.goal:
        raise ValueError("--background requires a goal.")

    session_id = generate_session_id()
    logs_dir = get_logs_dir()
    log_path = logs_dir / f"{session_id}.log"
    pid_path = logs_dir / f"{session_id}.pid"

    command = [get_background_python_executable(), "-u", str(Path(__file__).resolve())]
    if args.no_key_check:
        command.append("--no-key-check")
    command.append(args.goal)

    child_env = os.environ.copy()
    child_env[PID_FILE_ENV] = str(pid_path.resolve())
    child_env["MULTI_AGENT_BACKGROUND"] = "1"

    popen_kwargs = {
        "stdin": subprocess.DEVNULL,
        "cwd": str(Path.cwd()),
        "env": child_env,
    }

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = 0
        popen_kwargs["startupinfo"] = startupinfo
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        popen_kwargs["close_fds"] = True
    else:
        popen_kwargs["start_new_session"] = True

    with log_path.open("a", encoding="utf-8", buffering=1) as log_file:
        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=log_file,
            **popen_kwargs,
        )

    pid_path.write_text(str(process.pid), encoding="utf-8")
    print(f"Görev arka planda başlatıldı. Log: logs/{session_id}.log")


def show_background_status() -> None:
    """Show currently active background jobs from logs/*.pid."""
    logs_dir = get_logs_dir()
    active_jobs = []

    for pid_path in sorted(logs_dir.glob("*.pid"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue

        if not is_pid_running(pid):
            continue

        session_id = pid_path.stem
        active_jobs.append((session_id, pid))

    if not active_jobs:
        print("Aktif arka plan gorevi yok.")
        return

    print("Aktif arka plan gorevleri:")
    for session_id, pid in active_jobs:
        print(f"- Session: {session_id} | PID: {pid} | Log: logs/{session_id}.log")


def follow_latest_log() -> None:
    """Follow the most recent log file similar to tail -f."""
    logs_dir = get_logs_dir()
    log_files = list(logs_dir.glob("*.log"))
    if not log_files:
        print("Takip edilecek log dosyasi bulunamadi.")
        return

    latest_log = max(log_files, key=lambda item: item.stat().st_mtime)
    print(f"Takip ediliyor: logs/{latest_log.name} (Ctrl+C ile cik)")

    try:
        with latest_log.open("r", encoding="utf-8", errors="replace") as log_file:
            while True:
                line = log_file.readline()
                if line:
                    print(line, end="", flush=True)
                    continue
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nLog takibi durduruldu.")


def check_api_key():
    """Warn if the active provider is missing required credentials."""
    provider = configure_llm_provider()
    if provider == "vertex":
        return True

    key = os.getenv("BLACKBOX_API_KEY", "")
    if not key:
        print(
            "\n⚠️  WARNING: BLACKBOX_API_KEY is not set!\n"
            "  Add it to your .env file.\n"
        )
        return False
    return True


def build_agents() -> dict:
    """Instantiate all agents and attach to the shared message bus."""
    configure_llm_provider()
    from core.message_bus import bus
    from agents.planner_agent import PlannerAgent
    from agents.researcher_agent import ResearcherAgent
    from agents.architect_agent import ArchitectAgent
    from agents.coder_agent import CoderAgent
    from agents.critic_agent import CriticAgent
    from agents.security_agent import SecurityAgent
    from agents.optimizer_agent import OptimizerAgent
    from agents.docs_agent import DocsAgent
    from agents.executor_agent import ExecutorAgent
    from agents.builder_agent import BuilderAgent

    return {
        "planner": PlannerAgent(bus=bus),
        "researcher": ResearcherAgent(bus=bus),
        "architect": ArchitectAgent(bus=bus),
        "coder": CoderAgent(agent_id="coder", bus=bus),
        "coder_fast": CoderAgent(agent_id="coder_fast", bus=bus),
        "critic": CriticAgent(bus=bus),
        "security": SecurityAgent(bus=bus),
        "optimizer": OptimizerAgent(bus=bus),
        "docs": DocsAgent(bus=bus),
        "executor": ExecutorAgent(bus=bus),
        "builder": BuilderAgent(bus=bus),
        # "analyzer": AnalyzerAgent(bus=bus),  # DEVRE DIŞI
    }


async def run_interactive():
    """Start the interactive CLI."""
    from core.orchestrator import Orchestrator
    from ui.cli import AgentCLI

    cli = AgentCLI()
    agents = build_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator
    await cli.run_interactive()


async def run_single_goal(goal: str):
    """Run a single goal non-interactively."""
    from core.orchestrator import Orchestrator
    from ui.cli import AgentCLI, print_banner

    # Cluster mode kontrolü
    use_cluster = os.getenv("CLUSTER_MODE", "false").lower() == "true"
    
    if use_cluster:
        from core.cluster_manager import should_use_clusters, run_with_clusters
        if should_use_clusters(goal):
            print(f"[Main] 🔀 Cluster modu aktif — 2 model yarışıyor")
            result = await run_with_clusters(goal)
            print(f"\n✅ Cluster modu tamamlandı!")
            print(f"Kazanan: {result.get('cluster_label', '?')}")
            print(f"Maliyet: ${result.get('cost_usd', 0):.4f}")
            return
    
    # Normal mod
    cli = AgentCLI()
    agents = build_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator
    print_banner()
    await cli.run_goal(goal)


async def run_goal_async(goal: str, log_callback=None):
    """
    Async wrapper for Telegram Bot and external integrations.
    Returns orchestrator result dict.
    """
    from core.orchestrator import Orchestrator

    agents = build_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=log_callback)
    result = await orchestrator.run(goal)
    return result


async def run_demo():
    """Run the demo Hacker News scenario."""
    from ui.cli import run_demo as _run_demo
    await _run_demo()


async def run_profile():
    """Run the Profiler Agent — scans workspace and generates user_profile.txt."""
    from agents.profiler_agent import ProfilerAgent
    from rich.console import Console

    console = Console()
    console.print("[bold cyan]\n🔍 Profil Analisti başlatılıyor...\n[/bold cyan]")
    profiler = ProfilerAgent()
    path = await profiler.generate_profile()
    if path:
        console.print(f"[bold green]✅ Profil kaydedildi:[/bold green] {path}")
    else:
        console.print("[bold red]❌ Profil oluşturulamadı.[/bold red]")


def main():
    register_background_cleanup()

    parser = argparse.ArgumentParser(
        description="Multi-Agent Orchestration System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                  # Interactive mode
  python main.py --demo                           # Run Hacker News demo
  python main.py "Summarize the latest AI news"   # Direct goal
        """,
    )
    parser.add_argument("goal", nargs="?", help="Goal to process (optional)")
    parser.add_argument("-b", "--background", action="store_true", help="Run a goal in a detached background process")
    parser.add_argument("--demo", action="store_true", help="Run the Hacker News demo scenario")
    parser.add_argument("--status", action="store_true", help="Show active background jobs from logs/")
    parser.add_argument("--log", action="store_true", help="Follow the most recent log file from logs/")
    parser.add_argument("--profile", action="store_true", help="Analyze workspace and generate user_profile.txt")
    parser.add_argument("--no-key-check", action="store_true", help="Skip API key check")

    args = parser.parse_args()

    if args.background and not args.goal:
        parser.error("--background only works with a goal.")

    if args.background and (args.demo or args.profile):
        parser.error("--background cannot be combined with --demo or --profile.")

    if args.background and (args.status or args.log):
        parser.error("--background cannot be combined with --status or --log.")

    if args.status and args.log:
        parser.error("--status and --log cannot be combined.")

    if args.status and (args.goal or args.demo or args.profile):
        parser.error("--status cannot be combined with goal, --demo, or --profile.")

    if args.log and (args.goal or args.demo or args.profile):
        parser.error("--log cannot be combined with goal, --demo, or --profile.")

    if args.status:
        show_background_status()
        return

    if args.log:
        follow_latest_log()
        return

    if args.background:
        start_background_goal(args)
        return

    if not args.no_key_check:
        key_ok = check_api_key()
        if not key_ok and not args.demo:
            # Still allow running in demo/test mode without a real key
            pass

    if args.demo:
        asyncio.run(run_demo())
    elif args.profile:
        asyncio.run(run_profile())
    elif args.goal:
        asyncio.run(run_single_goal(args.goal))
    else:
        asyncio.run(run_interactive())


if __name__ == "__main__":
    main()

