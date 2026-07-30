import pytest
from cybertron.core.config import load_config, list_personas

def test_default_config():
    cfg = load_config()
    assert "theme" in cfg
    assert cfg.get("theme") == "dark"

def test_personas_exist():
    personas = list_personas()
    assert len(personas) >= 5
    ids = [p["id"] for p in personas]
    assert "default" in ids
    assert "bug_bounty" in ids
