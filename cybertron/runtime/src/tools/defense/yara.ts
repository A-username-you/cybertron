import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";

const execFileAsync = promisify(execFile);

/**
 * Real wrapper around `yara` — scans a file or directory against a rules
 * file for known-bad patterns. This is the blue-team counterpart to the
 * red-team wrappers: same shape (validate args, shell out to a real
 * installed binary, return raw output), used for detection instead of
 * offense. https://virustotal.github.io/yara/
 *
 * Requires the `yara` binary and a .yar rules file on disk — this project
 * doesn't ship rules; point rulesPath at your own or a known set like
 * YARA-Rules/rules.
 */
export async function runYara(args: Record<string, string>): Promise<string> {
  const rulesPath = args.rulesPath;
  const targetPath = args.targetPath;

  if (!rulesPath || !existsSync(rulesPath)) {
    throw new Error("yara: 'rulesPath' arg missing or does not exist on disk");
  }
  if (!targetPath || !existsSync(targetPath)) {
    throw new Error("yara: 'targetPath' arg missing or does not exist on disk");
  }

  try {
    const { stdout } = await execFileAsync(
      "yara",
      ["-r", rulesPath, targetPath],
      { timeout: 60_000 }
    );
    return stdout.trim() || "(no rule matches)";
  } catch (err: any) {
    if (err.code === "ENOENT") {
      throw new Error("yara binary not found on PATH. Install: https://virustotal.github.io/yara/");
    }
    // yara can exit non-zero depending on match/version behavior — surface stdout if we have it
    if (typeof err.stdout === "string" && err.stdout.length > 0) return err.stdout.trim();
    throw new Error(`yara failed: ${err.message}`);
  }
}
