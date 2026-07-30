"""Cybertron Desktop GUI — Tkinter-based with server toggle."""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from pathlib import Path

from cybertron.core.config import CybertronConfig
from cybertron.core.engine import CybertronEngine
from cybertron.core.protocol import AgentState
from cybertron.security.auth import AuthManager


class PixelCanvas(tk.Canvas):
    """Pixel-art state icon canvas."""

    COLORS = {
        "gold": "#FFD700", "amber": "#FFBF00", "cyan": "#4DD0E1",
        "navy": "#1a1a3e", "bronze": "#CD7F32", "white": "#ffffff"
    }

    def __init__(self, parent, size=120):
        super().__init__(parent, width=size, height=size, bg="#0a0a1a", highlightthickness=0)
        self.size = size
        self.state = AgentState.IDLE
        self._job = None
        self._t = 0
        self.draw_idle()

    def draw_pixel(self, x, y, color, alpha=1.0):
        px = self.size / 28
        self.create_rectangle(x*px, y*px, (x+1)*px, (y+1)*px,
                              fill=color, outline="")

    def draw_idle(self):
        self.delete("all")
        cx, cy = 14, 14
        for y in range(28):
            for x in range(28):
                dx, dy = x - cx, y - cy
                r = (dx*dx + dy*dy) ** 0.5
                if r <= 5:
                    self.draw_pixel(x, y, self.COLORS["gold"])
                elif 7 <= r <= 9:
                    self.draw_pixel(x, y, self.COLORS["amber"])

    def draw_thinking(self, t):
        self.delete("all")
        cx, cy = 14, 14
        for y in range(28):
            for x in range(28):
                dx, dy = x - cx, y - cy
                r = (dx*dx + dy*dy) ** 0.5
                pulse = 1 + 0.1 * (1 + (t * 2) % 2)
                if r <= 5 * pulse:
                    self.draw_pixel(x, y, self.COLORS["gold"])
                ring_r = 8 + 2 * (t % 1)
                if abs(r - ring_r) < 1:
                    self.draw_pixel(x, y, self.COLORS["amber"])

    def draw_writing(self, t):
        self.delete("all")
        cx, cy = 14, 14
        arms, tightness = 2, 2.4
        for y in range(28):
            for x in range(28):
                dx, dy = x - cx + 0.5, y - cy + 0.5
                r = (dx*dx + dy*dy) ** 0.5
                if r > 14:
                    continue
                theta = (dy, dx)  # simplified
                # Draw spiral approximation
                angle = (y * 0.5 + t * 2) % 6.28
                if abs(r - 4 - 3 * (angle / 6.28)) < 1.5:
                    self.draw_pixel(x, y, self.COLORS["cyan"])

    def draw_result(self, t):
        self.delete("all")
        cx, cy = 14, 14
        rays = 8
        max_len = 12 * min(t * 2, 1)
        for i in range(rays):
            angle = (i / rays) * 3.14159 * 2
            for d in range(int(max_len)):
                x = int(cx + (angle * 0) + d * 0.5)  # simplified
                y = int(cy + d * 0.5)
                if 0 <= x < 28 and 0 <= y < 28:
                    self.draw_pixel(x, y, self.COLORS["gold"])
        self.draw_pixel(cx, cy, self.COLORS["white"])
        self.draw_pixel(cx-1, cy, self.COLORS["white"])
        self.draw_pixel(cx+1, cy, self.COLORS["white"])
        self.draw_pixel(cx, cy-1, self.COLORS["white"])
        self.draw_pixel(cx, cy+1, self.COLORS["white"])

    def animate(self):
        self._t += 0.05
        if self.state == AgentState.THINKING:
            self.draw_thinking(self._t)
        elif self.state == AgentState.WRITING:
            self.draw_writing(self._t)
        elif self.state == AgentState.RESULT:
            self.draw_result(self._t)
        else:
            self.draw_idle()
        self._job = self.after(50, self.animate)

    def set_state(self, state: AgentState):
        self.state = state

    def stop(self):
        if self._job:
            self.after_cancel(self._job)


