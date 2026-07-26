import { randomBytes } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

/**
 * Not passkeys/WebAuthn — that needs a credential store, an RP id, and a
 * library like @simplewebauthn/server, which is a real follow-up but more
 * than this pass covers. This is the practical equivalent for a localhost
 * daemon: a per-machine shared secret, generated once, stored 0600 in the
 * user's home directory — the same model Jupyter's own local server uses.
 *
 * CYBERTRON_AUTH_TOKEN env var overrides the file, for CI/scripting.
 */

const TOKEN_DIR = path.join(os.homedir(), ".cybertron");
const TOKEN_PATH = path.join(TOKEN_DIR, "auth-token");

export function getOrCreateToken(): string {
  if (process.env.CYBERTRON_AUTH_TOKEN) return process.env.CYBERTRON_AUTH_TOKEN;
  if (existsSync(TOKEN_PATH)) return readFileSync(TOKEN_PATH, "utf-8").trim();

  mkdirSync(TOKEN_DIR, { recursive: true });
  const token = randomBytes(24).toString("hex");
  writeFileSync(TOKEN_PATH, token, { mode: 0o600 });
  return token;
}

export function tokenFilePath(): string {
  return TOKEN_PATH;
}
