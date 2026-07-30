"""Tests for Cybertron CLI."""
import pytest
from cybertron.cli import load_config, save_config


def test_load_config_default():
    cfg = load_config()
    assert "api_key" in cfg
    assert cfg.get("theme") == "hermes"


def test_save_config():
    cfg = load_config()
    cfg["test_key"] = "test_value"
    save_config(cfg)
    cfg2 = load_config()
    assert cfg2["test_key"] == "test_value"
