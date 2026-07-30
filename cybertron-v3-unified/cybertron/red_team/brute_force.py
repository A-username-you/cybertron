"""Red Team — Brute Force Engine."""
import asyncio
import httpx
from typing import List, Optional
from pathlib import Path


class BruteForceEngine:
    """Multi-mode brute force: dirs, subdomains, params, vhosts, API, IDOR."""

    MODES = ["dirs", "subdomains", "params", "vhosts", "api", "idor"]

    def __init__(self, target: str, mode: str = "dirs", wordlist: Optional[str] = None):
        self.target = target
        self.mode = mode
        self.wordlist = wordlist or self._default_wordlist()
        self.results: List[str] = []

    def _default_wordlist(self) -> str:
        default = Path.home() / ".cybertron" / "wordlists" / "common.txt"
        if default.exists():
            return str(default)
        return "/usr/share/wordlists/dirb/common.txt"

    def run(self):
        print(f"[Brute] Starting {self.mode} brute force against {self.target}")
        try:
            with open(self.wordlist) as f:
                words = [w.strip() for w in f if w.strip()]
        except FileNotFoundError:
            words = ["admin", "test", "api", "v1", "dev", "backup", "config", "login", "wp-admin"]

        if self.mode == "dirs":
            self._brute_dirs(words)
        elif self.mode == "subdomains":
            self._brute_subdomains(words)
        elif self.mode == "params":
            self._brute_params(words)
        elif self.mode == "vhosts":
            self._brute_vhosts(words)
        elif self.mode == "api":
            self._brute_api(words)
        elif self.mode == "idor":
            self._brute_idor(words)

        print(f"[Brute] Found {len(self.results)} hits.")
        return self.results

    def _brute_dirs(self, words: List[str]):
        import requests
        for word in words[:100]:
            url = f"{self.target}/{word}"
            try:
                r = requests.get(url, timeout=5, allow_redirects=False)
                if r.status_code in [200, 301, 302, 401, 403]:
                    self.results.append(f"[{r.status_code}] {url}")
            except Exception:
                pass

    def _brute_subdomains(self, words: List[str]):
        import socket
        domain = self.target.replace("https://", "").replace("http://", "").split("/")[0]
        for word in words[:100]:
            sub = f"{word}.{domain}"
            try:
                socket.gethostbyname(sub)
                self.results.append(sub)
            except socket.gaierror:
                pass

    def _brute_params(self, words: List[str]):
        import requests
        for word in words[:50]:
            url = f"{self.target}?{word}=1"
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200 and len(r.text) > 100:
                    self.results.append(f"[param] {word}")
            except Exception:
                pass

    def _brute_vhosts(self, words: List[str]):
        import requests
        ip = self.target.replace("https://", "").replace("http://", "").split("/")[0]
        for word in words[:50]:
            try:
                r = requests.get(f"http://{ip}", headers={"Host": f"{word}.local"}, timeout=5)
                if r.status_code == 200:
                    self.results.append(f"[vhost] {word}.local")
            except Exception:
                pass

    def _brute_api(self, words: List[str]):
        import requests
        for word in words[:50]:
            for method in ["GET", "POST", "PUT", "DELETE"]:
                url = f"{self.target}/api/{word}"
                try:
                    r = requests.request(method, url, timeout=3)
                    if r.status_code != 404:
                        self.results.append(f"[{method}] {url} -> {r.status_code}")
                except Exception:
                    pass

    def _brute_idor(self, words: List[str]):
        import requests
        for i in range(1, 100):
            url = f"{self.target}/user/{i}"
            try:
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    self.results.append(f"[IDOR] {url}")
            except Exception:
                pass
