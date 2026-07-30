"""Tests for authentication."""
import pytest
from cybertron.security.auth import AuthManager


def test_generate_api_key():
    auth = AuthManager()
    key = auth.generate_api_key("test")
    assert key.startswith("ct_")
    assert auth.verify_api_key(key)


def test_verify_passkey():
    auth = AuthManager()
    auth.config.passkey_secret = "test-secret"
    auth.config.passkey_enabled = True
    assert auth.verify_passkey("test-secret")
    assert not auth.verify_passkey("wrong")
