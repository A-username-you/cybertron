"""Tests for reconnaissance."""
import pytest
from cybertron.red_team.recon import ReconEngine


def test_recon_engine_init():
    engine = ReconEngine(target="example.com")
    assert engine.target == "example.com"
    assert len(engine.STAGES) == 10
