"""Cybertron CLI"""
import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from cybertron.core import ExecutionEngine
from cybertron.agents import CybertronOrchestrator
from cybertron.ui.tui import CybertronTUI

app = typer.Typer(help="Cybertron v2.0 - Advanced Security & RE Framework")
console = Console()


def print_banner():
    banner = r"""
     ____      _                  _             
    / ___|   _| |__  _ __ ___  ___| |_ ___ _ __ 
   | |  | | | | '_ \| '__/ _ \/ __| __/ _ \ '__|
   | |__| |_| | |_) | | |  __/\__ \ ||  __/ |   
    \____\__, |_.__/|_|  \___||___/\__\___|_|   
          |___/                                    v2.0
    """
    console.print(Panel(Text(banner, style="cyan bold"), border_style="cyan"))


@app.callback()
def main_callback():
    print_banner()


@app.command()
def scan(
    target: str = typer.Argument(..., help="Target domain/IP/file"),
    plugin: str = typer.Option("subdomain_enum", "--plugin", "-p"),
    scope: Optional[Path] = typer.Option(None, "--scope", "-s"),
):
    """Run a single security scan."""
    async def _run():
        engine = ExecutionEngine()
        if scope:
            engine.scope.load_scope(scope)
        result = await engine.execute_task(plugin, target)

        table = Table(title=f"Scan Results: {target}")
        table.add_column("Severity", style="red")
        table.add_column("Title")
        table.add_column("Category")

        for f in result.findings:
            color = {"critical": "red", "high": "bright_red", "medium": "yellow",
                     "low": "green", "info": "blue"}.get(f.severity.value, "white")
            table.add_row(f"[{color}]{f.severity.value}[/{color}]", f.title, f.category)

        console.print(table)
        console.print(f"Execution time: {result.execution_time_ms:.2f}ms")

    asyncio.run(_run())


@app.command()
def tui():
    """Launch the interactive TUI."""
    async def _run():
        engine = ExecutionEngine()
        tui_app = CybertronTUI(engine)
        await tui_app.run_async()
    asyncio.run(_run())


@app.command()
def engage(
    name: str = typer.Argument(...),
    target: str = typer.Argument(...),
    scope: Path = typer.Argument(...),
    type: str = typer.Option("bug_bounty", "--type", "-t"),
):
    """Start a full engagement."""
    async def _run():
        engine = ExecutionEngine()
        orch = CybertronOrchestrator(engine)
        eng = await orch.start_engagement(name, target, str(scope))
        console.print(f"[green]Engagement started: {eng.id}[/green]")
        if type == "bug_bounty":
            results = await orch.run_bug_bounty_pipeline(eng.id, target)
        else:
            console.print("[red]Unknown engagement type[/red]")
            return
        total = sum(len(r.findings) for r in results)
        console.print(f"[blue]Completed {len(results)} tasks with {total} findings[/blue]")
    asyncio.run(_run())


@app.command()
def plugins():
    """List all available plugins."""
    engine = ExecutionEngine()
    table = Table(title="Available Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Description")
    for p in engine.registry.list_plugins():
        table.add_row(p["name"], p["version"], p["description"])
    console.print(table)


def main():
    app()


if __name__ == "__main__":
    main()
