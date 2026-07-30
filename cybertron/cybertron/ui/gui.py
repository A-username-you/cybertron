#!/usr/bin/env python3
"""Cybertron GUI — Tkinter desktop UI. Connects to Python gateway."""
import asyncio
import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import websockets

GATEWAY_HOST = os.environ.get("CYBERTRON_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("CYBERTRON_PORT", "8765"))
WS_URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws"

THEME = {
    "bg": "#14141f", "fg": "#c0c0c0", "gold": "#FFD700",
    "amber": "#FFBF00", "bronze": "#CD7F32", "green": "#00ff88",
    "red": "#ff4444", "blue": "#4aa8ff", "panel": "#1a1a2e",
    "border": "#333355",
}

class CybertronGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Cybertron v3.0.0")
        self.root.configure(bg=THEME["bg"])
        self.root.geometry("1200x800")
        self.ws = None
        self.authed = False
        self.token = os.environ.get("CYBERTRON_AUTH_TOKEN", "")
        self.pending_approvals = []
        self._build_ui()
        threading.Thread(target=self._ws_loop, daemon=True).start()

    def _build_ui(self):
        header = tk.Frame(self.root, bg=THEME["panel"], height=40)
        header.pack(fill=tk.X, padx=4, pady=4)
        tk.Label(header, text="CYBERTRON", font=("Courier", 16, "bold"),
                 fg=THEME["gold"], bg=THEME["panel"]).pack(side=tk.LEFT, padx=10)
        self.status_label = tk.Label(header, text="● DISCONNECTED", fg=THEME["red"],
                                      bg=THEME["panel"], font=("Courier", 10))
        self.status_label.pack(side=tk.RIGHT, padx=10)

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=THEME["bg"])
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        left = tk.Frame(paned, bg=THEME["bg"])
        paned.add(left, width=700)

        self.log = scrolledtext.ScrolledText(left, bg=THEME["panel"], fg=THEME["fg"],
                                              font=("Courier", 10), wrap=tk.WORD,
                                              insertbackground=THEME["fg"])
        self.log.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        input_frame = tk.Frame(left, bg=THEME["bg"])
        input_frame.pack(fill=tk.X, padx=4, pady=4)
        self.entry = tk.Entry(input_frame, bg=THEME["panel"], fg=THEME["fg"],
                              font=("Courier", 11), insertbackground=THEME["fg"])
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.entry.bind("<Return>", lambda e: self._send_cmd())
        tk.Button(input_frame, text="Send", command=self._send_cmd,
                  bg=THEME["gold"], fg=THEME["bg"], font=("Courier", 10, "bold")).pack(side=tk.RIGHT)

        right = tk.Frame(paned, bg=THEME["bg"])
        paned.add(right, width=400)

        tk.Label(right, text="Sessions", font=("Courier", 12, "bold"),
                 fg=THEME["amber"], bg=THEME["bg"]).pack(anchor=tk.W, padx=4, pady=4)
        self.sessions_list = tk.Listbox(right, bg=THEME["panel"], fg=THEME["fg"],
                                        font=("Courier", 10), selectmode=tk.SINGLE)
        self.sessions_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        tk.Label(right, text="Pending Approvals", font=("Courier", 12, "bold"),
                 fg=THEME["red"], bg=THEME["bg"]).pack(anchor=tk.W, padx=4, pady=4)
        self.approvals_list = tk.Listbox(right, bg=THEME["panel"], fg=THEME["fg"],
                                         font=("Courier", 10), selectmode=tk.SINGLE)
        self.approvals_list.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        btn_frame = tk.Frame(right, bg=THEME["bg"])
        btn_frame.pack(fill=tk.X, padx=4, pady=4)
        tk.Button(btn_frame, text="Approve", command=self._approve_selected,
                  bg=THEME["green"], fg=THEME["bg"]).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Deny", command=self._deny_selected,
                  bg=THEME["red"], fg=THEME["bg"]).pack(side=tk.LEFT, padx=2)

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log.insert(tk.END, f"[{ts}] {msg}\n")
        self.log.see(tk.END)

    def _send_cmd(self):
        cmd = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        if not cmd or not self.ws:
            return
        if cmd.startswith("scan "):
            target = cmd[5:].strip()
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({"type": "session_start", "goal": target})), self.loop)
            self._log(f"Started scan: {target}")
        elif cmd == "sessions":
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({"type": "list_sessions"})), self.loop)
        elif cmd == "tools":
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({"type": "get_tools"})), self.loop)
        else:
            self._log(f"Unknown: {cmd}")

    def _approve_selected(self):
        sel = self.approvals_list.curselection()
        if not sel or not self.pending_approvals:
            return
        approval = self.pending_approvals[sel[0]]
        asyncio.run_coroutine_threadsafe(
            self.ws.send(json.dumps({
                "type": "tool_call_approval", "sessionId": approval["sessionId"],
                "requestId": approval["requestId"], "toolId": approval["toolId"], "approved": True
            })), self.loop)
        self._log(f"Approved {approval['toolId']}")

    def _deny_selected(self):
        sel = self.approvals_list.curselection()
        if not sel or not self.pending_approvals:
            return
        approval = self.pending_approvals.pop(sel[0])
        self.approvals_list.delete(sel[0])
        self._log(f"Denied {approval['toolId']}")

    def _ws_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._connect())

    async def _connect(self):
        while True:
            try:
                self.ws = await websockets.connect(WS_URL)
                self.root.after(0, lambda: self.status_label.config(text="● CONNECTED", fg=THEME["green"]))
                self._log(f"Connected to {WS_URL}")
                if self.token:
                    await self.ws.send(json.dumps({"type": "auth", "token": self.token}))
                async for raw in self.ws:
                    msg = json.loads(raw)
                    self.root.after(0, lambda m=msg: self._handle(m))
            except Exception as e:
                self.root.after(0, lambda: self.status_label.config(text="● DISCONNECTED", fg=THEME["red"]))
                self._log(f"Error: {e}")
                await asyncio.sleep(3)

    def _handle(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "auth_result":
            self.authed = msg.get("ok", False)
            self._log("Auth " + ("OK" if self.authed else "FAILED"))
        elif mtype == "sessions_snapshot":
            self.sessions_list.delete(0, tk.END)
            for s in msg.get("sessions", []):
                self.sessions_list.insert(tk.END, f"{s['id'][:8]} | {s['goal'][:20]} | {s['state']}")
        elif mtype == "agent_status":
            self._log(f"Agent: {msg.get('state')} — {msg.get('detail', '')}")
        elif mtype == "stream":
            self._log(f"→ {msg.get('content', '')[:80]}")
        elif mtype == "tool_call_request":
            self.pending_approvals.append(msg)
            self.approvals_list.insert(tk.END, f"{msg['toolId']} ({msg['sessionId'][:8]})")
            self._log(f"Approval needed: {msg['toolId']}")
        elif mtype == "tool_call_result":
            r = msg.get("result", {})
            self._log(f"Result: {r.get('toolId')} {'OK' if r.get('ok') else 'FAIL'}")
        elif mtype == "error":
            self._log(f"Error: {msg.get('message', '')}")

if __name__ == "__main__":
    root = tk.Tk()
    app = CybertronGUI(root)
    root.mainloop()
