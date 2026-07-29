"""Cybertron Core Engine"""
import asyncio, importlib, inspect, pkgutil, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Set
from dataclasses import dataclass, field
from enum import Enum, auto
import structlog
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

class TaskStatus(Enum):
    PENDING = auto(); RUNNING = auto(); SUCCESS = auto(); FAILED = auto(); CANCELLED = auto()

class Severity(Enum):
    CRITICAL = "critical"; HIGH = "high"; MEDIUM = "medium"; LOW = "low"; INFO = "info"

class Finding(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str; description: str; severity: Severity; category: str; target: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    remediation: Optional[str] = None
    references: List[str] = Field(default_factory=list)
    cwe_id: Optional[str] = None; cvss_score: Optional[float] = None
    tags: Set[str] = Field(default_factory=set)
    class Config: frozen = True

@dataclass
class TaskResult:
    task_id: str; status: TaskStatus
    findings: List[Finding] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)

class PluginInterface:
    name: str = "base"; version: str = "1.0.0"
    description: str = "Base plugin"; author: str = "unknown"
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = structlog.get_logger(plugin=self.name)
    async def initialize(self) -> bool: return True
    async def execute(self, target: str, options: Dict[str, Any]) -> TaskResult:
        raise NotImplementedError
    async def shutdown(self) -> None: pass
    def health_check(self) -> Dict[str, Any]:
        return {"status": "ok", "plugin": self.name}

class ScopeManager:
    def __init__(self):
        self.allowed_domains: Set[str] = set()
        self.allowed_ips: Set[str] = set()
        self.allowed_cidrs: List[Any] = []
        self.excluded_targets: Set[str] = set()
    def load_scope(self, scope_file: Path) -> None:
        import yaml
        from ipaddress import ip_network
        data = yaml.safe_load(scope_file.read_text())
        self.allowed_domains = set(data.get("domains", []))
        self.allowed_ips = set(data.get("ips", []))
        self.excluded_targets = set(data.get("exclude", []))
        for cidr in data.get("cidrs", []):
            self.allowed_cidrs.append(ip_network(cidr, strict=False))
    def is_in_scope(self, target: str) -> bool:
        if target in self.excluded_targets: return False
        if target in self.allowed_domains or target in self.allowed_ips: return True
        from ipaddress import ip_address
        try:
            addr = ip_address(target)
            for network in self.allowed_cidrs:
                if addr in network: return True
        except ValueError: pass
        for domain in self.allowed_domains:
            if domain.startswith("*.") and target.endswith(domain[1:]): return True
        return False

class PluginRegistry:
    def __init__(self):
        self._plugins: Dict[str, Type[PluginInterface]] = {}
        self._instances: Dict[str, PluginInterface] = {}
        self._lock = asyncio.Lock()
    def register(self, plugin_class: Type[PluginInterface]) -> None:
        if not issubclass(plugin_class, PluginInterface):
            raise TypeError(f"{plugin_class} must inherit from PluginInterface")
        self._plugins[plugin_class.name] = plugin_class
        logger.info("plugin_registered", name=plugin_class.name, version=plugin_class.version)
    async def get_instance(self, name: str, config: Dict[str, Any]) -> PluginInterface:
        async with self._lock:
            if name not in self._instances:
                if name not in self._plugins: raise KeyError(f"Plugin '{name}' not found")
                instance = self._plugins[name](config)
                await instance.initialize()
                self._instances[name] = instance
            return self._instances[name]
    def discover(self, package_path: str = "cybertron.plugins") -> None:
        try:
            package = importlib.import_module(package_path)
            for _, modname, ispkg in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
                try:
                    module = importlib.import_module(modname)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, PluginInterface) and obj is not PluginInterface:
                            self.register(obj)
                except Exception as e:
                    logger.warning("plugin_load_failed", module=modname, error=str(e))
        except ImportError:
            logger.warning("plugin_package_not_found", path=package_path)
    def list_plugins(self) -> List[Dict[str, str]]:
        return [{"name": p.name, "version": p.version, "description": p.description, "author": p.author}
                for p in self._plugins.values()]

class ExecutionEngine:
    def __init__(self, max_workers: int = 10):
        self.registry = PluginRegistry()
        self.scope = ScopeManager()
        self.max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._task_history: List[TaskResult] = []
        self.logger = structlog.get_logger(engine="cybertron")
    async def execute_task(self, plugin_name: str, target: str,
                           options: Optional[Dict[str, Any]] = None,
                           config: Optional[Dict[str, Any]] = None) -> TaskResult:
        options = options or {}; config = config or {}
        if not self.scope.is_in_scope(target):
            return TaskResult(task_id=uuid.uuid4().hex, status=TaskStatus.CANCELLED,
                              error=f"Target {target} is out of scope")
        async with self._semaphore:
            plugin = await self.registry.get_instance(plugin_name, config)
            start_time = asyncio.get_event_loop().time()
            try:
                @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
                async def _run() -> TaskResult: return await plugin.execute(target, options)
                result = await _run()
                result.execution_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                self._task_history.append(result)
                self.logger.info("task_completed", plugin=plugin_name, target=target,
                                 status=result.status.name, findings=len(result.findings))
                return result
            except Exception as e:
                self.logger.error("task_failed", plugin=plugin_name, target=target, error=str(e))
                return TaskResult(task_id=uuid.uuid4().hex, status=TaskStatus.FAILED,
                                  error=str(e),
                                  execution_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000)
    async def execute_pipeline(self, pipeline: List[Dict[str, Any]], target: str) -> List[TaskResult]:
        results = []
        for step in pipeline:
            plugin_name = step["plugin"]
            options = step.get("options", {})
            config = step.get("config", {})
            condition = step.get("condition")
            if condition and results:
                last = results[-1]
                if condition == "has_findings" and not last.findings: continue
                if condition == "no_findings" and last.findings: continue
            result = await self.execute_task(plugin_name, target, options, config)
            results.append(result)
            if step.get("stop_on_failure") and result.status == TaskStatus.FAILED: break
        return results
    def get_findings(self, severity: Optional[Severity] = None) -> List[Finding]:
        findings = []
        for task in self._task_history: findings.extend(task.findings)
        if severity: findings = [f for f in findings if f.severity == severity]
        return findings
    async def shutdown(self) -> None:
        for name, instance in self.registry._instances.items():
            try:
                await instance.shutdown()
                self.logger.info("plugin_shutdown", name=name)
            except Exception as e:
                self.logger.error("plugin_shutdown_failed", name=name, error=str(e))
