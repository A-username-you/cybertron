import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

/**
 * Real wrapper around ProjectDiscovery's `nuclei` template scanner.
 * https://github.com/projectdiscovery/nuclei
 *
 * Runs the default community templates against a single validated URL.
 * Severity floor is fixed at medium+ to keep noise down; adjust in args
 * if you want everything.
 */
export async function runNuclei(args: Record<string, string>): Promise<string> {
  const url = args.url;
  if (!url || !/^https?:\/\/[a-zA-Z0-9.:/_-]+$/.test(url)) {
    throw new Error("nuclei: 'url' arg missing or not a valid http(s) URL");
  }
  const severity = args.severity ?? "medium,high,critical";

  try {
    const { stdout } = await execFileAsync(
      "nuclei",
      ["-u", url, "-severity", severity, "-silent", "-timeout", "10"],
      { timeout: 120_000 }
    );
    return stdout.trim() || "(no findings at this severity level)";
  } catch (err: any) {
    if (err.code === "ENOENT") {
      throw new Error("nuclei binary not found on PATH. Install: https://github.com/projectdiscovery/nuclei");
    }
    // nuclei exits non-zero on findings sometimes depending on version; surface stdout if present
    if (err.stdout) return err.stdout.trim();
    throw new Error(`nuclei failed: ${err.message}`);
  }
}
