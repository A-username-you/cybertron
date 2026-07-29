"""Cybertron TUI"""
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, DataTable, Log, Static, Input, Button, TabbedContent, TabPane
from textual.reactive import reactive
from cybertron.core import ExecutionEngine


class CybertronTUI(App):
    CSS = """
    Screen { align: center middle; }
    DataTable { height: 1fr; }
    Log { height: 1fr; }
    #sidebar { width: 30%; }
    #main { width: 70%; }
    .title { text-align: center; text-style: bold; color: $primary; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    findings = reactive([])

    def __init__(self, engine: ExecutionEngine):
        super().__init__()
        self.engine = engine

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("Cybertron v2.0", classes="title")
                yield Input(placeholder="Target", id="target_input")
                yield Button("Run Recon", id="btn_recon")
                yield Button("Run Port Scan", id="btn_portscan")
            with Vertical(id="main"):
                with TabbedContent():
                    with TabPane("Findings", id="findings"):
                        yield DataTable(id="findings_table")
                    with TabPane("Log", id="log"):
                        yield Log(id="log_widget")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#findings_table", DataTable)
        table.add_columns("Severity", "Category", "Target", "Title")
        self.query_one("#log_widget", Log).write_line("[INIT] Cybertron v2.0 ready")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        target = self.query_one("#target_input", Input).value
        log = self.query_one("#log_widget", Log)
        table = self.query_one("#findings_table", DataTable)
        if not target:
            log.write_line("[ERROR] No target")
            return
        plugin_map = {"btn_recon": "subdomain_enum", "btn_portscan": "port_scan"}
        plugin = plugin_map.get(event.button.id)
        if not plugin:
            return
        result = await self.engine.execute_task(plugin, target)
        log.write_line(f"[INFO] {result.status.name} ({len(result.findings)} findings)")
        for finding in result.findings:
            table.add_row(finding.severity.value, finding.category, finding.target, finding.title)
