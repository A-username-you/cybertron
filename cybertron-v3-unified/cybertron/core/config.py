"""Cybertron core configuration."""
import os
import json
from pathlib import Path
from pydantic_settings import BaseSettings

CYBERTRON_HOME = Path.home() / ".cybertron"
CYBERTRON_HOME.mkdir(exist_ok=True)
CONFIG_PATH = CYBERTRON_HOME / "config.json"


class CybertronConfig(BaseSettings):
    """Central configuration for all Cybertron modules."""
    app_name: str = "Cybertron"
    version: str = "3.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8443
    web_port: int = 8080

    # Auth
    api_key: str = ""
    nim_api_key: str = ""
    passkey_enabled: bool = True
    passkey_secret: str = ""
    jwt_secret: str = "cybertron-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # Integrations
    hackerone_token: str = ""
    slack_webhook: str = ""
    discord_webhook: str = ""
    jira_url: str = ""
    jira_token: str = ""

    # Infrastructure
    redis_url: str = "redis://localhost:6379"
    database_url: str = f"sqlite:///{CYBERTRON_HOME}/cybertron.db"
    celery_broker: str = "redis://localhost:6379/0"
    celery_backend: str = "redis://localhost:6379/0"

    # Recon / Scan defaults
    default_wordlist: str = str(CYBERTRON_HOME / "wordlists" / "common.txt")
    default_scope: str = ""
    rate_limit_rps: int = 10
    max_concurrent_scans: int = 5
    request_timeout: int = 30

    # Theme
    theme: str = "hermes"  # hermes, dark, light

    class Config:
        env_prefix = "CT_"
        env_file = ".env"

    def save(self):
        data = self.model_dump()
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def load(cls):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            return cls(**data)
        return cls()
