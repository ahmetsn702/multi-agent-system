"""
ui/cli.py
Rich-based interactive CLI for the Multi-Agent Orchestration System.
Shows live agent status, message bus log, token tracker, and final output.
"""
import asyncio
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text
from rich import print as rprint

from core.llm_client import token_tracker
from core.message_bus import bus
import sys
from ui.dashboard import (
    make_agent_table,
    make_message_log_panel,
    make_token_panel,
    make_thought_trace_panel,
    make_progress_bar,
)

# Windows üzerinde Türkçe/Kutu Çizimi karakterlerinin (cp1254) patlamasını engellemek için UTF-8 zorla:
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


def print_banner():
    """Print the startup banner."""
    console.print(Panel(
        Text.assemble(
            ("  ╔═══════════════════════════════════╗\n", "bright_blue"),
            ("  ║   Çoklu Ajan Orkestrasyon Sistemi   ║\n", "bold bright_white"),
            ("  ║    Powered by OpenRouter + Groq     ║\n", "bright_cyan"),  # updated: removed AWS refs
            ("  ╚═══════════════════════════════════╝\n", "bright_blue"),
            ("  Model: us.anthropic.claude-3-5-haiku-20241022-v1:0\n", "dim"),
            ("  Bağlam: 200,000 jeton (token)\n", "dim"),
        ),
        border_style="bright_blue",
    ))


