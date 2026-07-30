#!/usr/bin/env python3
"""Cybertron Control Center — Settings, personas, themes, API keys."""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_DIR = Path.home() / ".cybertron"
CONFIG_FILE = CONFIG_DIR / "config.json"
PERSONAS_DIR = CONFIG_DIR / "personas"

DEFAULT_CONFIG = {
    "nim_api_key": "",
    "nim_model": "nvidia/nemotron-4-340b-instruct",
    "theme": "dark",
    "auto_approve_recon": False,
    "auto_approve_scan": False,
    "dry_run": False,
    "rate_limit_per_min": 30,
    "max_iterations": 12,
    "webhook_url": "",
    "slack_webhook": "",
    "github_token": "",
    "system_prompt": "",
    "output_sanitize": True,
    "sandbox_mode": False,
    "remember_sessions": True,
    "current_persona": "default",
}

PERSONAS = {
    "default": {
        "name": "Default",
        "prompt": "You are Cybertron, a red/blue team security agent. You plan carefully, use tools methodically, and report findings clearly.",
    },
    "stealthy": {
        "name": "Stealthy Red Teamer",
        "prompt": "You are a stealthy red team operator. Minimize noise, avoid detection, and prioritize low-and-slow techniques.",
    },
    "compliance": {
        "name": "Compliance Auditor",
        "prompt": "You are a compliance auditor focused on PCI-DSS, SOC 2, and ISO 27001. Map findings to controls and provide remediation guidance.",
    },
    "threat_hunter": {
        "name": "Threat Hunter",
        "prompt": "You are a threat hunter. Look for IOCs, lateral movement, persistence mechanisms, and anomalous behavior.",
    },
    "bug_bounty": {
        "name": "Bug Bounty Hunter",
        "prompt": "You are a bug bounty hunter. Focus on high-impact, reproducible vulnerabilities. Provide clear proof-of-concept steps.",
    },
}

def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)

def load_config() -> dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(saved)
        return merged
    return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    ensure_dirs()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_persona(name: str) -> Optional[dict]:
    if name in PERSONAS:
        return PERSONAS[name]
    persona_file = PERSONAS_DIR / f"{name}.json"
    if persona_file.exists():
        with open(persona_file) as f:
            return json.load(f)
    return None

def list_personas() -> List[dict]:
    result = []
    for key, val in PERSONAS.items():
        result.append({"id": key, **val})
    for f in PERSONAS_DIR.glob("*.json"):
        with open(f) as fh:
            data = json.load(fh)
        result.append({"id": f.stem, **data})
    return result

def save_persona(name: str, persona: dict):
    ensure_dirs()
    path = PERSONAS_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(persona, f, indent=2)

def get_nim_key() -> str:
    cfg = load_config()
    return cfg.get("nim_api_key") or os.environ.get("NIM_API_KEY", "")

def get_system_prompt() -> str:
    cfg = load_config()
    persona_name = cfg.get("current_persona", "default")
    persona = get_persona(persona_name)
    if persona:
        return persona.get("prompt", "")
    return cfg.get("system_prompt", "")
