#!/usr/bin/env node
import { spawn } from "node:child_process";
import * as http from "node:http";
import * as path from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { runTui } from "./cli.js";
import { GATEWAY_HOST, GATEWAY_PORT } from "@cybertron/shared";

const require = createRequire(import.meta.url);

/**
 * `cybertron`          -> TUI (default, no subcommand needed — same shape
 *                          as Hermes's own CLI, where the bare command is
 *                          the primary way in)
 * `cybertron desktop`  -> Electron GUI
 * `cybertron server`   -> headless gateway only, foreground, for running
 *                          on a box you don't want a UI on
 *
 * All three talk to the same gateway process (runtime/src/server.ts).
 * `cybertron` and `cybertron server` will spawn the gateway themselves if
 * it isn't already reachable; `cybertron desktop` delegates that same
 * spawn to Electron's main process instead (see electron/main.ts) since
 * that's the one that owns the gateway's lifecycle when the GUI is open.
 */

const __dirname = path.dirname(fileURLToPath(import.meta.url));

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

function spawnGateway() {
  const serverEntry = path.join(__dirname, "server.js");
  // NOT detached, deliberately: this gateway was auto-spawned as a
  // convenience for this TUI session, not requested as a standalone
  // daemon (that's what `cybertron server` is for). Sessions live only in
  // an in-memory Map anyway, so nothing is gained by letting it outlive
  // the TUI — and letting it outlive the TUI is exactly what caused a
  // real EADDRINUSE crash the first time this got tested for real:
  // `cybertron desktop`, run later, couldn't tell an orphaned auto-spawned
  // gateway from a deliberately-running one and crashed hitting the same
  // port. Tying its lifetime to this process closes that gap.
  const child = spawn(process.execPath, [serverEntry], { stdio: "ignore" });
  const cleanup = () => {
    try {
      child.kill();
    } catch {
      // already gone
    }
  };
  process.on("exit", cleanup);
  process.on("SIGINT", () => {
    cleanup();
    process.exit(130);
  });
  process.on("SIGTERM", () => {
    cleanup();
    process.exit(143);
  });
}

async function ensureGateway() {
  if (await isGatewayUp()) return;
  spawnGateway();
  // poll briefly rather than assuming a fixed startup time
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 200));
    if (await isGatewayUp()) return;
  }
  throw new Error("gateway did not become healthy within ~4s of spawning");
}

async function main() {
  const sub = process.argv[2];

  if (sub === "desktop") {
    const electronMain = path.resolve(__dirname, "..", "..", "electron", "dist", "main.js");
    if (!existsSync(electronMain)) {
      console.error(
        `[cybertron] ${electronMain} doesn't exist — the electron workspace hasn't been built.\n` +
          "[cybertron] from the repo root, run: npm run build --workspace=electron\n" +
          "[cybertron] (and npm run build --workspace=app, if you haven't — the desktop app loads that static export)"
      );
      process.exit(1);
    }
    // `npx electron` resolves against the CURRENT WORKING DIRECTORY's
    // node_modules, not this package's — so run as a global command from
    // some other folder, it can't find the version pinned in
    // electron/package.json and silently downloads a fresh, unrelated one
    // instead. require("electron") returns the actual pinned binary's path
    // (that's the whole content of the npm `electron` package's main
    // export), so this always launches the version this project ships
    // with, regardless of cwd.
    let electronBinPath: string;
    try {
      electronBinPath = require("electron");
    } catch {
      console.error(
        "[cybertron] electron isn't installed. From the repo root, run: npm install --workspaces"
      );
      process.exit(1);
    }
    const child = spawn(electronBinPath, [electronMain], { stdio: "inherit" });
    child.on("exit", (code) => process.exit(code ?? 0));
    return;
  }

  if (sub === "server") {
    console.log("[cybertron] starting gateway in foreground...");
    await import("./server.js");
    return;
  }

  // default: TUI
  if (!process.stdin.isTTY) {
    console.error(
      "[cybertron] the TUI needs an interactive terminal (stdin isn't a TTY here — " +
        "common over non-interactive SSH, inside a script, or in a container without -it).\n" +
        "[cybertron] use `cybertron server` for a headless gateway, or `cybertron desktop` for the GUI instead."
    );
    process.exit(1);
  }

  try {
    await ensureGateway();
  } catch (err: any) {
    console.error(`[cybertron] ${err.message}`);
    process.exit(1);
  }
  runTui();
}

main();
