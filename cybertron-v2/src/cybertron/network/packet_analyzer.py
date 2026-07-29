"""Packet Analyzer"""
from pathlib import Path
from typing import Dict, List
import structlog
from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

logger = structlog.get_logger()


class PacketAnalyzer(PluginInterface):
    name = "packet_analyzer"
    version = "2.0.0"
    description = "Analyze PCAP files for anomalies"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        findings = []
        pcap_path = Path(target)

        try:
            from scapy.all import rdpcap
            packets = rdpcap(str(pcap_path))

            for pkt in packets:
                if hasattr(pkt, "load"):
                    payload = bytes(pkt.load)
                    if b"Authorization: Basic " in payload:
                        findings.append(Finding(
                            title="HTTP Basic Auth Detected",
                            description="Cleartext credentials in HTTP traffic",
                            severity=Severity.HIGH,
                            category="network",
                            target=str(pcap_path)
                        ))
                    if b"PASS " in payload or b"USER " in payload:
                        findings.append(Finding(
                            title="FTP Credentials in Cleartext",
                            description="FTP login traffic detected",
                            severity=Severity.CRITICAL,
                            category="network",
                            target=str(pcap_path)
                        ))

            findings.append(Finding(
                title="PCAP Analysis Summary",
                description=f"Analyzed {len(packets)} packets",
                severity=Severity.INFO,
                category="network",
                target=str(pcap_path)
            ))
        except ImportError:
            return TaskResult(
                task_id=__import__("uuid").uuid4().hex,
                status=TaskStatus.FAILED,
                error="scapy not installed"
            )

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings
        )
