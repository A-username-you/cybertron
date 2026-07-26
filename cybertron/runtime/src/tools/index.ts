import type { ToolDefinition } from "@cybertron/shared";
import { runSubfinder } from "./recon/subfinder.js";
import { runHttpx } from "./crawl/httpx.js";
import { runNuclei } from "./scan/nuclei.js";
import { runGitleaks } from "./secrets/gitleaks.js";
import { runYara } from "./defense/yara.js";
import { runExploitStub } from "./exploit/stub.js";

/**
 * Full catalog across both teams. Only entries marked implemented:true have
 * a working handler below — the rest are real, named slots in the catalog
 * with no handler yet, rendered honestly in the UI rather than hidden.
 */
export const TOOL_CATALOG: ToolDefinition[] = [
  // --- red team: recon ---
  { id: "subfinder", category: "recon", label: "Subdomain enumeration (subfinder)", autoApprove: true, implemented: true },
  { id: "amass", category: "recon", label: "Attack surface mapping (amass)", autoApprove: true, implemented: false },
  { id: "dnsx", category: "recon", label: "DNS resolution (dnsx)", autoApprove: true, implemented: false },
  { id: "asnmap", category: "recon", label: "ASN mapping", autoApprove: true, implemented: false },
  { id: "shodan-lookup", category: "recon", label: "Shodan lookup", autoApprove: true, implemented: false },
  // --- red team: crawl ---
  { id: "httpx", category: "crawl", label: "HTTP probing (httpx)", autoApprove: true, implemented: true },
  { id: "katana", category: "crawl", label: "Web crawler (katana)", autoApprove: true, implemented: false },
  { id: "gau", category: "crawl", label: "Archived URL discovery (gau)", autoApprove: true, implemented: false },
  { id: "wayback", category: "crawl", label: "Wayback machine URLs", autoApprove: true, implemented: false },
  // --- red team: scan ---
  { id: "nuclei", category: "scan", label: "Vulnerability templates (nuclei)", autoApprove: true, implemented: true },
  { id: "nikto", category: "scan", label: "Web server scan (nikto)", autoApprove: true, implemented: false },
  { id: "nmap", category: "scan", label: "Port scan (nmap)", autoApprove: true, implemented: false },
  { id: "sslscan", category: "scan", label: "TLS config scan", autoApprove: true, implemented: false },
  { id: "ffuf", category: "scan", label: "Directory/param fuzzing (ffuf)", autoApprove: true, implemented: false },
  // --- shared: secrets ---
  { id: "gitleaks", category: "secrets", label: "Secrets detection (gitleaks)", autoApprove: true, implemented: true },
  { id: "trufflehog", category: "secrets", label: "Secrets detection (trufflehog)", autoApprove: true, implemented: false },
  { id: "github-dorking", category: "secrets", label: "GitHub dorking", autoApprove: true, implemented: false },
  // --- blue team: defense ---
  { id: "yara-scan", category: "defense", label: "Malware/pattern detection (yara)", autoApprove: true, implemented: true },
  { id: "log-triage", category: "defense", label: "Log/event triage", autoApprove: true, implemented: false },
  { id: "ioc-check", category: "defense", label: "IOC reputation check", autoApprove: true, implemented: false },
  { id: "ids-rule-test", category: "defense", label: "IDS/IPS rule test (suricata)", autoApprove: true, implemented: false },
  { id: "siem-query", category: "defense", label: "SIEM query", autoApprove: true, implemented: false },
  // --- exploit verification: never auto-approved, either team ---
  { id: "sqlmap", category: "exploit", label: "SQLi verification (sqlmap)", autoApprove: false, implemented: false },
  { id: "xss-verify", category: "exploit", label: "XSS payload verification", autoApprove: false, implemented: false },
  { id: "ssrf-verify", category: "exploit", label: "SSRF verification", autoApprove: false, implemented: false },
  { id: "auth-bypass-check", category: "exploit", label: "Auth/IDOR bypass check", autoApprove: false, implemented: false },
];

export type ToolHandler = (args: Record<string, string>) => Promise<string>;

export const TOOL_HANDLERS: Record<string, ToolHandler> = {
  subfinder: runSubfinder,
  httpx: runHttpx,
  nuclei: runNuclei,
  gitleaks: runGitleaks,
  "yara-scan": runYara,
  sqlmap: runExploitStub,
  "xss-verify": runExploitStub,
  "ssrf-verify": runExploitStub,
  "auth-bypass-check": runExploitStub,
};

export function getTool(id: string): ToolDefinition | undefined {
  return TOOL_CATALOG.find((t) => t.id === id);
}
