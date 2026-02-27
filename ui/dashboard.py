"""
ui/dashboard.py
Rich-based live status panels for the multi-agent system.
Provides reusable panels: AgentStatusTable, MessageBusLog, TokenCounter.
"""
from datetime import datetime
from typing import Any

from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text


STATUS_COLORS = {
    "IDLE": "green",
    "THINKING": "yellow",
    "ACTING": "cyan",
    "WAITING": "blue",
    "ERROR": "red",
}

STATUS_ICONS = {
    "IDLE": "⬜",
    "THINKING": "🧠",
    "ACTING": "⚡",
    "WAITING": "⏳",
    "ERROR": "❌",
}


def make_agent_table(agent_statuses: list[dict]) -> Table:
    """Create a Rich table showing all agent statuses."""
    table = Table(title="🤖 Ajan Durumları", border_style="bright_blue", expand=True)
    table.add_column("Ajan", style="bold white")
    table.add_column("Rol", style="dim")
    table.add_column("Durum", justify="center")
    table.add_column("Bellek", justify="right", style="dim")

    for agent in agent_statuses:
        status = agent.get("status", "IDLE")
        color = STATUS_COLORS.get(status, "white")
        icon = STATUS_ICONS.get(status, "•")
        table.add_row(
            agent.get("name", "Unknown"),
            agent.get("role", ""),
            Text(f"{icon} {status}", style=color),
            str(agent.get("memory_size", 0)),
        )
    return table


def make_message_log_panel(messages: list[dict], max_entries: int = 8) -> Panel:
    """Create a panel showing recent message bus activity."""
    recent = messages[-max_entries:]
    lines = []
    for msg in recent:
        ts = msg.get("timestamp", "")[:19].replace("T", " ")
        from_a = msg.get("from_agent", "?")
        to_a = msg.get("to_agent", "?")
        mtype = msg.get("type", "?")
        content_preview = str(msg.get("content", ""))[:40]
        lines.append(
            f"[dim]{ts}[/dim] [cyan]{from_a}[/cyan] → [green]{to_a}[/green] "
            f"[[yellow]{mtype}[/yellow]] {content_preview}"
        )

    content = "\n".join(lines) if lines else "[dim]Henüz mesaj yok[/dim]"
    return Panel(content, title="📡 Mesaj Veriyolu (Message Bus)", border_style="magenta", expand=True)


def make_token_panel(token_data: dict[str, dict], cost_usd: float) -> Panel:
    """Create a panel showing token usage and estimated cost."""
    from config.settings import MODEL_ROUTING
    from tools.web_search import cache_stats

    table = Table(title="💰 Maliyet Takibi", show_header=True, header_style="bold", expand=True, border_style="green")
    table.add_column("Ajan", style="cyan")
    table.add_column("Model", style="magenta")
    table.add_column("Prompt", justify="right")
    table.add_column("Tamamlama", justify="right")
    table.add_column("Toplam", justify="right", style="bold")
    table.add_column("Maliyet ($)", justify="right", style="bold green")

    total_all = 0
    calculated_cost = 0.0
    for agent_id, usage in token_data.items():
        total = usage.get("total_tokens", 0)
        cost = usage.get("total_cost", 0.0)
        total_all += total
        calculated_cost += cost
        
        model_name = MODEL_ROUTING.get(agent_id, "N/A")
        
        table.add_row(
            agent_id,
            str(model_name),
            str(usage.get("prompt_tokens", 0)),
            str(usage.get("completion_tokens", 0)),
            str(total),
            f"${cost:.6f}"
        )

    table.add_row("─" * 10, "─" * 10, "─" * 8, "─" * 12, "─" * 8, "─" * 10)
    table.add_row(
        "[bold]TOPLAM[/bold]", "", "", "", f"[bold]{total_all}[/bold]", f"[bold]${calculated_cost:.6f}[/bold]"
    )

    budget_remaining = 100.0 - calculated_cost
    
    hits = cache_stats.get("hits", 0)
    total_q = cache_stats.get("total_queries", 0)
    hit_rate = (hits / total_q * 100) if total_q > 0 else 0.0

    footer = (
        f"\n💵 Oturum Maliyeti: [bold green]${calculated_cost:.6f}[/bold green] | "
        f"Kalan Bütçe: [bold cyan]${budget_remaining:.6f}[/bold cyan] (Max $100)\n"
        f"🧠 Cache Tasarrufu: {hits} çağrı engellendi | Hit Rate: %{hit_rate:.1f}"
    )
    return Panel(
        Group(table, Text(footer, justify="center")),
        title="📊 Sistem Kaynak Kullanımı",
        border_style="green",
        expand=True,
    )


def make_thought_trace_panel(thoughts: list[str], agent_name: str) -> Panel:
    """Show the active agent's thought trace."""
    content = "\n".join(f"  {t}" for t in thoughts[-10:]) if thoughts else "[dim]Bekleniyor...[/dim]"
    return Panel(
        content,
        title=f"💭 {agent_name} Düşünce Akışı",
        border_style="yellow",
        expand=True,
    )


def make_progress_bar(completed: int, total: int) -> Progress:
    """Create a progress bar for task completion."""
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    )
    task_id = progress.add_task("Tasks", total=total)
    progress.update(task_id, completed=completed)
    return progress
