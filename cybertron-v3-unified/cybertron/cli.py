#!/usr/bin/env python3
"""
Cybertron CLI — One command to rule them all.
Usage:
  cybertron              → Launch TUI (default)
  cybertron tui          → Launch Terminal UI
  cybertron desktop      → Launch Desktop GUI
  cybertron web          → Launch Web UI server
  cybertron server       → Launch API server only
  cybertron config       → Manage configuration
  cybertron recon        → Run reconnaissance
  cybertron scan         → Run vulnerability scan
  cybertron brute        → Run brute force
  cybertron exploit      → Run exploitation
  cybertron forensics    → Run digital forensics
  cybertron reverse      → Reverse engineer a binary
  cybertron hunt         → Threat hunt
  cybertron report       → Generate report
"""
import sys
import os
import argparse
import json
from pathlib import Path

CYBERTRON_HOME = Path.home() / ".cybertron"
CYBERTRON_HOME.mkdir(exist_ok=True)
CONFIG_PATH = CYBERTRON_HOME / "config.json"


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {
        "api_key": "",
        "nim_api_key": "",
        "passkey_enabled": True,
        "passkey_secret": "",
        "server_host": "0.0.0.0",
        "server_port": 8443,
        "web_port": 8080,
        "theme": "hermes",
        "log_level": "INFO",
        "default_scope": "",
        "hackerone_token": "",
        "slack_webhook": "",
        "redis_url": "redis://localhost:6379",
    }


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def cmd_tui(args):
    from cybertron.ui.tui import CybertronTUI
    app = CybertronTUI()
    app.run()


def cmd_desktop(args):
    from cybertron.ui.gui import CybertronDesktop
    app = CybertronDesktop()
    app.run()


def cmd_web(args):
    from cybertron.ui.web import start_web_server
    cfg = load_config()
    port = args.port or cfg.get("web_port", 8080)
    host = args.host or cfg.get("server_host", "0.0.0.0")
    print(f"[Cybertron] Starting Web UI on http://{host}:{port}")
    start_web_server(host=host, port=port, passkey_enabled=cfg.get("passkey_enabled", True))


def cmd_server(args):
    from cybertron.gateway import start_gateway
    cfg = load_config()
    port = args.port or cfg.get("server_port", 8443)
    host = args.host or cfg.get("server_host", "0.0.0.0")
    print(f"[Cybertron] Starting API server on {host}:{port}")
    start_gateway(host=host, port=port)


def cmd_config(args):
    cfg = load_config()
    if args.show:
        for k, v in cfg.items():
            print(f"  {k}: {v}")
        return
    if args.set:
        key, val = args.set.split("=", 1)
        cfg[key] = val
        save_config(cfg)
        print(f"[Cybertron] Set {key} = {val}")
    if args.generate_passkey:
        import secrets
        secret = secrets.token_urlsafe(32)
        cfg["passkey_secret"] = secret
        cfg["passkey_enabled"] = True
        save_config(cfg)
        print(f"[Cybertron] Passkey generated: {secret}")
        print("          Store this securely. It will not be shown again.")


def cmd_recon(args):
    from cybertron.red_team.recon import ReconEngine
    engine = ReconEngine(target=args.target, scope=args.scope)
    engine.run()


def cmd_scan(args):
    from cybertron.red_team.scanner import VulnScanner
    scanner = VulnScanner(target=args.target)
    scanner.run()


def cmd_brute(args):
    from cybertron.red_team.brute_force import BruteForceEngine
    engine = BruteForceEngine(
        target=args.target,
        mode=args.mode or "dirs",
        wordlist=args.wordlist
    )
    engine.run()


def cmd_exploit(args):
    from cybertron.red_team.exploitation import ExploitFramework
    fw = ExploitFramework(target=args.target, module=args.module)
    fw.run()


def cmd_forensics(args):
    from cybertron.blue_team.forensics import ForensicsEngine
    engine = ForensicsEngine(source=args.source)
    engine.run()


