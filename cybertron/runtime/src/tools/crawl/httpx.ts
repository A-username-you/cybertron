import { spawn } from "node:child_process";

/**
 * Real wrapper around ProjectDiscovery's `httpx` probe.
 * https://github.com/projectdiscovery/httpx
 *
 * Target is passed via stdin to -l - equivalent rather than interpolated
 * into a shell string.
 */
export async function runHttpx(args: Record<string, string>): Promise<string> {
  const target = args.target;
  if (!target || !/^[a-zA-Z0-9.:/_-]+$/.test(target)) {
    throw new Error("httpx: 'target' arg missing or contains invalid characters");
  }

  return new Promise((resolve, reject) => {
    const child = spawn(
      "httpx",
      ["-silent", "-status-code", "-title", "-tech-detect"],
      { timeout: 20_000 }
    );
    let out = "";
    let err = "";
    child.stdout.on("data", (d: Buffer) => (out += d.toString()));
    child.stderr.on("data", (d: Buffer) => (err += d.toString()));
    child.on("error", (e: NodeJS.ErrnoException) => {
      if (e.code === "ENOENT") {
        reject(new Error("httpx binary not found on PATH. Install: https://github.com/projectdiscovery/httpx"));
      } else {
        reject(e);
      }
    });
    child.on("close", (code) => {
      const trimmed = out.trim();
      if (trimmed) {
        // httpx sometimes exits non-zero even with a valid result on the line — a result is a result.
        resolve(trimmed);
        return;
      }
      if (code === 0) {
        resolve("(no response)");
        return;
      }
      reject(new Error(`httpx failed (exit ${code}): ${err.trim() || "no output"}`));
    });
    child.stdin.write(target + "\n");
    child.stdin.end();
  });
}
