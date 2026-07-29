"""Reconnaissance Agent"""
import asyncio
import socket
from typing import Dict, List, Set
import structlog

from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

logger = structlog.get_logger()


class SubdomainEnumPlugin(PluginInterface):
    name = "subdomain_enum"
    version = "2.0.0"
    description = "Enumerate subdomains via DNS brute force"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        wordlist = options.get("wordlist", "wordlists/subdomains.txt")
        findings = []
        subdomains: Set[str] = set()

        try:
            with open(wordlist) as f:
                words = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            words = ["www", "mail", "ftp", "admin", "api", "dev", "staging", "test"]

        semaphore = asyncio.Semaphore(50)

        async def check_sub(sub: str):
            async with semaphore:
                try:
                    resolver = await asyncio.get_event_loop().getaddrinfo(
                        f"{sub}.{target}", None, family=socket.AF_INET
                    )
                    if resolver:
                        ips = [r[4][0] for r in resolver]
                        subdomains.add(f"{sub}.{target}")
                        findings.append(Finding(
                            title=f"Subdomain discovered: {sub}.{target}",
                            description=f"Resolved to {ips}",
                            severity=Severity.INFO,
                            category="recon",
                            target=f"{sub}.{target}",
                            evidence={"ips": ips}
                        ))
                except Exception:
                    pass

        await asyncio.gather(*[check_sub(w) for w in words[:1000]])

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=list(findings),
            artifacts={"subdomains": list(subdomains)}
        )


class PortScanPlugin(PluginInterface):
    name = "port_scan"
    version = "2.0.0"
    description = "Async TCP port scanner"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 8080, 8443]
        findings = []
        open_ports = []
        semaphore = asyncio.Semaphore(100)

        async def scan_port(port: int):
            async with semaphore:
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(target, port),
                        timeout=2.0
                    )
                    writer.close()
                    await writer.wait_closed()
                    open_ports.append(port)
                    findings.append(Finding(
                        title=f"Open port: {port}",
                        description=f"Port {port} is open on {target}",
                        severity=Severity.INFO,
                        category="port_scan",
                        target=target,
                        evidence={"port": port}
                    ))
                except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                    pass

        await asyncio.gather(*[scan_port(p) for p in common_ports])

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings,
            artifacts={"open_ports": open_ports}
        )