def cmd_reverse(args):
    from cybertron.reverse_engineering.analyzer import ReverseEngineer
    re = ReverseEngineer(target=args.target)
    re.run()


def cmd_hunt(args):
    from cybertron.blue_team.threat_hunt import ThreatHunter
    hunter = ThreatHunter(ioc=args.ioc, source=args.source)
    hunter.run()


def cmd_report(args):
    from cybertron.agents.report_generator import ReportGenerator
    gen = ReportGenerator(engagement_id=args.engagement)
    gen.run()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cybertron",
        description="Cybertron — Unified Red/Blue Team Security Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cybertron                          Launch TUI
  cybertron desktop                  Launch Desktop GUI
  cybertron web --port 9090          Launch Web UI on port 9090
  cybertron server --port 8443       Launch API server
  cybertron config --show            Show all config
  cybertron config --set api_key=xxx Set a config value
  cybertron config --generate-passkey
  cybertron recon example.com        Run reconnaissance
  cybertron scan example.com         Run vulnerability scan
  cybertron brute example.com --mode subdomains
  cybertron exploit example.com --module sqli
  cybertron forensics /path/to/disk.img
  cybertron reverse /path/to/binary
  cybertron hunt --ioc bad-hash
  cybertron report --engagement 001
        """
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("tui", help="Launch Terminal UI")
    sub.add_parser("desktop", help="Launch Desktop GUI")

    p_web = sub.add_parser("web", help="Launch Web UI server")
    p_web.add_argument("--host", default=None)
    p_web.add_argument("--port", type=int, default=None)

    p_srv = sub.add_parser("server", help="Launch API server only")
    p_srv.add_argument("--host", default=None)
    p_srv.add_argument("--port", type=int, default=None)

    p_cfg = sub.add_parser("config", help="Manage configuration")
    p_cfg.add_argument("--show", action="store_true", help="Show config")
    p_cfg.add_argument("--set", type=str, help="Set key=value")
    p_cfg.add_argument("--generate-passkey", action="store_true", help="Generate passkey")

    p_rec = sub.add_parser("recon", help="Run reconnaissance")
    p_rec.add_argument("target", help="Target domain/IP")
    p_rec.add_argument("--scope", default=None, help="Scope file")

    p_scn = sub.add_parser("scan", help="Run vulnerability scan")
    p_scn.add_argument("target", help="Target URL/IP")

    p_brt = sub.add_parser("brute", help="Run brute force")
    p_brt.add_argument("target", help="Target URL")
    p_brt.add_argument("--mode", choices=["dirs","subdomains","params","vhosts","api","idor"], default="dirs")
    p_brt.add_argument("--wordlist", default=None)

    p_exp = sub.add_parser("exploit", help="Run exploitation")
    p_exp.add_argument("target", help="Target URL")
    p_exp.add_argument("--module", default="auto", help="Exploit module")

    p_for = sub.add_parser("forensics", help="Run digital forensics")
    p_for.add_argument("source", help="Disk image or directory")

    p_rev = sub.add_parser("reverse", help="Reverse engineer binary")
    p_rev.add_argument("target", help="Binary file path")

    p_hnt = sub.add_parser("hunt", help="Threat hunt")
    p_hnt.add_argument("--ioc", required=True, help="IOC to hunt")
    p_hnt.add_argument("--source", default="/var/log", help="Source directory")

    p_rep = sub.add_parser("report", help="Generate report")
    p_rep.add_argument("--engagement", required=True, help="Engagement ID")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        cmd_tui(args)
        return

    commands = {
        "tui": cmd_tui, "desktop": cmd_desktop, "web": cmd_web,
        "server": cmd_server, "config": cmd_config, "recon": cmd_recon,
        "scan": cmd_scan, "brute": cmd_brute, "exploit": cmd_exploit,
        "forensics": cmd_forensics, "reverse": cmd_reverse,
        "hunt": cmd_hunt, "report": cmd_report,
    }
    fn = commands.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
