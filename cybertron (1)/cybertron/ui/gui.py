#!/usr/bin/env python3
"""
Cybertron GUI (Python) — Desktop UI for the Cybertron Agent.
Tkinter + Canvas pixel art. Connects to the Node.js runtime gateway.
Hermes-style chat transcript with warm-glow dark theme.

NEW: GitHub Tool Loader
  /add-tool <github-url> [category]   Install a tool from GitHub releases
  /tools                              View installed tool registry
  /marketplace                        Browse curated security tools
  /remove-tool <id>                   Remove an installed tool
"""
import asyncio
import json
import os
import queue
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

import websockets
import tkinter as tk
from tkinter import ttk

# ─── Config ──────────────────────────────────────────────────────────────────
GATEWAY_HOST = os.environ.get("CYBERTRON_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}"
TOKEN_PATH = Path.home() / ".cybertron" / "auth-token"

# ─── Hermes Palette ──────────────────────────────────────────────────────────
SURFACE_0 = "#14141f"
SURFACE_1 = "#1a1a2e"
SURFACE_2 = "#333355"
TEXT_PRIMARY = "#FFF8DC"
TEXT_MUTED = "#B8860B"
GOLD = "#FFD700"
AMBER = "#FFBF00"
BRONZE = "#CD7F32"
TEAL = "#4dd0e1"
TEAL_DIM = "#2a8a99"
DANGER = "#ef5350"
SUCCESS = "#4caf50"
WARN = "#ffa726"
BORDER = "#CD7F32"
BORDER_DIM = "#2a2a4a"
MSG_USER_BG = "#1a1a35"
MSG_USER_BORDER = "#2a2a55"
MSG_AGENT_BG = "#141428"
MSG_AGENT_BORDER = "#3a2a1a"
MSG_TOOL_BG = "#1a1a2e"
MSG_TOOL_BORDER_LEFT = "#CD7F32"
MSG_RESULT_BG = "#141428"
MSG_RESULT_BORDER_LEFT = "#4caf50"
COMPOSER_BG = "#14142b"

# ─── Pixel Art Engine ────────────────────────────────────────────────────────
def ramp_color(t):
    stops = [(0.00, (255,215,0)), (0.35, (255,191,0)), (0.65, (77,208,225)), (1.00, (40,40,90))]
    for i in range(len(stops)-1):
        t0, c0 = stops[i]; t1, c1 = stops[i+1]
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return (int(c0[0]+(c1[0]-c0[0])*f), int(c0[1]+(c1[1]-c0[1])*f), int(c0[2]+(c1[2]-c0[2])*f))
    return (40,40,90)

def rgb_hex(r,g,b): return f"#{r:02x}{g:02x}{b:02x}"

def draw_planet(canvas, N, ring_angle, pulse, scale=5):
    canvas.delete("all")
    cx, cy = N/2, N/2
    pr = N * 0.2 * (1 + pulse * 0.05)
    for y in range(N):
        for x in range(N):
            dx, dy = x-cx, y-cy
            r = (dx*dx+dy*dy)**0.5
            if r <= pr:
                c = ramp_color((r/pr)*0.6)
                canvas.create_rectangle(x*scale, y*scale, (x+1)*scale, (y+1)*scale, fill=rgb_hex(*c), outline="")
    cos_a = __import__('math').cos(ring_angle)
    sin_a = __import__('math').sin(ring_angle)
    for a in range(0, 360, 4):
        rad = (a*3.14159)/180
        ex = __import__('math').cos(rad)*pr*1.8
        ey = __import__('math').sin(rad)*pr*0.35
        rx = ex*cos_a - ey*sin_a
        ry = ex*sin_a + ey*cos_a
        px, py = round(cx+rx), round(cy+ry)
        if 0 <= px < N and 0 <= py < N:
            canvas.create_rectangle(px*scale, py*scale, (px+1)*scale, (py+1)*scale, fill="#FFBF00", outline="")

def draw_spiral(canvas, N, rot_offset, scale=5):
    canvas.delete("all")
    cx, cy = N/2, N/2
    for y in range(N):
        for x in range(N):
            dx, dy = x-cx+0.5, y-cy+0.5
            r = (dx*dx+dy*dy)**0.5
            if r > N/2: continue
            theta = __import__('math').atan2(dy,dx) + rot_offset
            spiral = __import__('math').cos(2*theta - 2.4*r)
            density = (spiral+1)/2 * (1 - r/(N/2))
            if density > 0.42 or r < 1.6:
                c = ramp_color(min(r/(N/2), 1))
                canvas.create_rectangle(x*scale, y*scale, (x+1)*scale, (y+1)*scale, fill=rgb_hex(*c), outline="")

def draw_burst(canvas, N, progress, scale=5):
    canvas.delete("all")
    cx, cy = N/2, N/2
    rays = 10
    max_len = N * 0.46
    length = max_len * min(progress*2, 1)
    fade = 1 - (progress-0.5)*2 if progress > 0.5 else 1
    for i in range(rays):
        angle = (i/rays)*2*3.14159
        for d in range(int(length)):
            px = round(cx + __import__('math').cos(angle)*d)
            py = round(cy + __import__('math').sin(angle)*d)
            if 0 <= px < N and 0 <= py < N:
                c = ramp_color(d/max_len)
                faded = tuple(int(v*fade + 10*(1-fade)) for v in c)
                canvas.create_rectangle(px*scale, py*scale, (px+1)*scale, (py+1)*scale, fill=rgb_hex(*faded), outline="")
    for yy in range(-1,2):
        for xx in range(-1,2):
            px, py = int(cx)+xx, int(cy)+yy
            canvas.create_rectangle(px*scale, py*scale, (px+1)*scale, (py+1)*scale, fill="#FFD700", outline="")

# ─── GUI Application ─────────────────────────────────────────────────────────
class CybertronGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Cybertron — Agent Console")
        self.root.configure(bg=SURFACE_0)
        self.root.geometry("1200x800")
        self.root.minsize(780, 540)

        self.connected = False
        self.authed = False
        self.current_state = "idle"
        self.status_text = "idle"
        self.state_detail = ""
        self.sessions: List[Dict[str,Any]] = []
        self.server_view = False
        self.tools_view = False
        self.marketplace_view = False
        self.control_view = False
        self.split_pane = False
        self.dry_run = False
        self.bb_mode = False
        self.current_target = ""
        self.pending_approval: Optional[Dict[str,Any]] = None
        self.pending_download: Optional[Dict[str,Any]] = None
        self.stream_buffer = ""
        self.stream_label = None
        self.plan_steps = []
        self.session_start = 0
        self.ws = None
        self.anim_t = 0
        self.msg_queue = queue.Queue()
        self.current_session_id = self.new_session_id()
        self.reconnect_attempt = 0
        self.tool_loader = None
        self.audit_logger = None
        self.session_exporter = None
        self._init_services()

        self.token = ""
        if TOKEN_PATH.exists():
            self.token = TOKEN_PATH.read_text().strip()

        self.build_ui()
        self.start_ws_thread()
        self.poll_queue()
        self.animate()

    def _init_services(self):
        try:
            from github_tool_loader import get_loader
            self.tool_loader = get_loader()
        except Exception:
            self.tool_loader = None
        try:
            from audit_logger import get_logger
            self.audit_logger = get_logger()
        except Exception:
            self.audit_logger = None
        try:
            from session_exporter import get_exporter
            self.session_exporter = get_exporter()
        except Exception:
            self.session_exporter = None

    def new_session_id(self):
        return f"gui-{int(time.time()*1000)}-{secrets.token_hex(3)}"

    def build_ui(self):
        main = tk.Frame(self.root, bg=SURFACE_0)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Header
        header = tk.Frame(main, bg=SURFACE_1, height=48)
        header.pack(fill=tk.X, pady=(0, 10))
        header.pack_propagate(False)

        tk.Label(header, text="CYBERTRON", font=("Courier", 13, "bold"), 
                 bg=SURFACE_1, fg=GOLD).pack(side=tk.LEFT, padx=16, pady=8)
        tk.Label(header, text="Agent Console", font=("IBM Plex Mono", 9),
                 bg=SURFACE_1, fg=TEXT_MUTED).pack(side=tk.LEFT, pady=8)

        self.conn_label = tk.Label(header, text="● Offline", font=("IBM Plex Mono", 9, "bold"),
                                   bg=SURFACE_1, fg=DANGER)
        self.conn_label.pack(side=tk.RIGHT, padx=16, pady=8)

        # View toggles
        btn_frame = tk.Frame(header, bg=SURFACE_1)
        btn_frame.pack(side=tk.RIGHT, padx=8, pady=8)

        self.server_btn = tk.Button(btn_frame, text="Server", font=("IBM Plex Mono", 9),
                                    bg=SURFACE_2, fg=TEXT_MUTED, bd=1, relief=tk.FLAT,
                                    activebackground=SURFACE_2, activeforeground=GOLD,
                                    cursor="hand2", command=self.toggle_server)
        self.server_btn.pack(side=tk.LEFT, padx=2)

        self.tools_btn = tk.Button(btn_frame, text="Tools", font=("IBM Plex Mono", 9),
                                   bg=SURFACE_2, fg=TEXT_MUTED, bd=1, relief=tk.FLAT,
                                   activebackground=SURFACE_2, activeforeground=GOLD,
                                   cursor="hand2", command=self.toggle_tools)
        self.tools_btn.pack(side=tk.LEFT, padx=2)

        self.market_btn = tk.Button(btn_frame, text="Market", font=("IBM Plex Mono", 9),
                                    bg=SURFACE_2, fg=TEXT_MUTED, bd=1, relief=tk.FLAT,
                                    activebackground=SURFACE_2, activeforeground=GOLD,
                                    cursor="hand2", command=self.toggle_marketplace)
        self.market_btn.pack(side=tk.LEFT, padx=2)

        self.control_btn = tk.Button(btn_frame, text="⚙", font=("IBM Plex Mono", 9),
                                     bg=SURFACE_2, fg=TEXT_MUTED, bd=1, relief=tk.FLAT,
                                     activebackground=SURFACE_2, activeforeground=GOLD,
                                     cursor="hand2", command=self.toggle_control)
        self.control_btn.pack(side=tk.LEFT, padx=2)

        # Content
        content = tk.Frame(main, bg=SURFACE_0)
        content.pack(fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=0)  # split pane
        content.grid_columnconfigure(2, weight=1)  # sidebar
        content.grid_rowconfigure(0, weight=1)

        # Left: Chat area
        left = tk.Frame(content, bg=SURFACE_0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Middle: Split pane (raw output)
        self.split_frame = tk.Frame(content, bg=SURFACE_0, width=0)
        self.split_frame.grid(row=0, column=1, sticky="nsew")
        self.split_frame.grid_remove()

        self.split_header = tk.Label(self.split_frame, text="RAW OUTPUT", font=("IBM Plex Mono", 9, "bold"),
                                     bg=SURFACE_1, fg=BRONZE)
        self.split_header.pack(fill=tk.X, padx=0, pady=(0, 4))

        self.split_text = tk.Text(self.split_frame, bg=SURFACE_0, fg=TEXT_MUTED,
                                  font=("IBM Plex Mono", 9), wrap=tk.WORD,
                                  bd=0, highlightthickness=0, state=tk.DISABLED)
        self.split_text.pack(fill=tk.BOTH, expand=True, padx=4)
        left.grid_rowconfigure(0, weight=0)
        left.grid_rowconfigure(1, weight=1)
        left.grid_rowconfigure(2, weight=0)
        left.grid_columnconfigure(0, weight=1)

        # State bar
        state_bar = tk.Frame(left, bg=SURFACE_1, height=44, bd=1, relief=tk.FLAT)
        state_bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        state_bar.pack_propagate(False)
        state_bar.config(highlightbackground=BORDER, highlightthickness=1)

        self.state_canvas = tk.Canvas(state_bar, width=32, height=32, bg=SURFACE_1, highlightthickness=0)
        self.state_canvas.pack(side=tk.LEFT, padx=(12, 8), pady=6)

        self.state_label = tk.Label(state_bar, text="IDLE", font=("Courier", 10, "bold"),
                                      bg=SURFACE_1, fg=GOLD)
        self.state_label.pack(side=tk.LEFT, pady=8)

        self.state_detail_lbl = tk.Label(state_bar, text="Enter a goal to start.",
                                       font=("IBM Plex Mono", 9), bg=SURFACE_1, fg=TEXT_MUTED)
        self.state_detail_lbl.pack(side=tk.LEFT, padx=(10, 0), pady=8)

        self.timer_label = tk.Label(state_bar, text="", font=("Courier", 9),
                                     bg=SURFACE_1, fg=BRONZE)
        self.timer_label.pack(side=tk.RIGHT, padx=12, pady=8)

        # Chat transcript
        chat_frame = tk.Frame(left, bg=SURFACE_0, bd=1, relief=tk.FLAT)
        chat_frame.grid(row=1, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat_canvas = tk.Canvas(chat_frame, bg=SURFACE_0, highlightthickness=0)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")

        chat_scroll = tk.Scrollbar(chat_frame, command=self.chat_canvas.yview, bg=SURFACE_0, troughcolor=SURFACE_0)
        chat_scroll.grid(row=0, column=1, sticky="ns")
        self.chat_canvas.config(yscrollcommand=chat_scroll.set)

        self.chat_inner = tk.Frame(self.chat_canvas, bg=SURFACE_0)
        self.chat_canvas.create_window((0, 0), window=self.chat_inner, anchor="nw", width=680)
        self.chat_inner.bind("<Configure>", lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))

        # Composer
        composer = tk.Frame(left, bg=COMPOSER_BG, height=56)
        composer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        composer.pack_propagate(False)

        self.goal_entry = tk.Entry(composer, bg=SURFACE_0, fg=TEXT_PRIMARY, font=("IBM Plex Mono", 11),
                                    insertbackground=TEXT_PRIMARY, bd=1, relief=tk.FLAT,
                                    highlightbackground=BORDER_DIM, highlightcolor=AMBER)
        self.goal_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.goal_entry.bind("<Return>", lambda e: self.send_goal())

        self.send_btn = tk.Button(composer, text="Run", font=("IBM Plex Mono", 10, "bold"),
                                   bg=AMBER, fg=SURFACE_0, bd=0, relief=tk.FLAT,
                                   activebackground=GOLD, cursor="hand2",
                                   command=self.send_goal)
        self.send_btn.pack(side=tk.RIGHT, padx=10, pady=10)

        # Right: Sidebar (multi-purpose)
        self.sidebar = tk.Frame(content, bg=SURFACE_1, bd=1, relief=tk.FLAT)
        self.sidebar.grid(row=0, column=2, rowspan=3, sticky="nsew")
        self.sidebar.config(highlightbackground=BORDER, highlightthickness=1)

        self.sidebar_title = tk.Label(self.sidebar, text="SESSIONS", font=("IBM Plex Mono", 9, "bold"),
                 bg=SURFACE_1, fg=BRONZE)
        self.sidebar_title.pack(anchor="w", padx=14, pady=(14, 8))

        self.sidebar_content = tk.Frame(self.sidebar, bg=SURFACE_1)
        self.sidebar_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.render_sessions()

        # Approval modal
        self.approval_frame = tk.Frame(self.root, bg=SURFACE_0)
        self.approval_modal = tk.Frame(self.approval_frame, bg=SURFACE_1, bd=2, relief=tk.FLAT)
        self.approval_modal.place(relx=0.5, rely=0.5, anchor="center")
        self.approval_modal.config(highlightbackground=DANGER, highlightthickness=2)

        tk.Label(self.approval_modal, text="APPROVAL REQUIRED", font=("Courier", 12, "bold"),
                 bg=SURFACE_1, fg=DANGER).pack(padx=30, pady=(20, 10))

        self.approval_text = tk.Label(self.approval_modal, text="", font=("IBM Plex Mono", 10),
                                       bg=SURFACE_1, fg=TEXT_MUTED, wraplength=380, justify=tk.LEFT)
        self.approval_text.pack(padx=30, pady=10)

        btn_frame = tk.Frame(self.approval_modal, bg=SURFACE_1)
        btn_frame.pack(padx=30, pady=(10, 20))

        tk.Button(btn_frame, text="Approve", font=("IBM Plex Mono", 10, "bold"),
                  bg=SUCCESS, fg=SURFACE_0, bd=0, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self.send_approval(True)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Deny", font=("IBM Plex Mono", 10, "bold"),
                  bg=DANGER, fg="white", bd=0, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self.send_approval(False)).pack(side=tk.LEFT, padx=5)

        # Download approval modal
        self.download_frame = tk.Frame(self.root, bg=SURFACE_0)
        self.download_modal = tk.Frame(self.download_frame, bg=SURFACE_1, bd=2, relief=tk.FLAT)
        self.download_modal.place(relx=0.5, rely=0.5, anchor="center")
        self.download_modal.config(highlightbackground=WARN, highlightthickness=2)

        tk.Label(self.download_modal, text="DOWNLOAD APPROVAL", font=("Courier", 12, "bold"),
                 bg=SURFACE_1, fg=WARN).pack(padx=30, pady=(20, 10))

        self.download_text = tk.Label(self.download_modal, text="", font=("IBM Plex Mono", 10),
                                       bg=SURFACE_1, fg=TEXT_MUTED, wraplength=380, justify=tk.LEFT)
        self.download_text.pack(padx=30, pady=10)

        dl_btn_frame = tk.Frame(self.download_modal, bg=SURFACE_1)
        dl_btn_frame.pack(padx=30, pady=(10, 20))

        tk.Button(dl_btn_frame, text="Download", font=("IBM Plex Mono", 10, "bold"),
                  bg=SUCCESS, fg=SURFACE_0, bd=0, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self.send_download_approval(True)).pack(side=tk.LEFT, padx=5)
        tk.Button(dl_btn_frame, text="Cancel", font=("IBM Plex Mono", 10, "bold"),
                  bg=DANGER, fg="white", bd=0, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self.send_download_approval(False)).pack(side=tk.LEFT, padx=5)

    def add_stream_msg(self, text: str):
        frame = tk.Frame(self.chat_inner, bg=SURFACE_0)
        frame.pack(fill=tk.X, padx=12, pady=6)
        inner = tk.Frame(frame, bg=MSG_AGENT_BG, bd=1, relief=tk.FLAT)
        inner.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 60))
        inner.config(highlightbackground=MSG_AGENT_BORDER, highlightthickness=1)
        tk.Label(inner, text="Cybertron", font=("IBM Plex Mono", 8, "bold"),
                 bg=MSG_AGENT_BG, fg=AMBER).pack(anchor="w", padx=10, pady=(8, 4))
        self.stream_label = tk.Label(inner, text=text, font=("IBM Plex Mono", 10),
                     bg=MSG_AGENT_BG, fg=TEXT_PRIMARY, wraplength=480, justify=tk.LEFT)
        self.stream_label.pack(anchor="w", padx=10, pady=(0, 4))
        tk.Label(inner, text="thinking...", font=("IBM Plex Mono", 8),
                 bg=MSG_AGENT_BG, fg=TEAL).pack(anchor="w", padx=10, pady=(0, 8))
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    def add_chat_msg(self, role: str, text: str, meta: str = ""):
        frame = tk.Frame(self.chat_inner, bg=SURFACE_0)
        frame.pack(fill=tk.X, padx=12, pady=6)
        ts = time.strftime("%H:%M:%S")

        if role == "user":
            inner = tk.Frame(frame, bg=MSG_USER_BG, bd=1, relief=tk.FLAT)
            inner.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(60, 0))
            inner.config(highlightbackground=MSG_USER_BORDER, highlightthickness=1)
            tk.Label(inner, text="You", font=("IBM Plex Mono", 8, "bold"),
                     bg=MSG_USER_BG, fg=TEAL).pack(anchor="w", padx=10, pady=(8, 4))
            tk.Label(inner, text=text, font=("IBM Plex Mono", 10),
                     bg=MSG_USER_BG, fg=TEXT_PRIMARY, wraplength=480, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 4))
            tk.Label(inner, text=f"{ts}  {meta}", font=("IBM Plex Mono", 8),
                     bg=MSG_USER_BG, fg=TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 8))

        elif role == "agent":
            inner = tk.Frame(frame, bg=MSG_AGENT_BG, bd=1, relief=tk.FLAT)
            inner.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 60))
            inner.config(highlightbackground=MSG_AGENT_BORDER, highlightthickness=1)
            tk.Label(inner, text="Cybertron", font=("IBM Plex Mono", 8, "bold"),
                     bg=MSG_AGENT_BG, fg=AMBER).pack(anchor="w", padx=10, pady=(8, 4))
            tk.Label(inner, text=text, font=("IBM Plex Mono", 10),
                     bg=MSG_AGENT_BG, fg=TEXT_PRIMARY, wraplength=480, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 4))
            tk.Label(inner, text=ts, font=("IBM Plex Mono", 8),
                     bg=MSG_AGENT_BG, fg=TEXT_MUTED).pack(anchor="w", padx=10, pady=(0, 8))

        elif role == "system":
            inner = tk.Label(frame, text=text, font=("IBM Plex Mono", 9),
                             bg=SURFACE_0, fg=TEXT_MUTED, wraplength=500)
            inner.pack(anchor="center", pady=4)

        elif role == "tool":
            inner = tk.Frame(frame, bg=MSG_TOOL_BG, bd=1, relief=tk.FLAT)
            inner.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 80))
            inner.config(highlightbackground=MSG_TOOL_BORDER_LEFT, highlightthickness=1)
            tk.Label(inner, text=f"TOOL: {meta}", font=("IBM Plex Mono", 8, "bold"),
                     bg=MSG_TOOL_BG, fg=BRONZE).pack(anchor="w", padx=10, pady=(8, 4))
            tk.Label(inner, text=text, font=("IBM Plex Mono", 9),
                     bg=MSG_TOOL_BG, fg=TEXT_MUTED, wraplength=480, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        elif role == "result":
            inner = tk.Frame(frame, bg=MSG_RESULT_BG, bd=1, relief=tk.FLAT)
            inner.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 80))
            inner.config(highlightbackground=MSG_RESULT_BORDER_LEFT, highlightthickness=1)
            tk.Label(inner, text="RESULT", font=("IBM Plex Mono", 8, "bold"),
                     bg=MSG_RESULT_BG, fg=SUCCESS).pack(anchor="w", padx=10, pady=(8, 4))
            tk.Label(inner, text=text, font=("IBM Plex Mono", 9),
                     bg=MSG_RESULT_BG, fg=TEXT_PRIMARY, wraplength=480, justify=tk.LEFT).pack(anchor="w", padx=10, pady=(0, 8))

        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    def render_sessions(self):
        for w in self.sidebar_content.winfo_children():
            w.destroy()
        if not self.sessions:
            tk.Label(self.sidebar_content, text="No active sessions", font=("IBM Plex Mono", 9),
                     bg=SURFACE_1, fg=TEXT_MUTED).pack(pady=20)
            return
        colors = {"thinking": TEAL, "running_tool": TEAL, "writing": AMBER, "done": SUCCESS,
                  "idle": TEXT_MUTED, "awaiting_approval": DANGER, "error": DANGER}
        for s in self.sessions[-10:]:
            frame = tk.Frame(self.sidebar_content, bg=SURFACE_0, bd=1, relief=tk.FLAT)
            frame.pack(fill=tk.X, pady=2)
            sid = s.get("id", "?")[:8]
            state = s.get("state", "idle")
            started = s.get("startedAt", 0)
            finished = s.get("finishedAt")
            elapsed_s = ((finished or int(time.time()*1000)) - started) / 1000
            tk.Label(frame, text=f"{sid}  {state}", font=("IBM Plex Mono", 9),
                     bg=SURFACE_0, fg=colors.get(state, TEXT_MUTED)).pack(anchor="w", padx=8, pady=4)
            tk.Label(frame, text=f"T+{elapsed_s:.1f}s  calls:{s.get('toolCallCount',0)}", font=("IBM Plex Mono", 8),
                     bg=SURFACE_0, fg=TEXT_MUTED).pack(anchor="w", padx=8, pady=(0, 4))

    def render_tools(self):
        for w in self.sidebar_content.winfo_children():
            w.destroy()
        if self.tool_loader is None:
            tk.Label(self.sidebar_content, text="Tool loader unavailable\nInstall requests library", font=("IBM Plex Mono", 9),
                     bg=SURFACE_1, fg=DANGER).pack(pady=20)
            return
        tools = self.tool_loader.get_catalog_list()
        if not tools:
            tk.Label(self.sidebar_content, text="No tools installed", font=("IBM Plex Mono", 9),
                     bg=SURFACE_1, fg=TEXT_MUTED).pack(pady=20)
            return
        for t in tools:
            frame = tk.Frame(self.sidebar_content, bg=SURFACE_0, bd=1, relief=tk.FLAT)
            frame.pack(fill=tk.X, pady=2)
            tid = t.get("id", "?")
            ver = t.get("version", "?")[:14]
            cat = t.get("category", "?")
            tk.Label(frame, text=f"{tid}  v{ver}", font=("IBM Plex Mono", 9),
                     bg=SURFACE_0, fg=AMBER).pack(anchor="w", padx=8, pady=4)
            tk.Label(frame, text=f"{cat}  —  {t.get('binary_path','?')[:40]}", font=("IBM Plex Mono", 8),
                     bg=SURFACE_0, fg=TEXT_MUTED).pack(anchor="w", padx=8, pady=(0, 4))

    def render_marketplace(self):
        for w in self.sidebar_content.winfo_children():
            w.destroy()
        if self.tool_loader is None:
            tk.Label(self.sidebar_content, text="Tool loader unavailable", font=("IBM Plex Mono", 9),
                     bg=SURFACE_1, fg=DANGER).pack(pady=20)
            return
        items = self.tool_loader.get_marketplace()
        installed = set(self.tool_loader.catalog.keys()) if self.tool_loader else set()
        for item in items:
            frame = tk.Frame(self.sidebar_content, bg=SURFACE_0, bd=1, relief=tk.FLAT)
            frame.pack(fill=tk.X, pady=2)
            name = item.get("name", "?")
            mark = "✓ " if name in installed else "  "
            tk.Label(frame, text=f"{mark}{name}", font=("IBM Plex Mono", 9),
                     bg=SURFACE_0, fg=SUCCESS if name in installed else AMBER).pack(anchor="w", padx=8, pady=4)
            tk.Label(frame, text=f"{item.get('category','?')}  —  {item.get('description','')[:40]}", font=("IBM Plex Mono", 8),
                     bg=SURFACE_0, fg=TEXT_MUTED).pack(anchor="w", padx=8, pady=(0, 4))
            if name not in installed:
                tk.Button(frame, text="Install", font=("IBM Plex Mono", 8),
                          bg=SURFACE_2, fg=TEAL, bd=0, relief=tk.FLAT,
                          cursor="hand2",
                          command=lambda repo=item.get('repo'), cat=item.get('category'): self.request_tool_install(repo, cat)).pack(anchor="w", padx=8, pady=(0, 4))

    def request_tool_install(self, repo, category):
        if not repo:
            return
        if self.tool_loader is None:
            self.add_chat_msg("system", "Tool loader not available.")
            return
        parsed = self.tool_loader.parse_repo(repo)
        if not parsed:
            self.add_chat_msg("system", f"Could not parse repo: {repo}")
            return
        self.pending_download = {
            "url": f"https://github.com/{parsed}",
            "repo": parsed,
            "category": category or "recon",
        }
        self.download_text.config(text=f"Repository: {parsed}\nCategory: {category or 'recon'}\n\nThis will download and execute a binary from GitHub. Proceed?")
        self.download_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    def set_state(self, state: str, detail: str = ""):
        self.current_state = state
        self.state_label.config(text=state.upper())
        if detail:
            self.state_detail_lbl.config(text=detail)
        if state in ("done", "error", "idle"):
            self.session_start = 0
            self.timer_label.config(text="")

    def toggle_server(self):
        self.server_view = not self.server_view
        self.tools_view = False
        self.marketplace_view = False
        self.server_btn.config(fg=GOLD if self.server_view else TEXT_MUTED)
        self.tools_btn.config(fg=TEXT_MUTED)
        self.market_btn.config(fg=TEXT_MUTED)
        self.sidebar_title.config(text="SESSIONS")
        if self.server_view and self.ws:
            self.send_ws({"type": "list_sessions"})
        self.render_sessions()

    def toggle_tools(self):
        self.tools_view = not self.tools_view
        self.server_view = False
        self.marketplace_view = False
        self.tools_btn.config(fg=GOLD if self.tools_view else TEXT_MUTED)
        self.server_btn.config(fg=TEXT_MUTED)
        self.market_btn.config(fg=TEXT_MUTED)
        self.sidebar_title.config(text="TOOL REGISTRY")
        self.render_tools()

    def toggle_marketplace(self):
        self.marketplace_view = not self.marketplace_view
        self.server_view = False
        self.tools_view = False
        self.control_view = False
        self.market_btn.config(fg=GOLD if self.marketplace_view else TEXT_MUTED)
        self.server_btn.config(fg=TEXT_MUTED)
        self.tools_btn.config(fg=TEXT_MUTED)
        self.control_btn.config(fg=TEXT_MUTED)
        self.sidebar_title.config(text="MARKETPLACE")
        self.render_marketplace()

    def toggle_control(self):
        self.control_view = not self.control_view
        self.server_view = False
        self.tools_view = False
        self.marketplace_view = False
        self.control_btn.config(fg=GOLD if self.control_view else TEXT_MUTED)
        self.server_btn.config(fg=TEXT_MUTED)
        self.tools_btn.config(fg=TEXT_MUTED)
        self.market_btn.config(fg=TEXT_MUTED)
        self.sidebar_title.config(text="CONTROL CENTER")
        self.render_control()

    def toggle_split(self):
        self.split_pane = not self.split_pane
        if self.split_pane:
            self.split_frame.grid()
            self.split_frame.config(width=350)
            content.grid_columnconfigure(1, weight=1)
        else:
            self.split_frame.grid_remove()
            self.split_frame.config(width=0)
            content.grid_columnconfigure(1, weight=0)

    def append_split(self, text: str):
        self.split_text.config(state=tk.NORMAL)
        self.split_text.insert(tk.END, text + "\n")
        self.split_text.see(tk.END)
        self.split_text.config(state=tk.DISABLED)

    def render_control(self):
        for w in self.sidebar_content.winfo_children():
            w.destroy()

        # Theme section
        tk.Label(self.sidebar_content, text="APPEARANCE", font=("IBM Plex Mono", 9, "bold"),
                 bg=SURFACE_1, fg=BRONZE).pack(anchor="w", padx=8, pady=(10, 4))
        tk.Label(self.sidebar_content, text="Theme: Hermes Dark", font=("IBM Plex Mono", 9),
                 bg=SURFACE_1, fg=TEXT_MUTED).pack(anchor="w", padx=8, pady=2)
        tk.Button(self.sidebar_content, text="Toggle Split Pane", font=("IBM Plex Mono", 9),
                  bg=SURFACE_2, fg=TEAL, bd=0, relief=tk.FLAT, cursor="hand2",
                  command=self.toggle_split).pack(anchor="w", padx=8, pady=2)

        # Agent section
        tk.Label(self.sidebar_content, text="AGENT", font=("IBM Plex Mono", 9, "bold"),
                 bg=SURFACE_1, fg=BRONZE).pack(anchor="w", padx=8, pady=(14, 4))
        tk.Button(self.sidebar_content, text=f"Dry-run: {'ON' if self.dry_run else 'OFF'}",
                  font=("IBM Plex Mono", 9), bg=SURFACE_2,
                  fg=WARN if self.dry_run else TEXT_MUTED, bd=0, relief=tk.FLAT,
                  cursor="hand2", command=self.toggle_dry_run).pack(anchor="w", padx=8, pady=2)

        # Security section
        tk.Label(self.sidebar_content, text="SECURITY", font=("IBM Plex Mono", 9, "bold"),
                 bg=SURFACE_1, fg=BRONZE).pack(anchor="w", padx=8, pady=(14, 4))
        tk.Label(self.sidebar_content, text="Output sanitization: ON", font=("IBM Plex Mono", 9),
                 bg=SURFACE_1, fg=SUCCESS).pack(anchor="w", padx=8, pady=2)
        tk.Label(self.sidebar_content, text="Rate limit: 30/min", font=("IBM Plex Mono", 9),
                 bg=SURFACE_1, fg=TEXT_MUTED).pack(anchor="w", padx=8, pady=2)

    def toggle_dry_run(self):
        self.dry_run = not self.dry_run
        self.add_chat_msg("system", f"Dry-run mode: {'ON' if self.dry_run else 'OFF'}")
        if self.control_view:
            self.render_control()

    def send_goal(self):
        goal = self.goal_entry.get().strip()
        if not goal: return
        self.goal_entry.delete(0, tk.END)

        # Slash commands
        if goal.startswith("/"):
            self.handle_slash_command(goal)
            return

        self.add_chat_msg("user", goal)
        self.add_chat_msg("system", "Starting reconnaissance session...")
        self.current_session_id = self.new_session_id()
        if self.audit_logger:
            self.audit_logger.session_started(self.current_session_id, goal, "gui")
        self.send_ws({"type": "session_start", "sessionId": self.current_session_id, "goal": goal, "origin": "gui"})
        self.session_start = time.time()

    def handle_slash_command(self, buf: str):
        parts = buf.split()
        if not parts:
            return
        cmd = parts[0].lower()

        if cmd == "/add-tool":
            if len(parts) < 2:
                self.add_chat_msg("system", "Usage: /add-tool <github-url-or-repo> [category]")
                return
            url = parts[1]
            category = parts[2] if len(parts) > 2 else "recon"
            if self.tool_loader is None:
                self.add_chat_msg("system", "Tool loader not available. Install requests.")
                return
            parsed = self.tool_loader.parse_repo(url)
            if not parsed:
                self.add_chat_msg("system", f"Could not parse repo from: {url}")
                return
            self.pending_download = {
                "url": url if "github.com" in url else f"https://github.com/{url}",
                "repo": parsed,
                "category": category,
            }
            self.download_text.config(text=f"Repository: {parsed}\nCategory: {category}\n\nThis will download and execute a binary from GitHub. Proceed?")
            self.download_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            return

        if cmd == "/tools":
            self.toggle_tools()
            return

        if cmd == "/marketplace":
            self.toggle_marketplace()
            return

        if cmd == "/remove-tool":
            if len(parts) < 2:
                self.add_chat_msg("system", "Usage: /remove-tool <tool-id>")
                return
            tool_id = parts[1]
            if self.tool_loader is None:
                self.add_chat_msg("system", "Tool loader not available.")
                return
            ok, msg = self.tool_loader.remove_tool(tool_id)
            self.add_chat_msg("system", msg, "success" if ok else "error")
            if self.tools_view:
                self.render_tools()
            return

        if cmd == "/export":
            if len(parts) < 2:
                self.add_chat_msg("system", "Usage: /export markdown | json | audit | list")
                return
            fmt = parts[1].lower()
            if fmt == "audit":
                if self.audit_logger:
                    recent = self.audit_logger.get_recent(20)
                    self.add_chat_msg("system", f"Recent audit entries ({len(recent)}):")
                    for entry in recent:
                        ts = entry.get("timestamp", "?")[11:19]
                        cat = entry.get("category", "?")
                        action = entry.get("action", "?")
                        self.add_chat_msg("system", f"  [{ts}] {cat}/{action}")
                else:
                    self.add_chat_msg("system", "Audit logger not available")
                return
            if fmt == "list":
                if self.session_exporter:
                    exports = self.session_exporter.list_exports()
                    self.add_chat_msg("system", f"Exports: {len(exports)} files")
                    for e in exports[:10]:
                        self.add_chat_msg("system", f"  {e['filename']} ({e['size']} bytes)")
                else:
                    self.add_chat_msg("system", "Session exporter not available")
                return
            if fmt in ("markdown", "md"):
                if self.session_exporter:
                    path = self.session_exporter.export_markdown(
                        self.current_session_id,
                        [], goal="", tool_calls=0
                    )
                    self.add_chat_msg("system", f"Exported to {path}")
                else:
                    self.add_chat_msg("system", "Session exporter not available")
                return
            if fmt == "json":
                if self.session_exporter:
                    path = self.session_exporter.export_json(
                        self.current_session_id,
                        [], goal="", tool_calls=0
                    )
                    self.add_chat_msg("system", f"Exported to {path}")
                else:
                    self.add_chat_msg("system", "Session exporter not available")
                return
            self.add_chat_msg("system", "Usage: /export markdown | json | audit | list")
            return

        if cmd == "/dry-run":
            self.toggle_dry_run()
            return
        if cmd == "/split":
            self.toggle_split()
            return
        if cmd == "/config":
            self.toggle_control()
            return
        if cmd == "/bb" or cmd == "/bounty":
            self.bb_mode = not self.bb_mode
            self.add_chat_msg("system", f"Bug Bounty mode: {'ON' if self.bb_mode else 'OFF'}")
            if self.bb_mode:
                self.add_chat_msg("system", "Commands: /target <name>  /recon  /brute <type>  /report  /submit  /sync-h1 <handle>  /targets")
            return

        if cmd == "/target":
            if len(parts) < 2:
                self.add_chat_msg("system", "Usage: /target <target-name>")
                return
            self.current_target = parts[1]
            self.add_chat_msg("system", f"Target set: {parts[1]}")
            return

        if cmd == "/recon":
            if not self.current_target:
                self.add_chat_msg("system", "No target set. Use /target <name> first.")
                return
            self.add_chat_msg("system", f"Starting reconnaissance on {self.current_target}...")
            self.send_ws({
                "type": "execute_recon",
                "target": self.current_target,
                "scope_name": self.current_target,
            })
            return

        if cmd == "/brute":
            if len(parts) < 2:
                self.add_chat_msg("system", "Usage: /brute <dirs|subdomains|params|vhosts|api|idor> [wordlist]")
                return
            attack_type = parts[1]
            wordlist = parts[2] if len(parts) > 2 else "common"
            if not self.current_target:
                self.add_chat_msg("system", "No target set. Use /target <name> first.")
                return
            self.add_chat_msg("system", f"Starting {attack_type} brute force on {self.current_target}...")
            self.send_ws({
                "type": "execute_brute",
                "target": self.current_target,
                "attack_type": attack_type,
                "wordlist": wordlist,
                "scope_name": self.current_target,
            })
            return

        if cmd == "/report":
            if not self.current_target:
                self.add_chat_msg("system", "No target set. Use /target <name> first.")
                return
            self.add_chat_msg("system", f"Generating report for {self.current_target}...")
            self.send_ws({
                "type": "generate_report",
                "program": self.current_target,
                "handle": self.current_target,
            })
            return

        if cmd == "/submit":
            if not self.current_target:
                self.add_chat_msg("system", "No target set. Use /target <name> first.")
                return
            self.add_chat_msg("system", f"Submitting findings to HackerOne for {self.current_target}...")
            self.send_ws({
                "type": "submit_hackerone",
                "target": self.current_target,
            })
            return

        if cmd == "/sync-h1":
            if len(parts) < 2:
                self.add_chat_msg("system", "Usage: /sync-h1 <program-handle>")
                return
            handle = parts[1]
            self.add_chat_msg("system", f"Syncing HackerOne program: {handle}...")
            self.send_ws({
                "type": "sync_hackerone",
                "handle": handle,
            })
            return

        if cmd == "/targets":
            self.send_ws({"type": "list_targets"})
            return

        if cmd in ("/help", "/?"):
            self.add_chat_msg("system", "Commands: /add-tool <url> [cat]  /tools  /marketplace  /remove-tool <id>")
            self.add_chat_msg("system", "          /export <fmt>  /dry-run  /split  /config  /bb  /target <name>")
            self.add_chat_msg("system", "          /recon  /brute <type>  /report  /submit  /sync-h1 <handle>  /targets")
            return

        self.add_chat_msg("system", f"Unknown command: {cmd}. Use /help for available commands.")

    def send_approval(self, approved: bool):
        if self.pending_approval and self.ws:
            tool_id = self.pending_approval["toolId"]
            session_id = self.pending_approval["sessionId"]
            request_id = self.pending_approval["requestId"]
            self.send_ws({
                "type": "tool_call_approval",
                "sessionId": session_id,
                "requestId": request_id,
                "approved": approved
            })
            if self.audit_logger:
                if approved:
                    self.audit_logger.tool_approved(session_id, tool_id, request_id)
                else:
                    self.audit_logger.tool_denied(session_id, tool_id, request_id)
            self.add_chat_msg("system", f"{'Approved' if approved else 'Denied'}: {tool_id}")
            self.pending_approval = None
            self.approval_frame.place_forget()

    def send_download_approval(self, approved: bool):
        if not self.pending_download:
            self.download_frame.place_forget()
            return
        if not approved:
            self.add_chat_msg("system", "Download cancelled.")
            if self.audit_logger:
                self.audit_logger.system_event("Tool download denied by user", "warn")
            self.pending_download = None
            self.download_frame.place_forget()
            return

        dd = self.pending_download
        self.pending_download = None
        self.download_frame.place_forget()
        self.add_chat_msg("system", f"Downloading {dd['repo']}...")
        if self.audit_logger:
            self.audit_logger.system_event(f"Tool download approved: {dd['repo']}", "info")

        def do_install():
            try:
                ok, msg, spec = self.tool_loader.install_tool(dd["url"], category=dd.get("category", "recon"))
                if ok and spec:
                    self.msg_queue.put(("system", f"✓ {msg}"))
                    if self.audit_logger:
                        self.audit_logger.tool_installed(spec.id, spec.repo, spec.version, spec.binary_path)
                    self.send_ws({
                        "type": "register_github_tool",
                        "url": dd["url"],
                        "category": dd.get("category", "recon"),
                        "tool": spec.__dict__ if hasattr(spec, "__dict__") else spec,
                    })
                    if self.tools_view:
                        self.root.after(0, self.render_tools)
                    if self.marketplace_view:
                        self.root.after(0, self.render_marketplace)
                else:
                    self.msg_queue.put(("system", f"✗ {msg}"))
                    if self.audit_logger:
                        self.audit_logger.system_event(f"Tool install failed: {msg}", "error")
            except Exception as e:
                self.msg_queue.put(("system", f"✗ Install error: {e}"))
                if self.audit_logger:
                    self.audit_logger.system_event(f"Tool install exception: {e}", "error")

        threading.Thread(target=do_install, daemon=True).start()

    def show_approval(self, tool_id: str, args: dict, request_id: str, session_id: str):
        self.pending_approval = {"toolId": tool_id, "args": args, "requestId": request_id, "sessionId": session_id}
        self.approval_text.config(text=f"Tool: {tool_id}\n{json.dumps(args, indent=2)}")
        self.approval_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

    # ─── WebSocket ────────────────────────────────────────────────────────
    def start_ws_thread(self):
        threading.Thread(target=self.ws_loop, daemon=True).start()

    def ws_loop(self):
        if not self.token:
            self.msg_queue.put(("error", "No auth token found. Start gateway first."))
            return
        while True:
            try:
                asyncio.run(self._ws_connect())
            except Exception as e:
                self.msg_queue.put(("error", f"WS error: {e}"))
            time.sleep(3)

    async def _ws_connect(self):
        async with websockets.connect(WS_URL) as ws:
            self.ws = ws
            await ws.send(json.dumps({"type": "auth", "token": self.token}))
            self.msg_queue.put(("connected", None))
            async for msg in ws:
                data = json.loads(msg)
                self.msg_queue.put(("msg", data))

    def send_ws(self, msg: dict):
        if self.ws:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.ws.send(json.dumps(msg)))
            except Exception as e:
                self.add_chat_msg("system", f"Send failed: {e}")

    def poll_queue(self):
        try:
            while True:
                kind, data = self.msg_queue.get_nowait()
                if kind == "connected":
                    self.connected = True
                    self.conn_label.config(text="● Online", fg=SUCCESS)
                    self.add_chat_msg("system", "Connected to gateway")
                elif kind == "error":
                    self.add_chat_msg("system", data)
                elif kind == "msg":
                    self.handle_msg(data)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def handle_msg(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "auth_result":
            self.authed = msg.get("ok", False)
            if not self.authed:
                self.add_chat_msg("system", "Auth rejected — token file may be stale")
        elif mtype == "agent_status":
            sid = msg.get("sessionId")
            if sid == self.current_session_id:
                state = msg.get("state", "idle")
                detail = msg.get("detail", "")
                self.set_state(state, detail)
                if state == "thinking":
                    self.session_start = time.time()
                if state == "awaiting_approval":
                    self.pending_approval = None
        elif mtype == "tool_call_request":
            sid = msg.get("sessionId")
            if sid == self.current_session_id:
                self.show_approval(msg.get("toolId", "?"), msg.get("args", {}), msg.get("requestId", ""), sid)
        elif mtype == "tool_call_result":
            sid = msg.get("sessionId")
            if sid == self.current_session_id:
                tool_id = msg.get("toolId", "?")
                ok = msg.get("ok", False)
                output = msg.get("output", "")
                error = msg.get("error", "")
                duration = msg.get("durationMs", 0)
                if ok:
                    self.add_chat_msg("result", f"[{tool_id}] ok ({duration}ms)\n{output}", tool_id)
                else:
                    self.add_chat_msg("result", f"[{tool_id}] error ({duration}ms)\n{error}", tool_id)
                if self.audit_logger:
                    self.audit_logger.tool_executed(sid, tool_id, ok, duration, output, error)
        elif mtype == "sessions_snapshot":
            self.sessions = msg.get("sessions", [])
            if self.server_view:
                self.render_sessions()
        elif mtype == "config_state":
            if not msg.get("nimApiKeySet", False):
                self.add_chat_msg("system", "NIM API key not set — agent will not respond.")
        elif mtype == "stream_token":
            token = msg.get("token", msg.get("text", ""))
            self.stream_buffer += token
            if self.stream_label and self.stream_label.winfo_exists():
                self.stream_label.config(text=self.stream_buffer)
            else:
                self.add_stream_msg(self.stream_buffer)
            return
        elif mtype == "agent_plan":
            steps = msg.get("steps", [])
            self.plan_steps = steps
            plan_text = "PLAN:\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
            self.add_chat_msg("system", plan_text)
            return
        elif mtype == "recon_complete":
            result = msg.get("result", {})
            success = result.get("success", False)
            target = result.get("target", "?")
            findings = result.get("total_findings", 0)
            duration = result.get("duration_seconds", 0)
            if success:
                self.add_chat_msg("system", f"[RECON] {target} complete — {findings} findings in {duration}s")
            else:
                self.add_chat_msg("system", f"[RECON] {target} failed: {result.get('error', 'unknown')}")
            return

        elif mtype == "brute_complete":
            result = msg.get("result", {})
            success = result.get("success", False)
            attack = result.get("attack_type", "?")
            count = result.get("results_count", 0)
            if success:
                self.add_chat_msg("system", f"[BRUTE] {attack} complete — {count} results")
            else:
                self.add_chat_msg("system", f"[BRUTE] failed: {result.get('error', 'unknown')}")
            return

        elif mtype == "report_generated":
            files = msg.get("files", {})
            count = msg.get("vulnerability_count", 0)
            self.add_chat_msg("system", f"[REPORT] Generated with {count} vulns — files: {', '.join(files.keys())}")
            return

        elif mtype == "targets_list":
            targets = msg.get("targets", [])
            self.add_chat_msg("system", f"Targets ({len(targets)}):")
            for t in targets:
                name = t.get("name", "?")
                platform = t.get("platform", "?")
                enabled = "✓" if t.get("enabled") else "✗"
                self.add_chat_msg("system", f"  {enabled} {name} ({platform})")
            return

        elif mtype == "github_tool_status":
            success = msg.get("success", False)
            message = msg.get("message", "")
            tool = msg.get("tool")
            if success and tool:
                self.add_chat_msg("system", f"[github] {message} — {tool.get('id')} {tool.get('version')}")
            else:
                self.add_chat_msg("system", f"[github] {message}")

    # ─── Animation ────────────────────────────────────────────────────────
    def animate(self):
        self.anim_t += 0.03
        state = self.current_state
        if state in ("thinking", "running_tool", "awaiting_approval"):
            draw_planet(self.state_canvas, 28, self.anim_t*0.6, (__import__('math').sin(self.anim_t*1.5)+1)/2, scale=1.15)
        elif state == "done":
            draw_spiral(self.state_canvas, 28, self.anim_t*0.8, scale=1.15)
        elif state == "error":
            draw_planet(self.state_canvas, 28, 0, 0, scale=1.15)
        else:
            draw_planet(self.state_canvas, 28, 0, 0, scale=1.15)
        if self.session_start and state not in ("done", "error", "idle"):
            elapsed = time.time() - self.session_start
            self.timer_label.config(text=f"T+{elapsed:.1f}s")
        self.root.after(50, self.animate)

def main():
    root = tk.Tk()
    app = CybertronGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
