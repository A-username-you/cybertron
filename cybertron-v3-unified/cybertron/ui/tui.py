"""Cybertron TUI — Terminal User Interface."""
import asyncio
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import Header, Footer, Static, Button, Input, Log, DataTable, TabbedContent, TabPane, Label
from textual.reactive import reactive
from cybertron.core.engine import CybertronEngine
from cybertron.core.protocol import AgentState


class PixelCanvas(Static):
    """ASCII pixel-art state display."""
    state = reactive(AgentState.IDLE)

    def render(self):
        icons = {
            AgentState.IDLE: """
    [gold1]  .-.
   (o o)
    |O|
   /   \
  '-----'
    [/gold1]""",
            AgentState.THINKING: """
    [gold1]  .-.
   (o o)  ~
    |O|   ~
   /   \
  '-----'
    [/gold1]""",
            AgentState.WRITING: """
    [gold1]  .-.
   (o o)  *
    |O|   *
   /   \
  '-----'
    [/gold1]""",
            AgentState.RESULT: """
    [gold1]  .-.
   (o o)  [bright_green]✓[/bright_green]
    |O|
   /   \
  '-----'
    [/gold1]""",
            AgentState.ERROR: """
    [gold1]  .-.
   (o o)  [red]✗[/red]
    |O|
   /   \
  '-----'
    [/gold1]""",
        }
        return icons.get(self.state, icons[AgentState.IDLE])


class CybertronTUI(App):
    """Cybertron Terminal UI with pixel-art state icons."""

    CSS = """
    Screen { align: center middle; }
    #main { width: 100%; height: 100%; }
    #sidebar { width: 30%; height: 100%; border-right: solid $primary; padding: 1; }
    #content { width: 70%; height: 100%; padding: 1; }
    #pixel-canvas { height: auto; content-align: center middle; }
    #log { height: 60%; border: solid $primary; }
    #input-bar { height: auto; margin-top: 1; }
    .title { text-style: bold; color: $primary; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "recon", "Recon"),
        ("s", "scan", "Scan"),
        ("b", "brute", "Brute"),
        ("e", "exploit", "Exploit"),
        ("f", "forensics", "Forensics"),
        ("v", "reverse", "Reverse"),
        ("h", "hunt", "Hunt"),
    ]

    def __init__(self):
        super().__init__()
        self.engine = CybertronEngine()
        self.engine.on_state_change(self._on_state_change)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Label("[bold gold1]Cybertron[/bold gold1] [dim]v3.0[/dim]", classes="title")
                yield Label("")
                yield PixelCanvas(id="pixel-canvas")
                yield Label("")
                yield Button("Recon (r)", id="btn-recon", variant="primary")
                yield Button("Scan (s)", id="btn-scan")
                yield Button("Brute (b)", id="btn-brute")
                yield Button("Exploit (e)", id="btn-exploit")
                yield Button("Forensics (f)", id="btn-forensics")
                yield Button("Reverse (v)", id="btn-reverse")
                yield Button("Hunt (h)", id="btn-hunt")
            with Vertical(id="content"):
                with TabbedContent():
                    with TabPane("Console", id="tab-console"):
                        yield Log(id="log")
                        with Horizontal(id="input-bar"):
                            yield Input(placeholder="Enter target or command...", id="cmd-input")
                            yield Button("Run", id="btn-run", variant="success")
                    with TabPane("Findings", id="tab-findings"):
                        yield DataTable(id="findings-table")
                    with TabPane("Config", id="tab-config"):
                        yield Static("Use 'cybertron config' to manage settings.")
        yield Footer()

    def on_mount(self):
        self.query_one("#log", Log).write("[gold1]Cybertron[/gold1] v3.0 TUI loaded.")
        self.query_one("#log", Log).write("Press a button or type a command.")
        table = self.query_one("#findings-table", DataTable)
        table.add_columns("Severity", "Title", "Target", "Time")

    def _on_state_change(self, msg):
        self.query_one("#pixel-canvas", PixelCanvas).state = msg.state
        self.query_one("#log", Log).write(f"[{msg.state.value}] {msg.content}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        log = self.query_one("#log", Log)
        inp = self.query_one("#cmd-input", Input)
        target = inp.value or "example.com"

        if btn_id == "btn-recon":
            log.write(f"[cyan]Starting recon on {target}...[/cyan]")
            await asyncio.to_thread(self._run_recon, target)
        elif btn_id == "btn-scan":
            log.write(f"[cyan]Starting scan on {target}...[/cyan]")
            await asyncio.to_thread(self._run_scan, target)
        elif btn_id == "btn-brute":
            log.write(f"[cyan]Starting brute on {target}...[/cyan]")
            await asyncio.to_thread(self._run_brute, target)
        elif btn_id == "btn-exploit":
            log.write(f"[red]Exploitation requires approval.[/red]")
        elif btn_id == "btn-forensics":
            log.write(f"[cyan]Starting forensics...[/cyan]")
        elif btn_id == "btn-reverse":
            log.write(f"[cyan]Starting reverse engineering...[/cyan]")
        elif btn_id == "btn-hunt":
            log.write(f"[cyan]Starting threat hunt...[/cyan]")
        elif btn_id == "btn-run":
            log.write(f">>> {target}")

    def _run_recon(self, target):
        from cybertron.red_team.recon import ReconEngine
        engine = ReconEngine(target=target)
        engine.run()

    def _run_scan(self, target):
        from cybertron.red_team.scanner import VulnScanner
        scanner = VulnScanner(target=target)
        scanner.run()

    def _run_brute(self, target):
        from cybertron.red_team.brute_force import BruteForceEngine
        engine = BruteForceEngine(target=target, mode="dirs")
        engine.run()

    def action_recon(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-recon'})})())

    def action_scan(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-scan'})})())

    def action_brute(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-brute'})})())

    def action_exploit(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-exploit'})})())

    def action_forensics(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-forensics'})})())

    def action_reverse(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-reverse'})})())

    def action_hunt(self):
        self.on_button_pressed(type('Event', (), {'button': type('Btn', (), {'id': 'btn-hunt'})})())

    def run(self):
        super().run()
