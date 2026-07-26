# Cybertron — red + blue team agent, one runtime, one build for every OS

Standalone scaffold — not a patch to your existing Orion v2 source (I don't have that tree in
this session; re-upload it if you want this merged into it directly instead of standalone).

## What's actually in it

**Hacker-AI pattern** (HexStrike AI, PentAGI, Xalgorix, Pentest Copilot): plan → call a real
security tool as a subprocess → observe → iterate. The value is tool orchestration and safety
gating, not generating novel exploit code — so exploitation-category tools are hard-gated behind
explicit human approval and shipped unimplemented (see the honesty table below).

**Hermes Agent pattern** (Nous Research): the agent core runs as its own local process — a
gateway (HTTP+WS), a CLI, an Ink TUI — and every UI is a thin client of that one process, never
a second copy of the agent logic. That's the fix for your static-export blocker: the Next.js UI
here is genuinely static (no API routes doing agent work), and everything dynamic lives in
`runtime/`, a plain Node process that runs the same way on Windows, macOS, and Linux.

**Red + blue, one catalog.** `runtime/src/tools/index.ts` has recon/crawl/scan (red) sitting
next to a `defense` category (blue) in the same tool list, with the same shape: real handler or
honest stub, no fiction either way.

## Visual identity

Three animated pixel-art icons (`app/app/components/StateIcon.tsx`), tied to real state:

| Icon | Fires on | Meaning |
|---|---|---|
| Ringed planet, rotating | `thinking` / `running_tool` / `awaiting_approval` | agent is working |
| Spiral, swirling | `done` (settles back to the planet after ~2s) | "writing output" — this is a proxy, since the protocol has no distinct streaming-text state; `done` is the closest real event to "the model just produced its answer" |
| Star burst, one-shot | a `tool_call_result` with `ok: true` | **assumption**: "something useful" = a tool result landed successfully. If you meant something else (e.g. approval-needed), tell me and I'll remap it — it's a one-line change |

Logo mark used for the app/window icon is the Spiral, generated from the exact same pixel math
as the animation (see `runtime`-adjacent `icon-gen` script, not shipped in this zip — ask if you
want the generator itself rather than just the output files).

## Authentication

The gateway requires a token before it'll do anything beyond respond to `/health`. On first
start it generates one (24 random bytes, hex) and stores it at `~/.cybertron/auth-token` (mode
0600) — same model Jupyter's local server uses, printed to the console every time the gateway
starts. `CYBERTRON_AUTH_TOKEN` overrides it for CI/scripting.

The desktop app and the TUI read that file directly and auto-authenticate, since they're running
as the same local user who owns the gateway. A browser tab hitting the gateway on its own has to
be told the token by a human — that's the password gate you see in `app/app/page.tsx`.

This is **not** passkeys/WebAuthn. A real WebAuthn implementation needs a credential store, a
relying-party id, and a library like `@simplewebauthn/server` — a legitimate next step, but more
than this pass covers. Verified end-to-end in this session: wrong token → rejected, every command
refused pre-auth, correct token from the file → accepted, session commands unlocked after.

honest stub, no fiction either way.

## The GUI layout bug — actual root cause, found and fixed

My previous theory (stale cache) was wrong, and a clean rebuild proved it — same broken layout
came back anyway. The real cause: `next build`'s static export always emits **absolute** asset
paths (`href="/_next/static/css/...`), which resolve correctly against a real HTTP server's root
but resolve against the **filesystem root** under `file://` — so every CSS/JS asset 404'd
silently. Confirmed directly by inspecting the built `index.html`'s own `<link>`/`<script>` tags,
and reproduced the exact failure: the same absolute path that 404's under `file://` returns
`200 OK` once served over HTTP.

The dark background you were seeing wasn't from the (never-loading) CSS at all — it's Electron's
own `backgroundColor` window option, set directly on the `BrowserWindow`, independent of any page
content. That's why colors looked partially present while layout was completely broken: nothing
about the actual stylesheet was working.