def build_layout(agent_statuses: list[dict], messages: list[dict], thoughts: list[str], active_agent: str, progress: tuple) -> Layout:
    """Build the live dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="top", size=len(agent_statuses) + 5),
        Layout(name="middle", size=12),
        Layout(name="bottom", size=6),
    )

    # Top: agent status table
    layout["top"].update(make_agent_table(agent_statuses))

    # Middle: split between message log and thought trace
    layout["middle"].split_row(
        Layout(name="msglog"),
        Layout(name="thought"),
    )
    layout["middle"]["msglog"].update(make_message_log_panel(messages))
    layout["middle"]["thought"].update(make_thought_trace_panel(thoughts, active_agent))

    # Bottom: token usage
    token_data = token_tracker.get_all()
    cost = token_tracker.estimated_cost_usd()
    layout["bottom"].update(make_token_panel(token_data, cost))

    return layout


class AgentCLI:
    """
    Main CLI class. Manages the live Rich dashboard and user interaction.
    """

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self._thoughts: list[str] = []
        self._active_agent: str = "System"
        self._running = False

    def add_thought(self, agent_name: str, thought: str):
        """Add a thought trace entry."""
        self._active_agent = agent_name
        self._thoughts.append(f"[{agent_name}] {thought}")
        if len(self._thoughts) > 50:
            self._thoughts = self._thoughts[-50:]

    async def status_callback(self, message: str):
        """Callback for orchestrator status updates."""
        console.print(f"  [dim]{message}[/dim]")
        self._thoughts.append(message)

    async def run_interactive(self):
        """Launch interactive mode: prompt user, run orchestrator, display results."""
        print_banner()

        while True:
            console.print()
            console.print(Rule("[bright_blue]Yeni Oturum[/bright_blue]"))
            try:
                goal = Prompt.ask(
                    "[bold cyan]🎯 Hedefinizi girin[/bold cyan] (veya çıkmak için 'quit' yazın)"
                )
            except EOFError:
                console.print("\n[yellow]Girdi akışı (pipe) sonlandı. Çıkış yapılıyor... 👋[/yellow]")
                break

            if goal.lower() in ("quit", "exit", "q", "çık", "çıkış"):
                console.print("[yellow]Görüşmek üzere! 👋[/yellow]")
                break

            if not goal.strip():
                continue

            # /open komutu — mevcut projeyi yükle
            if goal.strip().startswith("/open "):
                project_path = goal.strip()[6:].strip().strip('"').strip("'")
                console.print(f"\n[bold cyan]📂 '{project_path}' taranıyor...[/bold cyan]")

                from tools.project_indexer import index_project
                index = index_project(project_path)

                if "error" in index:
                    console.print(f"[red]❌ {index['error']}[/red]")
                    continue

                console.print(f"[green]✅ {index['summary']}[/green]")
                console.print(f"\n[dim]{index['structure']}[/dim]\n")
                console.print("[bold]Proje yüklendi! Ne değiştirmek istiyorsun?[/bold]")
                console.print("[dim]Örnek: 'main.py içindeki debug modunu kapat'[/dim]")
                console.print("[dim]Örnek: 'Tüm fonksiyonlara docstring ekle'[/dim]\n")

                if self.orchestrator:
                    self.orchestrator.set_project_context(index)
                continue

            await self.run_goal(goal)

    async def run_goal(self, goal: str):
        """Run a single goal through the multi-agent system with live display."""
        console.print(f"\n[bold green]Başlatılıyor...[/bold green] [dim]{goal}[/dim]\n")
        self._thoughts = []

        if not self.orchestrator:
            console.print("[red]Orkestratör bulunamadı.[/red]")
            return

        # Run with live status updates
        try:
            result = await self.orchestrator.run(goal)
            self._display_result(result)
        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️  Kullanıcı tarafından durduruldu[/yellow]")
        except Exception as e:
            console.print(f"[red]Hata: {e}[/red]")

    def _display_result(self, result: dict):
        """Render the final result in the terminal."""
        console.print()
        console.print(Rule("[bold green]✅ Kesin Sonuç[/bold green]"))

        if result.get("success"):
            output = result.get("output", "Çıktı yok")
            console.print(Panel(
                Markdown(output),
                title=f"[bold green]Sonuç — {result.get('tasks_completed', 0)} görev tamamlandı[/bold green]",
                border_style="green",
                expand=True,
            ))

            # Session stats
            stats = [
                f"Oturum: [cyan]{result.get('session_id', 'Yok')}[/cyan]",
                f"İterasyon: [yellow]{result.get('iterations', 0)}[/yellow]",
                f"Görevler: [green]{result.get('tasks_completed', 0)}[/green]",
                f"Tahmini Maliyet: [magenta]${token_tracker.estimated_cost_usd():.6f} USD[/magenta]",
                f"Toplam Jeton: [blue]{sum(v['total_tokens'] for v in token_tracker.get_all().values())}[/blue]",
            ]
            console.print("  " + "  |  ".join(stats))
        else:
            console.print(Panel(
                f"[red]Hata: {result.get('error', 'Bilinmeyen hata')}[/red]",
                title="[red]Başarısız[/red]",
                border_style="red",
            ))

        console.print()


async def run_demo():
    """Run the Hacker News demo scenario to verify everything works."""
    from core.orchestrator import Orchestrator
    from agents.planner_agent import PlannerAgent
    from agents.researcher_agent import ResearcherAgent
    from agents.coder_agent import CoderAgent
    from agents.critic_agent import CriticAgent
    from agents.executor_agent import ExecutorAgent
    from core.message_bus import bus

    agents = {
        "planner": PlannerAgent(bus=bus),
        "researcher": ResearcherAgent(bus=bus),
        "coder": CoderAgent(bus=bus),
        "critic": CriticAgent(bus=bus),
        "executor": ExecutorAgent(bus=bus),
    }

    cli = AgentCLI()
    orchestrator = Orchestrator(agents=agents, status_callback=cli.status_callback)
    cli.orchestrator = orchestrator

    demo_goal = (
        "Hacker News üzerindeki ilk 10 hikayeyi çeken ve "
        "bunu bir JSON dosyasına kaydeden bir Python web kazıyıcı (scraper) yaz."
    )
    console.print(f"\n[bold yellow]🧪 Demo senaryosu çalıştırılıyor:[/bold yellow] {demo_goal}\n")
    await cli.run_goal(demo_goal)
