"""Cybertron Authentication & Passkey System."""
import os
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict
import jwt
from cybertron.core.config import CybertronConfig


class AuthManager:
    """Manages API keys, JWT tokens, and passkey authentication."""

    def __init__(self, config: Optional[CybertronConfig] = None):
        self.config = config or CybertronConfig.load()
        self._key_cache: Dict[str, dict] = {}

    def generate_api_key(self, label: str = "default") -> str:
        raw = secrets.token_urlsafe(32)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        self._key_cache[hashed] = {
            "label": label,
            "created": datetime.utcnow().isoformat(),
            "last_used": None
        }
        return f"ct_{raw}"

    def verify_api_key(self, key: str) -> bool:
        if not key.startswith("ct_"):
            return False
        raw = key[3:]
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        if hashed in self._key_cache:
            self._key_cache[hashed]["last_used"] = datetime.utcnow().isoformat()
            return True
        return key == self.config.api_key

    def create_token(self, payload: dict, expiry_hours: int = None) -> str:
        exp = expiry_hours or self.config.jwt_expiry_hours
        payload["exp"] = datetime.utcnow() + timedelta(hours=exp)
        payload["iat"] = datetime.utcnow()
        return jwt.encode(payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm)

    def verify_token(self, token: str) -> Optional[dict]:
        try:
            return jwt.decode(token, self.config.jwt_secret, algorithms=[self.config.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def verify_passkey(self, secret: str) -> bool:
        if not self.config.passkey_enabled:
            return True
        if not self.config.passkey_secret:
            return False
        return hmac.compare_digest(secret, self.config.passkey_secret)

    def generate_passkey(self) -> str:
        secret = secrets.token_urlsafe(32)
        self.config.passkey_secret = secret
        self.config.passkey_enabled = True
        self.config.save()
        return secret
