import { app, BrowserWindow, ipcMain } from "electron";
import { spawn, type ChildProcess } from "node:child_process";
import * as path from "node:path";
import * as http from "node:http";
import { existsSync, readFileSync } from "node:fs";
import * as os from "node:os";
import WebSocket from "ws";

// Force loopback traffic to bypass any system-configured proxy. Kept as
// belt-and-suspenders even though the real fix below removes the renderer
// from the networking picture entirely.
app.commandLine.appendSwitch("proxy-bypass-list", "127.0.0.1;localhost;<local>");

// A second `cybertron desktop` launch — e.g. a GUI process left running in
// the background from an interrupted terminal session (Ctrl-C reliably
// kills the foreground CLI step, but not necessarily an already-detached
// GUI window) — would otherwise fight the first instance over port 8765 and
// over which one's window is "the" window. This guarantees only one
// instance actually runs; a second launch attempt just focuses the first
// instance's window and exits instead of creating a conflicting process.
const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

/**
 * This is the file that actually fixes your static-export problem.
 *
 * The Next.js UI is a plain static export (app/out/) — no Node server
 * doing agent work behind it, so `output: "export"` works exactly as
 * intended. It's served to the renderer via a tiny local HTTP server (see
 * startStaticServer below) rather than `file://` directly: Next's static
 * export always emits absolute asset paths (`/_next/static/...`), which
 * resolve correctly against a real HTTP server's root but resolve against
 * the filesystem root under `file://`, 404ing every CSS/JS asset silently
 * — confirmed directly by inspecting the built index.html's own links.
 * Every previously-broken "API route" concern moves to `runtimeProcess`
 * below, a real Node process talking WebSocket on localhost — the
 * renderer never needs an API route to reach it.
 *
 * ARCHITECTURE CHANGE from earlier: the renderer used to open its own
 * `new WebSocket(...)` directly to the gateway. Across repeated real
 * testing, that path never worked reliably in Electron, while the exact
 * same gateway connected fine every time from plain Node (the TUI, this
 * main process). Rather than keep guessing why Chromium's renderer
 * networking was failing (proxy config, sandbox, file:// origin quirks —
 * never confirmed which), this main process now owns the ONE WebSocket
 * connection to the gateway itself, using the same `ws` package and the
 * same unsandboxed-Node context the TUI already proved works. The renderer
 * talks to *this process* over Electron's own IPC, which doesn't touch
 * browser networking at all. A plain browser tab (not Electron) still uses
 * a direct WebSocket in page.tsx — that path was never the one failing.
 */

const MIME_TYPES: Record<string, string> = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".css": "text/css",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".ico": "image/x-icon",
  ".txt": "text/plain",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

/**
 * `next build`'s static export always emits absolute asset paths
 * (`/_next/static/...`), which is correct for a real HTTP server serving
 * from domain root but breaks under `file://` — a `file://.../index.html`
 * page resolves `/_next/...` against the filesystem *root*, not the
 * directory index.html lives in, so every CSS/JS asset 404s silently.
 * Verified directly: the built index.html's own links are all
 * `href="/_next/..."`. Rather than post-process Next's output to rewrite
 * paths (fragile, breaks the moment a new asset type shows up), serving
 * `out/` from a tiny local HTTP server sidesteps the whole problem —
 * absolute paths resolve exactly as intended against that server's root.
 */
function startStaticServer(rootDir: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const requestPath = decodeURIComponent((req.url ?? "/").split("?")[0]);
      const relative = requestPath === "/" ? "index.html" : requestPath.replace(/^\/+/, "");
      const filePath = path.normalize(path.join(rootDir, relative));

      if (!filePath.startsWith(path.normalize(rootDir))) {
        res.writeHead(403);
        res.end("forbidden");
        return;
      }

      readFileFallback(filePath, (err, data) => {
        if (err || !data) {
          res.writeHead(404);
          res.end("not found");
          return;
        }
        res.writeHead(200, { "Content-Type": MIME_TYPES[path.extname(filePath)] ?? "application/octet-stream" });
        res.end(data);
      });
    });

    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address && typeof address === "object") resolve(address.port);
      else reject(new Error("static server failed to report a port"));
    });
  });
}

