import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";

const execFileAsync = promisify(execFile);

/**
 * Real wrapper around `gitleaks`. https://github.com/gitleaks/gitleaks
 *
 * Scans a local repo path (agent should have already cloned or been given
 * a checkout). We only validate that the path exists on disk — there is
 * NO workspace-root confinement here, so the model can point this at any
 * path the runtime process can read. That's a deliberate tradeoff for a
 * tool meant to scan an arbitrarily-located target checkout, but it does
 * mean a misbehaving or confused model could point gitleaks at something
 * like a home directory and have real matches echoed back into the agent
 * transcript and UI. If you want a hard boundary, resolve repoPath and
 * reject anything outside an explicit allowed root before calling this.
 */
export async function runGitleaks(args: Record<string, string>): Promise<string> {
  const repoPath = args.repoPath;
  if (!repoPath || !existsSync(repoPath)) {
    throw new Error("gitleaks: 'repoPath' arg missing or does not exist on disk");
  }

  try {
    const { stdout } = await execFileAsync(
      "gitleaks",
      ["detect", "--source", repoPath, "--no-git", "-v"],
      { timeout: 60_000 }
    );
    return stdout.trim() || "(no secrets detected)";
  } catch (err: any) {
    if (err.code === "ENOENT") {
      throw new Error("gitleaks binary not found on PATH. Install: https://github.com/gitleaks/gitleaks");
    }
    // gitleaks exits 1 when it finds leaks — that's a result, not a failure
    if (typeof err.stdout === "string" && err.stdout.length > 0) {
      return err.stdout.trim();
    }
    throw new Error(`gitleaks failed: ${err.message}`);
  }
}
