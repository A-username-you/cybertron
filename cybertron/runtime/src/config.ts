import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

/**
 * Small persisted settings file for values a GUI user needs to be able to
 * set without touching environment variables or a terminal. Starts with
 * just the NIM API key, since "boots fine, errors the moment you send it
 * a goal, with no way to fix that from the app" was the actual reported
 * first-run dead end.
 *
 * Same storage model as auth.ts: JSON at ~/.cybertron/config.json, mode
 * 0600 since it can hold a real API key. An env var set at process start
 * always wins over the file — same precedent as CYBERTRON_AUTH_TOKEN —
 * so scripted/CI setups that already export NIM_API_KEY are unaffected;
 * the file only fills the gap for GUI users who have no shell to export
 * anything into.
 */

const CONFIG_DIR = path.join(os.homedir(), ".cybertron");
const CONFIG_PATH = path.join(CONFIG_DIR, "config.json");

interface StoredConfig {
  nimApiKey?: string;
}

function readConfigFile(): StoredConfig {
  if (!existsSync(CONFIG_PATH)) return {};
  try {
    return JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
  } catch {
    return {}; // corrupt or hand-edited file shouldn't take the gateway down
  }
}

function writeConfigFile(cfg: StoredConfig) {
  mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), { mode: 0o600 });
}

let nimKeySource: "env" | "file" | "none" = "none";

/** Call once at gateway startup, before anything reads NIM_API_KEY. */
export function initConfig(): void {
  if (process.env.NIM_API_KEY) {
    nimKeySource = "env";
    return;
  }
  const cfg = readConfigFile();
  if (cfg.nimApiKey) {
    process.env.NIM_API_KEY = cfg.nimApiKey;
    nimKeySource = "file";
  }
}

/** Called when the settings panel saves a new key. Takes effect on the
 * very next NIM call — nim-client.ts reads process.env.NIM_API_KEY fresh
 * on every request rather than caching it, so no restart is needed. */
export function setNimApiKey(key: string): void {
  const trimmed = key.trim();
  process.env.NIM_API_KEY = trimmed;
  nimKeySource = "file";
  const cfg = readConfigFile();
  cfg.nimApiKey = trimmed;
  writeConfigFile(cfg);
}

export function nimKeyStatus(): { set: boolean; source: "env" | "file" | "none" } {
  return { set: !!process.env.NIM_API_KEY, source: nimKeySource };
}
