import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

/**
 * Real wrapper around ProjectDiscovery's `subfinder` binary. Requires
 * subfinder to be installed and on PATH: https://github.com/projectdiscovery/subfinder
 *
 * We only pass a validated domain through -d and a fixed set of flags —
 * never raw, agent-generated shell strings — so there's no command
 * injection surface regardless of what the model outputs.
 */
export async function runSubfinder(args: Record<string, string>): Promise<string> {
  const domain = args.domain;
  if (!domain || !/^[a-zA-Z0-9.-]+$/.test(domain)) {
    throw new Error("subfinder: 'domain' arg missing or contains invalid characters");
  }

  try {
    const { stdout } = await execFileAsync(
      "subfinder",
      ["-d", domain, "-silent", "-timeout", "15"],
      { timeout: 30_000 }
    );
    return stdout.trim() || "(no subdomains found)";
  } catch (err: any) {
    if (err.code === "ENOENT") {
      throw new Error(
        "subfinder binary not found on PATH. Install: https://github.com/projectdiscovery/subfinder"
      );
    }
    throw new Error(`subfinder failed: ${err.message}`);
  }
}
