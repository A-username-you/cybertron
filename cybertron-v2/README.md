# Cybertron v2.0

> Advanced Security Automation & Reverse Engineering Framework

## Features

- **Reverse Engineering**: PE/ELF/Mach-O analysis, disassembler bridge, firmware extraction
- **Cloud Security**: AWS misconfiguration scanner, Docker security audit
- **Web/API Security**: Subdomain enum, port scan, OpenAPI fuzzing
- **Mobile Security**: Android APK static analysis
- **Network Forensics**: PCAP analysis for cleartext credentials
- **Enterprise**: Tamper-evident audit logs, output sanitization, granular scope

## Installation

```bash
pip install -e .
cybertron --help
```

## Quick Start

```bash
cybertron scan example.com --plugin port_scan
cybertron engage "BB-1" example.com configs/scope.yml
cybertron tui
uvicorn cybertron.ui.web:app --reload
```

## Writing a Plugin

```python
from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

class MyPlugin(PluginInterface):
    name = "my_plugin"
    version = "1.0.0"

    async def execute(self, target: str, options: dict) -> TaskResult:
        return TaskResult(
            task_id="...",
            status=TaskStatus.SUCCESS,
            findings=[Finding(...)]
        )
```

## License

MIT
