#!/usr/bin/env python3
"""
Cybertron Python UI Launcher
==============================
Unified entry point for the Python-based TUI, GUI, and Web UI.
Connects to the existing Node.js runtime gateway.

Usage:
    python cybertron_ui.py tui        # Terminal UI (Rich)
    python cybertron_ui.py gui        # Desktop GUI (Tkinter)
    python cybertron_ui.py web        # Serve web UI on local port
    python cybertron_ui.py --help     # Show this help

NEW: GitHub Tool Loader commands (in all UIs):
    /add-tool <github-url> [category]   Install a tool from GitHub releases
    /tools                              View installed tool registry
    /marketplace                        Browse curated security tools
    /remove-tool <id>                   Remove an installed tool
    /help                               Show available commands
"""
import sys
import os
import subprocess
import http.server
import socketserver
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

def run_tui():
    subprocess.run([sys.executable, str(SCRIPT_DIR / "tui.py")])

def run_gui():
    subprocess.run([sys.executable, str(SCRIPT_DIR / "gui.py")])

def run_web():
    os.chdir(SCRIPT_DIR)
    PORT = int(os.environ.get("CYBERTRON_WEB_PORT", "8080"))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        print(f"\n[Cybertron] Web UI serving at http://127.0.0.1:{PORT}/web_ui.html")
        print(f"[Cybertron] Press Ctrl+C to stop\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Cybertron] Web server stopped.")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()
    commands = {
        "tui": run_tui,
        "gui": run_gui,
        "web": run_web,
        "desktop": run_gui,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print("Available: tui, gui, web")
        sys.exit(1)

if __name__ == "__main__":
    main()