**Fix:** `main.ts` now runs a small local HTTP server (`startStaticServer`, plain Node `http`, no
new dependency) serving `app/out/` on an OS-assigned local port, and loads
`http://127.0.0.1:<port>/index.html` instead of `file://.../index.html`. Absolute paths now
resolve exactly as intended. Verified directly: fetched the exact same absolute CSS path a browser
would request, over the new server, confirmed `200 OK` with the correct `.gate-shell` rule intact
in the response bytes.

**Also fixed while investigating, both real, both confirmed from your crash log/screenshot:**
- `setGatewayWsStatus`/message relaying called `mainWindow?.webContents.send(...)` without
  checking `isDestroyed()` — `mainWindow` can be non-null while the underlying native object is
  already gone, and calling `.send()` on it throws an uncaught "Object has been destroyed"
  exception in the main process, crashing exactly like your screenshot showed. All sends now go
  through a `safeSend()` helper that checks first.
- Added `app.requestSingleInstanceLock()` — an interrupted terminal session (Ctrl-C reliably kills
  the foreground CLI step, but not necessarily an already-detached GUI window) could leave a
  `cybertron desktop` process running in the background; a second launch would then fight it over
  port 8765. Now a second launch attempt just focuses the first instance's window instead of
  spawning a conflicting process.

## Terminal (TUI) — closed the real functional gap

The TUI never handled `tool_call_request` at all — if a session hit an exploit-gated tool
(sqlmap, etc.), the agent would call `requestApproval()` and wait forever with no way to respond
from the terminal. Fixed, and actually verified end-to-end (not just read): using
`ink-testing-library` to drive the real `App` component against a scripted fake gateway — sent a
goal, confirmed the approval box rendered with the correct tool/args, pressed `y`, confirmed the
exact `tool_call_approval` message the server received matched. Also added:
- Reconnect-with-backoff on disconnect (was: just says "disconnected" forever)
- A distinct `?` glyph for "awaiting approval," separate from the working spinner
- A turn-elapsed timer, matching the web UI
- Per-goal session IDs instead of one ID reused for the whole TUI session (matches the web UI's
  model, avoids ambiguous state if you send a second goal before the first fully finishes)

## Web UI — responsive pass

There was no `viewport` export and zero media queries — every layout dimension was a fixed pixel
value in inline styles. Rebuilt as an actual responsive system in `globals.css`: three breakpoints
(phone <600px, tablet 600–900px, desktop >900px) driving CSS custom properties, so one set of
media queries controls font size, padding, and density everywhere instead of scattered fixed
values. Specific fixes:
- Status bar (turn timer, active count, Server toggle) now wraps instead of clipping; the two
  least-critical labels hide below 480px instead of squeezing
- Every button and the Server toggle now meet the ~44px minimum touch-target guidance (were sized
  for mouse only)
- The composer stacks input-above-button below 480px instead of staying cramped in a row
- Session rows and log lines use `overflow-wrap: anywhere` and flexible widths instead of fixed
  pixel columns that would clip long URLs/tool output on a narrow screen
- `min-height: 100dvh` instead of `100vh` — accounts for mobile browser chrome (address bar, etc.)
  that `100vh` notoriously ignores

## Getting started (tested end-to-end this session)

```bash
# 1. install + build everything
npm install --workspaces
npm run build --workspace=@cybertron/shared
npm run build --workspace=runtime
npm run build --workspace=electron
npm run build --workspace=app

# 2. make the commands global
cd runtime && npm link
```

`npm link` needs write access to npm's global prefix. If it fails with an EACCES-style
permission error (common on macOS/Linux with the system Node install), either run it with
`sudo npm link`, or point npm at a folder you own once:
`npm config set prefix ~/.npm-global` then add `~/.npm-global/bin` to your `PATH`.

After that, from **any directory**, not just this repo:

```
cybertron            # bare command -> the Ink TUI
cybertron desktop     # -> the Electron GUI
cybertron server      # -> headless gateway only, foreground
```

All three talk to the same gateway; `cybertron` and `cybertron server` spawn it themselves if it
isn't already running, `cybertron desktop` delegates that to Electron's main process instead.

**A real architectural change, after the previous fix didn't resolve it: the renderer no longer
opens a network connection at all in Electron.** Every previous attempt (explicit `127.0.0.1`,
proxy-bypass-list) assumed the renderer's WebSocket would eventually work if the right networking
condition was fixed — but across every real test, it never did, while the exact same gateway
connected instantly and reliably every time from plain Node (the TUI, `cybertron server`). Rather
than keep guessing which browser-networking quirk was responsible, Electron's main process — the
same kind of unsandboxed Node context the TUI already proved works — now owns the one WebSocket
connection to the gateway itself, using the `ws` package directly. The renderer talks to *that*
over Electron's own IPC (`electron/preload.ts` exposes `send`/`onMessage`/`onStatus`/`getToken`;
`electron/main.ts` relays to/from the gateway). IPC doesn't touch browser networking, proxy
config, sandboxing, or file:// origin behavior at all — it's a different transport, not a
different configuration of the same one. A plain browser tab (no Electron bridge present) still
uses a direct WebSocket in `page.tsx`, since that path was never the one that was broken.

Verified in this session: the exact connection code `main.ts` now runs — same `ws` package, same
host/port, same message shape — was tested standalone against a live gateway: connects instantly,
authenticates, receives the relayed result. All five IPC channel names were checked to match
character-for-character between `main.ts` and `preload.ts`. I can't verify the actual Electron
window rendering without your machine, but every piece up to the renderer boundary is now proven,
not assumed. `main.ts` also opens DevTools automatically in dev mode now, so if anything is still
wrong, the real browser console error will be visible immediately instead of needing another
round of guessing.

**A fifth real bug: stuck permanently on "Connecting..." in the desktop app, even though your own
log showed the gateway had booted successfully.** The TUI connected fine; only Electron's renderer
hung. That split points at Chromium's network stack specifically — Electron's renderer honors
system proxy settings (Burp Suite, mitmproxy, a VPN's proxy, all common on a pentesting-oriented
setup), plain Node doesn't. Three-part fix:
1. Gateway now binds explicitly to `127.0.0.1` instead of the wildcard address, and every client
   (TUI, web UI) connects to `127.0.0.1` explicitly instead of the hostname `localhost` — the
   hostname form is what a proxy config actually intercepts, even for loopback traffic.
2. Electron now sets `proxy-bypass-list` for `127.0.0.1;localhost;<local>` before `app.whenReady()`,
   forcing loopback traffic direct regardless of system proxy config.
3. The auth gate no longer has two separate render paths (a silent auto-auth spinner with zero
   error handling, and a manual form) — it's one path now, always showing real connection status,
   a 6-second connect timeout with an actual error message instead of hanging forever, and a
   visible hint if Electron's auto-token delivery didn't work so it's obvious what's happening
   instead of a mysterious stuck screen.

I can't fully verify the proxy theory without your machine, but the explicit-IP fix and the
timeout/error surfacing are correct regardless of root cause — if it's still stuck after this,
the new 6-second timeout will now tell you why instead of hanging silently.

**A fourth real bug: the auth gate looked "dead" — hitting Enter did nothing.** Two separate
issues stacked here:
1. Electron's auto-auth relied on `preload.ts` reading the token file via `fs` — but preload
   scripts run inside `webPreferences.sandbox`, where Node builtins can silently fail with no
   visible error. That's almost certainly why Electron was showing the manual gate at all instead
   of skipping it. Fixed: the always-unsandboxed main process now reads the token and passes it
   as a `?token=` URL param when it loads the page — `page.tsx` reads that param and never
   renders the gate at all when it's present, rather than rendering it and racing to auto-fill.
   Verified: token round-trips correctly through the URL encode/decode.
