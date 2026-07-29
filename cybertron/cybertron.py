#!/usr/bin/env python3
"""
Cybertron Launcher — unified entry point for Gateway, TUI, GUI, and Web UI
Usage:
    python cybertron.py gateway    # Start the gateway server
    python cybertron.py tui        # Start the terminal UI
    python cybertron.py gui        # Start the desktop GUI
    python cybertron.py web        # Serve the web UI on a local port
"""
import sys
import os
import subprocess
import http.server
import socketserver
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

def run_gateway():
    subprocess.run([sys.executable, str(SCRIPT_DIR / "gateway.py")])

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
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nNo command provided. Use one of: gateway, tui, gui, web")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    commands = {
        "gateway": run_gateway,
        "server": run_gateway,
        "tui": run_tui,
        "gui": run_gui,
        "web": run_web,
        "desktop": run_gui,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print("Available: gateway, tui, gui, web")
        sys.exit(1)

if __name__ == "__main__":
    main()
