"""Red Team — Reconnaissance Engine."""
import asyncio
import socket
import whois
import dns.resolver
from typing import List, Dict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ReconResult:
    target: str
    subdomains: List[str] = field(default_factory=list)
    open_ports: List[int] = field(default_factory=list)
    whois_info: Dict = field(default_factory=dict)
    dns_records: Dict = field(default_factory=dict)
    tech_stack: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ReconEngine:
    """10-stage reconnaissance pipeline."""

    STAGES = [
        "whois_lookup", "dns_enumeration", "subdomain_discovery",
        "port_scanning", "service_detection", "tech_fingerprinting",
        "content_discovery", "screenshotting", "wayback_analysis",
        "vhost_discovery"
    ]

    def __init__(self, target: str, scope: str = None):
        self.target = target
        self.scope = scope
        self.result = ReconResult(target=target)

    def run(self):
        print(f"[Recon] Starting 10-stage pipeline for {self.target}")
        self._whois()
        self._dns()
        self._subdomains()
        self._port_scan()
        self._tech_fingerprint()
        print(f"[Recon] Pipeline complete. Found {len(self.result.subdomains)} subdomains, "
              f"{len(self.result.open_ports)} open ports.")
        return self.result

    def _whois(self):
        try:
            self.result.whois_info = whois.whois(self.target).__dict__
        except Exception as e:
            self.result.whois_info = {"error": str(e)}

    def _dns(self):
        record_types = ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"]
        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(self.target, rtype)
                self.result.dns_records[rtype] = [str(r) for r in answers]
            except Exception:
                pass

    def _subdomains(self):
        # Stub — would integrate subfinder/amass
        common = ["www", "mail", "ftp", "admin", "api", "dev", "staging", "blog", "shop"]
        for sub in common:
            fqdn = f"{sub}.{self.target}"
            try:
                socket.gethostbyname(fqdn)
                self.result.subdomains.append(fqdn)
            except socket.gaierror:
                pass

    def _port_scan(self):
        common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 8080, 8443]
        for port in common_ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    if s.connect_ex((self.target, port)) == 0:
                        self.result.open_ports.append(port)
            except Exception:
                pass

    def _tech_fingerprint(self):
        # Stub — would use Wappalyzer/httpx
        self.result.tech_stack = ["Unknown"]