2. The manual form's real bug: hitting Enter/Connect before the WebSocket finished connecting
   called `.send()` on a socket that was still `CONNECTING` — per the WebSocket spec, that throws
   synchronously, uncaught, invisible in the UI. Fixed: the input and button are now disabled
   until the socket is confirmed open, and a 5s timeout surfaces "no response from the gateway"
   if authentication genuinely stalls, instead of the form just sitting there looking broken.

Per your note that **only the plain web UI should need auth** — that's now actually true: the TUI
authenticates in-process (never shows anything), Electron authenticates via the URL param and
never renders the gate, and only a browser tab with no token param sees the manual form.

**A third real bug, found from your screenshot + log — the biggest one yet:** `cybertron`
(bare TUI) auto-spawns a gateway as a detached background daemon so closing the TUI didn't kill
in-progress work. But nothing else knew that daemon might already be running: `cybertron desktop`
called `startRuntime()` unconditionally in Electron's main process, with no "is one already up"
check first — so it tried to bind port 8765 again and crashed with `EADDRINUSE` the moment you'd
already left a TUI-spawned gateway running. Two-part fix, both verified live:
1. Electron's `isGatewayUp()` check existed in the code already but was never actually called
   before spawning — wired it in. Verified: with a gateway already running, Electron's startup
   check now correctly detects it and skips spawning its own instead of crashing.
2. The TUI's auto-spawned gateway is no longer detached — it's tied to the TUI's own process
   lifetime via `SIGINT`/`SIGTERM`/`exit` cleanup handlers, so pressing esc or Ctrl+C kills it
   too. Verified: spawned gateway confirmed healthy in <1s, then confirmed gone within 1s of the
   parent receiving `SIGINT` — no orphaned daemon left holding the port.

(`cybertron server`, run explicitly, is unaffected — that one's *meant* to keep running
independently as a real headless daemon.)

**A real bug you found by actually running it, fixed just now:** `electron/tsconfig.json` still
had a stale `../shared/**/*` include left over from before `shared` became its own workspace
package — `electron/main.ts` never even imports it, but its presence made `tsc` nest the output
(`electron/dist/electron/main.js` instead of `electron/dist/main.js`), so `cybertron desktop`
couldn't find its own entry point after a clean build. Fixed, and now there are two friendly
checks instead of a silent failure: `cybertron desktop` tells you to run
`npm run build --workspace=electron` if `electron/dist/main.js` is missing, and the Electron
window itself tells you to run `npm run build --workspace=app` if `app/out/index.html` is
missing, instead of either crashing with a cryptic Electron error or showing a permanently blank
window.

**Two real bugs the previous pass found and fixed by actually running it, not just reading the code:**
1. `cybertron desktop` was resolving Electron via `npx electron`, which resolves against the
   *current working directory's* node_modules — so run as a global command from anywhere else,
   it silently downloaded a completely different, unpinned Electron version instead of using the
   one this project ships with. Fixed to resolve the pinned binary directly via
   `require("electron")`, verified: no more surprise downloads, launches the exact pinned 31.7.7.
2. The bare `cybertron` TUI crashed with a raw Ink stack trace if stdin wasn't a TTY (piped,
   scripted, non-interactive SSH, containers without `-it`). Fixed with an explicit TTY check that
   prints a clean message and points at `cybertron server`/`cybertron desktop` instead.

**What's needed for it to actually do something:**
- `NIM_API_KEY` in your environment (the agent reasoning loop calls NVIDIA NIM — without this it
  boots fine but errors the moment you send it a goal)
- `subfinder`, `httpx`, `nuclei`, `gitleaks`, `yara` on PATH for the real tool wrappers to have
  anything to shell out to
