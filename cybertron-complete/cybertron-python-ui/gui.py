#!/usr/bin/env python3
"""
Cybertron GUI (Python) — Desktop UI for the Cybertron Agent.
Tkinter + Canvas pixel art. Connects to the Node.js runtime gateway.
Hermes-style chat transcript with warm-glow dark theme.
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
        self.root.geometry("1100x740")
        self.root.minsize(780, 540)

        self.connected = False
        self.authed = False
        self.current_state = "idle"
        self.status_text = "idle"
        self.state_detail = ""
        self.sessions: List[Dict[str,Any]] = []
        self.server_view = False
        self.pending_approval: Optional[Dict[str,Any]] = None
        self.session_start = 0
        self.ws = None
        self.anim_t = 0
        self.msg_queue = queue.Queue()
        self.current_session_id = self.new_session_id()
        self.reconnect_attempt = 0

        self.token = ""
        if TOKEN_PATH.exists():
            self.token = TOKEN_PATH.read_text().strip()

        self.build_ui()
        self.start_ws_thread()
        self.poll_queue()
        self.animate()

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

        self.server_btn = tk.Button(header, text="Server View", font=("IBM Plex Mono", 9),
                                    bg=SURFACE_2, fg=TEXT_MUTED, bd=1, relief=tk.FLAT,
                                    activebackground=SURFACE_2, activeforeground=GOLD,
                                    cursor="hand2", command=self.toggle_server)
        self.server_btn.pack(side=tk.RIGHT, padx=8, pady=8)

        # Content
        content = tk.Frame(main, bg=SURFACE_0)
        content.pack(fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        # Left: Chat area
        left = tk.Frame(content, bg=SURFACE_0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
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

        # Chat transcript (Hermes-style bubbles)
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

        # Right: Sidebar
        self.sidebar = tk.Frame(content, bg=SURFACE_1, bd=1, relief=tk.FLAT)
        self.sidebar.grid(row=0, column=1, rowspan=3, sticky="nsew")
        self.sidebar.config(highlightbackground=BORDER, highlightthickness=1)

        tk.Label(self.sidebar, text="SESSIONS", font=("IBM Plex Mono", 9, "bold"),
                 bg=SURFACE_1, fg=BRONZE).pack(anchor="w", padx=14, pady=(14, 8))

        self.session_list = tk.Frame(self.sidebar, bg=SURFACE_1)
        self.session_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

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
        for w in self.session_list.winfo_children():
            w.destroy()
        if not self.sessions:
            tk.Label(self.session_list, text="No active sessions", font=("IBM Plex Mono", 9),
                     bg=SURFACE_1, fg=TEXT_MUTED).pack(pady=20)
            return
        colors = {"thinking": TEAL, "running_tool": TEAL, "writing": AMBER, "done": SUCCESS,
                  "idle": TEXT_MUTED, "awaiting_approval": DANGER, "error": DANGER}
        for s in self.sessions[-10:]:
            frame = tk.Frame(self.session_list, bg=SURFACE_0, bd=1, relief=tk.FLAT)
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
        self.server_btn.config(fg=GOLD if self.server_view else TEXT_MUTED,
                               text="Session View" if self.server_view else "Server View")
        if self.server_view and self.ws:
            self.send_ws({"type": "list_sessions"})

    def send_goal(self):
        goal = self.goal_entry.get().strip()
        if not goal: return
        self.goal_entry.delete(0, tk.END)
        self.add_chat_msg("user", goal)
        self.add_chat_msg("system", "Starting reconnaissance session...")
        self.current_session_id = self.new_session_id()
        self.send_ws({"type": "session_start", "sessionId": self.current_session_id, "goal": goal, "origin": "gui"})
        self.session_start = time.time()

    def send_approval(self, approved: bool):
        if self.pending_approval and self.ws:
            self.send_ws({
                "type": "tool_call_approval",
                "sessionId": self.pending_approval["sessionId"],
                "requestId": self.pending_approval["requestId"],
                "approved": approved
            })
            self.add_chat_msg("system", f"{'Approved' if approved else 'Denied'}: {self.pending_approval['toolId']}")
            self.pending_approval = None
            self.approval_frame.place_forget()

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
                    self.pending_approval = None  # will be set by tool_call_request
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
        elif mtype == "sessions_snapshot":
            self.sessions = msg.get("sessions", [])
            self.render_sessions()
        elif mtype == "config_state":
            if not msg.get("nimApiKeySet", False):
                self.add_chat_msg("system", "NIM API key not set — agent will not respond.")

    # ─── Animation ────────────────────────────────────────────────────────
    def animate(self):
        self.anim_t += 0.03
        state = self.current_state
        if state in ("thinking", "running_tool", "awaiting_approval"):
            draw_planet(self.state_canvas, 28, self.anim_t*0.6, (__import__('math').sin(self.anim_t*1.5)+1)/2, scale=1.15)
        elif state == "done":
            draw_spiral(self.state_canvas, 28, self.anim_t*0.8, scale=1.15)
        elif state == "error":
            draw_planet(self.state_canvas, 28, 0, 0, scale=1.15)  # could tint red
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
