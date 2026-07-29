"""Unit tests for Cybertron Core Engine"""
import pytest
import asyncio
from pathlib import Path
from cybertron.core import ExecutionEngine, PluginInterface, TaskResult, TaskStatus, Finding, Severity


class DummyPlugin(PluginInterface):
    name = "dummy"
    version = "1.0"

    async def execute(self, target, options):
        return TaskResult(
            task_id="test-1",
            status=TaskStatus.SUCCESS,
            findings=[Finding(
                title="Test finding",
                description="A test",
                severity=Severity.HIGH,
                category="test",
                target=target
            )]
        )


class FailingPlugin(PluginInterface):
    name = "failing"
    version = "1.0"

    async def execute(self, target, options):
        raise RuntimeError("Intentional failure")


@pytest.fixture
def engine(tmp_path):
    eng = ExecutionEngine(max_workers=2)
    eng.registry.register(DummyPlugin)
    eng.registry.register(FailingPlugin)
    scope_file = tmp_path / "scope.yml"
    scope_file.write_text("domains:
  - test.com
cidrs:
  - 192.168.1.0/24
")
    eng.scope.load_scope(scope_file)
    return eng


@pytest.mark.asyncio
async def test_scope_validation_blocks_out_of_scope(engine):
    result = await engine.execute_task("dummy", "evil.com")
    assert result.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_scope_validation_allows_in_scope(engine):
    result = await engine.execute_task("dummy", "test.com")
    assert result.status == TaskStatus.SUCCESS
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_plugin_execution(engine):
    result = await engine.execute_task("dummy", "test.com")
    assert result.status == TaskStatus.SUCCESS
    assert result.findings[0].severity == Severity.HIGH


@pytest.mark.asyncio
async def test_retry_on_failure(engine):
    result = await engine.execute_task("failing", "test.com")
    assert result.status == TaskStatus.FAILED
    assert "Intentional failure" in result.error


@pytest.mark.asyncio
async def test_pipeline_execution(engine):
    pipeline = [{"plugin": "dummy"}, {"plugin": "dummy", "condition": "has_findings"}]
    results = await engine.execute_pipeline(pipeline, "test.com")
    assert len(results) == 2
    assert all(r.status == TaskStatus.SUCCESS for r in results)


@pytest.mark.asyncio
async def test_concurrent_execution(engine):
    tasks = [engine.execute_task("dummy", "test.com") for _ in range(5)]
    results = await asyncio.gather(*tasks)
    assert all(r.status == TaskStatus.SUCCESS for r in results)