- Port 8765 free (the gateway's fixed port for now)

**Verified working in this session**, via the actual global `cybertron` command from outside the
repo: gateway boots and prints its auth token, wrong token rejected, correct token accepted, every
command refused pre-auth, a full session lifecycle (`session_start` → `agent_status` →
`sessions_snapshot`) runs end-to-end, `cybertron desktop` resolves and launches the real pinned
Electron binary (it can't fully open a window in this sandbox — no display — but that's the
sandbox, not the app), and `cybertron` alone in a non-TTY context now fails cleanly instead of
crashing.

## Commands — same shape as Hermes's own CLI

See "Getting started" above for the full command reference and the two bugs found/fixed while
verifying it actually works as a global install.

## The Server toggle

Flip it in the desktop UI (or press `s` in the TUI) and the view switches from "my current run"
to every session active on the gateway, from any connected client — id, goal, state, elapsed
time, tool-call count. This works because the gateway tracks sessions in a map and broadcasts a
snapshot to every connected socket on any change, not just the socket that started a session.
Verified end-to-end in this session: a session_start produces a `sessions_snapshot` broadcast,
an `agent_status` event, and a final snapshot with `finishedAt` set once the run completes
(tested against a live gateway process, not a mock).

## Honest status — what's real vs. stub

| Piece | Status |
|---|---|
| `runtime/src/server.ts` — gateway, multi-session, broadcast | **Real**, smoke-tested live, repeatedly, this session |
| `runtime/src/agent/core.ts` — plan/act/observe loop | **Real** control flow, calls NIM |
| `runtime/src/agent/nim-client.ts` — Nemotron via NVIDIA NIM | **Real** client, needs `NIM_API_KEY` |
| `subfinder` / `httpx` / `nuclei` / `gitleaks` wrappers | **Real** — shell out to the actual binaries |
| `yara-scan` wrapper (blue team) | **Real** — shells out to `yara`, needs your own rules file |
| Everything else in the 21-ish-entry catalog | **Named, categorized, not implemented** — I picked one real tool per category rather than stub all of them blind |
| `exploit` category (sqlmap, xss-verify, ssrf-verify, auth-bypass-check) | **Stub, hard-gated** — no payload logic written, on purpose |
| `runtime/src/cli.tsx` + `bin.ts` — TUI, command routing | **Real**, and now globally installable — `npm link` tested, all three subcommands verified from outside the repo |
| `electron/main.ts` + `preload.ts` | **Real** — spawns the gateway via `ELECTRON_RUN_AS_NODE`, no separate Node install needed |
| `app/` Next.js UI | **Skeleton**, but genuinely builds — `next build` with `output: "export"` ran clean and produced real `out/index.html` in this session |
| Server toggle / sessions dashboard | **Real**, both in the web UI and the TUI (`s` key) |
| Auth token (`runtime/src/auth.ts`) | **Real**, smoke-tested: wrong token rejected, correct token accepted, all commands gated |
| Passkeys/WebAuthn | **Not implemented** — token-based auth is the practical stand-in for now |
| Logo / icon | **Real** — `app/app/components/StateIcon.tsx` renders live; `electron/build/icon.{png,ico,icns}` are real generated binaries (verified: valid PNG 512×512, valid multi-res ICO, valid ICNS), wired into `electron-builder` config and the dev `BrowserWindow` |
| Animated status icon (planet/spiral/burst) | **Real** — tied to actual `agent_status`/`tool_call_result` events, not a demo loop |
| Color palette | **Real** — pulled from Hermes Agent's own published default skin (bronze/gold/amber/cornsilk/teal on navy), not invented |
| TUI visual parity | **Real, partial** — can't render the pixel-art canvas in a terminal, but colors match the same palette, and the status line has a real spinner/glyph driven by the same `agent_status` events |
| Global `cybertron` command | **Real** — `npm link` tested from outside the repo, all three subcommands (bare/desktop/server) verified |
| Windows/macOS/Linux installers | **Config is real**, unbuilt — see `scripts/build-all.md` for why one machine can't produce all three |
