"""Cybertron Configuration Management"""
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///cybertron.db"
    echo: bool = False
    pool_size: int = 10


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None


class SecurityConfig(BaseModel):
    max_requests_per_minute: int = 100
    audit_log_path: Path = Path("logs/audit.log")
    sanitize_output: bool = True
    require_scope_validation: bool = True
    enable_rate_limiting: bool = True


class ReverseEngineeringConfig(BaseModel):
    ghidra_path: Optional[Path] = None
    radare2_path: str = "r2"
    gdb_path: str = "gdb"
    qemu_path: Optional[Path] = None
    default_arch: str = "x64"
    max_binary_size_mb: int = 500
    sandbox_enabled: bool = True


class CloudConfig(BaseModel):
    aws_access_key: Optional[str] = None
    aws_secret_key: Optional[str] = None
    gcp_project_id: Optional[str] = None
    azure_subscription_id: Optional[str] = None
    scan_containers: bool = True
    scan_kubernetes: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )

    app_name: str = "Cybertron"
    debug: bool = False
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    reports_dir: Path = Path("./reports")
    wordlists_dir: Path = Path("./wordlists")

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    re_engine: ReverseEngineeringConfig = Field(default_factory=ReverseEngineeringConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)

    @validator("data_dir", "reports_dir", "wordlists_dir", pre=True)
    def create_dirs(cls, v):
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