function readFileFallback(filePath: string, cb: (err: NodeJS.ErrnoException | null, data?: Buffer) => void) {
  try {
    cb(null, readFileSync(filePath));
  } catch (err) {
    cb(err as NodeJS.ErrnoException);
  }
}

let runtimeProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
let gatewayWs: WebSocket | null = null;
let gatewayWsStatus: "connecting" | "open" | "closed" | "error" = "connecting";

/**
 * `mainWindow !== null` is not sufficient — Electron can leave the JS
 * reference non-null while the underlying native window/webContents has
 * already been destroyed, and calling .send() on it throws "Object has
 * been destroyed" as an UNCAUGHT exception in the main process (this is
 * exactly what crashed the app during real testing: a gateway-socket
 * "close" event fired after the window was gone, and the un-guarded
 * `mainWindow?.webContents.send(...)` call threw). Every send goes
 * through here now instead of being called directly.
 */
function safeSend(channel: string, ...args: unknown[]) {
  if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.webContents.isDestroyed()) {
    mainWindow.webContents.send(channel, ...args);
  }
}

const isDev = !app.isPackaged;

// Mirrors GATEWAY_HOST/GATEWAY_PORT in shared/src/protocol.ts — duplicated
// rather than imported, since that package is ESM-only and this workspace
// compiles to CommonJS.
const GATEWAY_HOST = "127.0.0.1";
const GATEWAY_PORT = 8765;

function runtimeEntryPath(): string {
  return isDev
    ? path.join(__dirname, "..", "..", "runtime", "dist", "server.js")
    : path.join(process.resourcesPath, "runtime", "server.js");
}

function readLocalToken(): string | null {
  try {
    const tokenPath = path.join(os.homedir(), ".cybertron", "auth-token");
    return existsSync(tokenPath) ? readFileSync(tokenPath, "utf-8").trim() : null;
  } catch {
    return null;
  }
}

function isGatewayUp(): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://${GATEWAY_HOST}:${GATEWAY_PORT}/health`, () => resolve(true));
    req.on("error", () => resolve(false));
    req.setTimeout(500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function waitForGateway(retries = 30): Promise<void> {
  return new Promise((resolve, reject) => {
    const attempt = (n: number) => {
      const req = http.get(`http://${GATEWAY_HOST}:${GATEWAY_PORT}/health`, () => resolve());
      req.on("error", () => {
        if (n <= 0) return reject(new Error("runtime gateway never became healthy"));
        setTimeout(() => attempt(n - 1), 300);
      });
    };
    attempt(retries);
  });
}

function startRuntime() {
  runtimeProcess = spawn(process.execPath, [runtimeEntryPath()], {
    env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" },
    stdio: "inherit",
  });
  runtimeProcess.on("exit", (code) => {
    if (code !== 0) {
      console.warn(
        `[cybertron-electron] the gateway process this window spawned exited unexpectedly (code ${code}). ` +
          "If another cybertron window/TUI/server is also running, that's likely a port conflict; " +
          "otherwise check the console output above for the actual error."
      );
    }
    runtimeProcess = null;
  });
}

/**
 * The actual fix. Connects to the gateway from this always-unsandboxed,
 * always-plain-Node process — the same kind of connection the TUI makes,
 * proven reliable in every real test so far — and relays messages to/from
 * the renderer over IPC instead of letting the renderer touch the network
 * itself at all.
 */
let quitting = false;
let reconnectAttempt = 0;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 10000;

function connectToGateway() {
  setGatewayWsStatus("connecting");
  const socket = new WebSocket(`ws://${GATEWAY_HOST}:${GATEWAY_PORT}`);
  gatewayWs = socket;

  socket.on("open", () => {
    reconnectAttempt = 0;
    setGatewayWsStatus("open");
  });
  socket.on("close", () => {
    setGatewayWsStatus("closed");
    scheduleReconnect();
  });
  socket.on("error", (err) => {
    console.error("[cybertron-electron] gateway connection error:", err.message);
    setGatewayWsStatus("error");
    // "close" always follows "error" for a ws client socket, which is what
    // schedules the retry — nothing extra needed here.
  });
  socket.on("message", (data) => {
    safeSend("cybertron-message", data.toString());
  });
}

function scheduleReconnect() {
  if (quitting || reconnectTimer) return;
  const delay = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempt, RECONNECT_MAX_MS);
  reconnectAttempt += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (!quitting) connectToGateway();
  }, delay);
}

