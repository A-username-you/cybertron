"""GitHub Tool Loader — dynamically load security tools from GitHub."""
import os
import json
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

CYBERTRON_HOME = Path.home() / ".cybertron"
TOOLS_DIR = CYBERTRON_HOME / "tools"
TOOLS_DIR.mkdir(parents=True, exist_ok=True)
MARKETPLACE_PATH = Path(__file__).parent / "marketplace.json"


@dataclass
class ToolSpec:
    name: str
    repo: str
    branch: str = "main"
    install_cmd: str = ""
    run_cmd: str = ""
    category: str = ""


class GitHubToolLoader:
    """Load and manage security tools from GitHub repositories."""

    def __init__(self):
        self.tools: Dict[str, ToolSpec] = {}
        self._load_marketplace()

    def _load_marketplace(self):
        if MARKETPLACE_PATH.exists():
            with open(MARKETPLACE_PATH) as f:
                data = json.load(f)
            for name, spec in data.get("tools", {}).items():
                self.tools[name] = ToolSpec(name=name, **spec)

    def list_available(self) -> List[str]:
        return list(self.tools.keys())

    def install(self, name: str) -> bool:
        spec = self.tools.get(name)
        if not spec:
            return False
        target = TOOLS_DIR / name
        if target.exists():
            return True
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "-b", spec.branch,
                 f"https://github.com/{spec.repo}.git", str(target)],
                check=True, capture_output=True
            )
            if spec.install_cmd:
                subprocess.run(spec.install_cmd, shell=True, cwd=str(target), check=True)
            return True
        except subprocess.CalledProcessError:
            return False

    def run(self, name: str, args: List[str] = None) -> tuple:
        spec = self.tools.get(name)
        if not spec:
            return (1, "", f"Tool {name} not found")
        target = TOOLS_DIR / name
        if not target.exists() and not self.install(name):
            return (1, "", f"Failed to install {name}")
        cmd = spec.run_cmd or "python3"
        full = cmd.split() + (args or [])
        result = subprocess.run(full, cwd=str(target), capture_output=True, text=True)
        return (result.returncode, result.stdout, result.stderr)

    def uninstall(self, name: str) -> bool:
        target = TOOLS_DIR / name
        if target.exists():
            import shutil
            shutil.rmtree(target)
            return True
        return False
