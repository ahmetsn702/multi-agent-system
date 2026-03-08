"""
main.py — Multi-Agent Orchestration System Entry Point

Usage:
  python main.py              -> Interactive mode
  python main.py --demo       -> Run Hacker News demo
  python main.py "your goal"  -> Run a single goal directly
"""
import argparse
import asyncio
import os
import sys

# Ensure we can import from the project root
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from core.message_bus import bus
from agents.planner_agent import PlannerAgent
from agents.researcher_agent import ResearcherAgent
from agents.coder_agent import CoderAgent
from agents.critic_agent import CriticAgent
from agents.executor_agent import ExecutorAgent
from agents.profiler_agent import ProfilerAgent
from core.orchestrator import Orchestrator
from ui.cli import AgentCLI, print_banner


def check_api_key():
    """Warn if OpenRouter API key is not set."""
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        print(
            "\n⚠️  WARNING: OPENROUTER_API_KEY is not set!\n"
            "  Add it to your .env file.\n"
        )
        return False
    return True


def build_agents() -> dict:
    """Instantiate all agents and attach to the shared message bus."""
    return {
        "planner": PlannerAgent(bus=bus),
        "researcher": ResearcherAgent(bus=bus),
        "coder": CoderAgent(bus=bus),
        "critic": CriticAgent(bus=bus),
        "executor": ExecutorAgent(bus=bus),
    }


async def run_interactive():
    """Start the interactive CLI."""
    cli = AgentCLI()
    agents = build_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator
    await cli.run_interactive()


async def run_single_goal(goal: str):
    """Run a single goal non-interactively."""
    cli = AgentCLI()
    agents = build_agents()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator
    print_banner()
    await cli.run_goal(goal)


async def run_demo():
    """Run the demo Hacker News scenario."""
    from ui.cli import run_demo as _run_demo
    await _run_demo()


async def run_profile():
    """Run the Profiler Agent — scans workspace and generates user_profile.txt."""
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
    parser.add_argument("--demo", action="store_true", help="Run the Hacker News demo scenario")
    parser.add_argument("--profile", action="store_true", help="Analyze workspace and generate user_profile.txt")
    parser.add_argument("--no-key-check", action="store_true", help="Skip API key check")

    args = parser.parse_args()

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