function setGatewayWsStatus(status: typeof gatewayWsStatus) {
  gatewayWsStatus = status;
  safeSend("cybertron-ws-status", status);
}

ipcMain.on("cybertron-send", (_event, json: string) => {
  if (gatewayWs?.readyState === WebSocket.OPEN) {
    gatewayWs.send(json);
  } else {
    console.warn("[cybertron-electron] dropped outgoing message, gateway socket not open:", gatewayWsStatus);
  }
});

ipcMain.handle("cybertron-get-ws-status", () => gatewayWsStatus);
ipcMain.handle("cybertron-get-token", () => readLocalToken());

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: "#14141f", // matches --bg in the Hermes-accurate palette
    icon: path.join(__dirname, "..", "build", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isDev) mainWindow.webContents.openDevTools({ mode: "detach" });

  // This is a dev tool that rebuilds constantly — a stale cached copy of
  // an old build (especially the unhashed index.html, which can still
  // reference an old build's asset filenames if `out/` wasn't cleaned)
  // showing up instead of the current one is a real, confusing failure
  // mode. Clearing on every launch trades a little startup time for never
  // wondering whether you're looking at old output.
  await mainWindow.webContents.session.clearCache();

  const useLiveNextDev = process.env.CYBERTRON_UI_DEV === "1";
  const staticRoot = isDev
    ? path.join(__dirname, "..", "..", "app", "out")
    : path.join(process.resourcesPath, "app");
  const staticIndexPath = path.join(staticRoot, "index.html");

  if (!useLiveNextDev && !existsSync(staticIndexPath)) {
    console.error(
      `[cybertron-electron] ${staticIndexPath} doesn't exist — the app workspace hasn't been built.\n` +
        "[cybertron-electron] from the repo root, run: npm run build --workspace=app"
    );
    await mainWindow.loadURL(
      "data:text/html,<body style='background:%2314141f;color:%23FFF8DC;font-family:monospace;padding:2rem'>" +
        "app/out/index.html not found.<br>Run <code>npm run build --workspace=app</code> from the repo root, then relaunch.</body>"
    );
    return;
  }

  let uiEntry: string;
  if (useLiveNextDev) {
    uiEntry = "http://localhost:3000";
  } else {
    const port = await startStaticServer(staticRoot);
    uiEntry = `http://127.0.0.1:${port}/index.html`;
  }
  await mainWindow.loadURL(uiEntry);
}

app.whenReady().then(async () => {
  const alreadyUp = await isGatewayUp();
  if (alreadyUp) {
    console.log(
      "[cybertron-electron] a gateway is already running on port 8765 (another window, " +
        "`cybertron server`, or a TUI session) — reusing it instead of spawning a new one."
    );
  } else {
    startRuntime();
    try {
      await waitForGateway();
    } catch (err) {
      console.error("[cybertron-electron]", err);
    }
  }

  connectToGateway();
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform === "darwin") {
    // Mac convention: the app (and its dock icon) stays alive with no
    // windows open. Leave the runtime process and gateway connection
    // running so the "activate" handler above can reopen a window against
    // a backend that's still there, instead of a dead one. Full teardown
    // only happens on an actual quit — see before-quit below.
    return;
  }
  quitting = true;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  gatewayWs?.close();
  runtimeProcess?.kill();
  app.quit();
});

app.on("before-quit", () => {
  quitting = true;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  gatewayWs?.close();
  runtimeProcess?.kill();
});