class CybertronDesktop:
    """Desktop GUI for Cybertron with server toggle."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Cybertron v3.0 — Desktop")
        self.root.geometry("1200x800")
        self.root.configure(bg="#0a0a1a")
        self.config = CybertronConfig.load()
        self.engine = CybertronEngine()
        self.server_running = False
        self.server_thread = None
        self._build_ui()

    def _build_ui(self):
        # Top bar
        top = tk.Frame(self.root, bg="#0a0a1a", height=60)
        top.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(top, text="CYBERTRON", font=("Courier", 20, "bold"),
                 fg="#FFD700", bg="#0a0a1a").pack(side=tk.LEFT)
        tk.Label(top, text="v3.0", font=("Courier", 10),
                 fg="#6b6b76", bg="#0a0a1a").pack(side=tk.LEFT, padx=5)

        # Server toggle
        self.server_btn = tk.Button(top, text="▶ Start Server", font=("Courier", 10),
                                    bg="#1a1a3e", fg="#4DD0E1", activebackground="#2a2a5e",
                                    command=self._toggle_server)
        self.server_btn.pack(side=tk.RIGHT, padx=5)

        self.server_status = tk.Label(top, text="● Server: OFF", font=("Courier", 10),
                                      fg="#ff4444", bg="#0a0a1a")
        self.server_status.pack(side=tk.RIGHT, padx=10)

        # Main content
        main = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#0a0a1a")
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left: Pixel canvas + controls
        left = tk.Frame(main, bg="#0a0a1a", width=300)
        main.add(left)

        self.canvas = PixelCanvas(left, size=200)
        self.canvas.pack(pady=20)
        self.canvas.animate()

        # State label
        self.state_label = tk.Label(left, text="IDLE", font=("Courier", 14, "bold"),
                                    fg="#FFD700", bg="#0a0a1a")
        self.state_label.pack(pady=5)

        # Module buttons
        btn_frame = tk.Frame(left, bg="#0a0a1a")
        btn_frame.pack(pady=10)

        modules = [
            ("Recon", self._run_recon),
            ("Scan", self._run_scan),
            ("Brute", self._run_brute),
            ("Exploit", self._run_exploit),
            ("Forensics", self._run_forensics),
            ("Reverse", self._run_reverse),
            ("Hunt", self._run_hunt),
        ]
        for name, cmd in modules:
            btn = tk.Button(btn_frame, text=name, font=("Courier", 10),
                           bg="#1a1a3e", fg="#FFD700", width=12,
                           activebackground="#2a2a5e", command=cmd)
            btn.pack(pady=2)

        # Right: Output + target input
        right = tk.Frame(main, bg="#0a0a1a")
        main.add(right)

        # Target input
        input_frame = tk.Frame(right, bg="#0a0a1a")
        input_frame.pack(fill=tk.X, pady=5)
        tk.Label(input_frame, text="Target:", font=("Courier", 10),
                fg="#FFD700", bg="#0a0a1a").pack(side=tk.LEFT)
        self.target_entry = tk.Entry(input_frame, font=("Courier", 10),
                                     bg="#1a1a3e", fg="#ffffff", insertbackground="#FFD700")
        self.target_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.target_entry.insert(0, "example.com")

        # Output log
        self.output = scrolledtext.ScrolledText(right, font=("Courier", 9),
                                                bg="#0f0f1a", fg="#e0e0e0",
                                                insertbackground="#FFD700")
        self.output.pack(fill=tk.BOTH, expand=True, pady=5)
        self.output.insert(tk.END, "[Cybertron] Desktop UI loaded.\n")
        self.output.insert(tk.END, "[Cybertron] Use the buttons or type commands.\n")

        # Bottom: Status bar
        status = tk.Frame(self.root, bg="#1a1a3e", height=25)
        status.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_text = tk.Label(status, text="Ready", font=("Courier", 9),
                                   fg="#6b6b76", bg="#1a1a3e")
        self.status_text.pack(side=tk.LEFT, padx=10)

    def _log(self, msg: str):
        self.output.insert(tk.END, f"{msg}\n")
        self.output.see(tk.END)

    def _set_state(self, state: AgentState, detail: str = ""):
        self.canvas.set_state(state)
        self.state_label.config(text=state.value.upper())
        if detail:
            self._log(f"[{state.value}] {detail}")

    def _toggle_server(self):
        if not self.server_running:
            self._start_server()
        else:
            self._stop_server()

    def _start_server(self):
        try:
            from cybertron.gateway import start_gateway
            import uvicorn
            self.server_running = True
            self.server_btn.config(text="⏹ Stop Server", fg="#ff4444")
            self.server_status.config(text="● Server: ON", fg="#44ff44")
            self._log(f"[Server] Starting on {self.config.server_host}:{self.config.server_port}")
            # Run in thread
            def run():
                try:
                    uvicorn.run("cybertron.gateway:app",
                               host=self.config.server_host,
                               port=self.config.server_port,
                               log_level="info")
                except Exception as e:
                    self.root.after(0, lambda: self._log(f"[Server] Error: {e}"))
            self.server_thread = threading.Thread(target=run, daemon=True)
            self.server_thread.start()
        except Exception as e:
            self._log(f"[Server] Failed to start: {e}")

    def _stop_server(self):
        self.server_running = False
        self.server_btn.config(text="▶ Start Server", fg="#4DD0E1")
        self.server_status.config(text="● Server: OFF", fg="#ff4444")
        self._log("[Server] Stopped (restart required to fully stop)")

    def _get_target(self):
        return self.target_entry.get().strip() or "example.com"

    def _run_recon(self):
        target = self._get_target()
        self._set_state(AgentState.THINKING, f"Starting recon on {target}")
        def task():
            from cybertron.red_team.recon import ReconEngine
            engine = ReconEngine(target=target)
            result = engine.run()
            self.root.after(0, lambda: self._set_state(AgentState.RESULT, f"Recon done: {len(result.subdomains)} subdomains"))
        threading.Thread(target=task, daemon=True).start()

    def _run_scan(self):
        target = self._get_target()
        self._set_state(AgentState.THINKING, f"Starting scan on {target}")
        def task():
            from cybertron.red_team.scanner import VulnScanner
            scanner = VulnScanner(target=target)
            findings = scanner.run()
            self.root.after(0, lambda: self._set_state(AgentState.RESULT, f"Scan done: {len(findings)} findings"))
        threading.Thread(target=task, daemon=True).start()

    def _run_brute(self):
        target = self._get_target()
        self._set_state(AgentState.THINKING, f"Starting brute force on {target}")
        def task():
            from cybertron.red_team.brute_force import BruteForceEngine
            engine = BruteForceEngine(target=target, mode="dirs")
            results = engine.run()
            self.root.after(0, lambda: self._set_state(AgentState.RESULT, f"Brute done: {len(results)} hits"))
        threading.Thread(target=task, daemon=True).start()

    def _run_exploit(self):
        target = self._get_target()
        self._set_state(AgentState.THINKING, "Exploitation requires approval")
        messagebox.showwarning("Approval Required", "High-severity exploits require explicit approval.\nUse CLI with --approve flag.")
        self._set_state(AgentState.IDLE)

    def _run_forensics(self):
        path = filedialog.askdirectory() or filedialog.askopenfilename()
        if not path:
            return
        self._set_state(AgentState.THINKING, f"Analyzing {path}")
        def task():
            from cybertron.blue_team.forensics import ForensicsEngine
            engine = ForensicsEngine(source=path)
            artifacts = engine.run()
            self.root.after(0, lambda: self._set_state(AgentState.RESULT, f"Forensics done: {len(artifacts)} artifacts"))
        threading.Thread(target=task, daemon=True).start()

    def _run_reverse(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        self._set_state(AgentState.THINKING, f"Reverse engineering {path}")
        def task():
            from cybertron.reverse_engineering.analyzer import ReverseEngineer
            re = ReverseEngineer(target=path)
            result = re.run()
            self.root.after(0, lambda: self._set_state(AgentState.RESULT, f"RE done: {result.file_type}"))
        threading.Thread(target=task, daemon=True).start()

    def _run_hunt(self):
        ioc = self.target_entry.get().strip()
        if not ioc:
            ioc = "bad-hash-example"
        self._set_state(AgentState.THINKING, f"Hunting IOC: {ioc}")
        def task():
            from cybertron.blue_team.threat_hunt import ThreatHunter
            hunter = ThreatHunter(ioc=ioc)
            results = hunter.run()
            self.root.after(0, lambda: self._set_state(AgentState.RESULT, f"Hunt done: {len(results)} matches"))
        threading.Thread(target=task, daemon=True).start()

    def run(self):
        self.root.mainloop()
        self.canvas.stop()
