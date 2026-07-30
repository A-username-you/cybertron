"""Report Generator."""
import json
from pathlib import Path
from datetime import datetime
from typing import List
from cybertron.core.protocol import Finding


class ReportGenerator:
    """Generate security reports in multiple formats."""

    def __init__(self, engagement_id: str):
        self.engagement_id = engagement_id
        self.findings: List[Finding] = []

    def add_finding(self, finding: Finding):
        self.findings.append(finding)

    def generate_markdown(self) -> str:
        lines = [
            f"# Security Assessment Report",
            f"**Engagement:** {self.engagement_id}",
            f"**Date:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Tool:** Cybertron v3.0",
            "",
            "## Findings Summary",
            f"| Severity | Count |",
            f"|----------|-------|",
        ]
        sev_counts = {}
        for f in self.findings:
            sev_counts[f.severity.value] = sev_counts.get(f.severity.value, 0) + 1
        for sev in ["critical", "high", "medium", "low", "info"]:
            lines.append(f"| {sev.upper()} | {sev_counts.get(sev, 0)} |")
        lines.append("")
        lines.append("## Detailed Findings")
        for i, finding in enumerate(self.findings, 1):
            lines.extend([
                f"### {i}. {finding.title}",
                f"- **Severity:** {finding.severity.value.upper()}",
                f"- **Description:** {finding.description}",
                f"- **Evidence:** {finding.evidence}",
                f"- **Remediation:** {finding.remediation}",
                f"- **CWE:** {finding.cwe}",
                f"- **CVSS:** {finding.cvss}",
                ""
            ])
        return "\n".join(lines)

    def generate_json(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "generated_at": datetime.utcnow().isoformat(),
            "tool": "Cybertron v3.0",
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity.value,
                    "description": f.description,
                    "evidence": f.evidence,
                    "remediation": f.remediation,
                    "cwe": f.cwe,
                    "cvss": f.cvss,
                    "timestamp": f.timestamp.isoformat()
                }
                for f in self.findings
            ]
        }

    def save(self, output_dir: str = "."):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        md_path = out / f"report_{self.engagement_id}.md"
        json_path = out / f"report_{self.engagement_id}.json"
        md_path.write_text(self.generate_markdown())
        json_path.write_text(json.dumps(self.generate_json(), indent=2))
        print(f"[Report] Saved to {md_path} and {json_path}")
