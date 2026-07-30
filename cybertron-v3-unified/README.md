# Cybertron v3.0 — Unified Red/Blue Team Security Platform

> "One command to rule them all."

Cybertron is a comprehensive security automation platform covering every aspect of red team, blue team, and reverse engineering operations.

## Quick Start

```bash
# Install
pip install -e .

# Launch TUI (default)
cybertron

# Launch Desktop UI
cybertron desktop

# Launch Web UI server
cybertron web

# Launch API server only
cybertron server

# Configuration
cybertron config --show
cybertron config --set key=value

# Operations
cybertron recon <target>
cybertron scan <target>
cybertron brute <target>
cybertron exploit <target>
cybertron forensics <file>
cybertron reverse <file>
cybertron hunt --ioc <indicator>
cybertron report --engagement <id>
```

## Architecture

```
cybertron/
├── core/           # Engine, config, protocol
├── red_team/       # Offensive security modules
├── blue_team/      # Defensive security modules
├── reverse_engineering/  # RE & malware analysis
├── ui/             # TUI, Desktop GUI, Web UI
├── security/       # Auth, rate limiting, audit
├── agents/         # AI orchestration
└── integrations/   # HackerOne, Slack, etc.
```

## Features

### Red Team
- Reconnaissance (passive & active)
- Vulnerability scanning
- Brute force (dirs, subdomains, params, APIs, IDOR)
- Exploitation framework
- Post-exploitation & lateral movement
- Social engineering toolkit
- Wireless attacks
- Web application attacks
- API security testing
- Network attacks
- Privilege escalation

### Blue Team
- Threat hunting & IOC scanning
- Incident response & timeline analysis
- Digital forensics & file carving
- Malware analysis (static & dynamic)
- Log analysis & anomaly detection
- SIEM integration
- Network monitoring
- Honeypot deployment
- Deception technology

### Reverse Engineering
- Binary analysis (PE, ELF, Mach-O)
- Disassembly & decompilation
- String & import extraction
- Entropy analysis
- YARA rule generation
- APK/IPA analysis
- Firmware extraction
- Memory dump analysis
- JavaScript deobfuscation
- PowerShell deobfuscation
- Shellcode analysis

## Authentication

- **API Keys**: For programmatic access
- **Passkeys**: For Web UI access (WebAuthn-ready)
- **Tokens**: JWT-based session management

## Docker

```bash
docker-compose up --build
```

## License

MIT
