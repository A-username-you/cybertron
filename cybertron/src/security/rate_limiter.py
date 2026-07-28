#!/usr/bin/env python3
"""
Cybertron Rate Limiter
======================
Prevents runaway agents by limiting tool calls per minute.

Uses a sliding window algorithm. Configurable via:
- max_calls_per_minute (default: 30)
- burst_allowance (default: 5)
"""
import time
from collections import deque
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    max_calls_per_minute: int = 30
    burst_allowance: int = 5
    cooldown_seconds: float = 1.0


class RateLimiter:
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._windows: Dict[str, deque] = {}  # session_id -> deque of timestamps
        self._last_call: Dict[str, float] = {}

    def _get_window(self, session_id: str) -> deque:
        if session_id not in self._windows:
            self._windows[session_id] = deque()
        return self._windows[session_id]

    def _prune_window(self, window: deque, now: float):
        """Remove entries older than 60 seconds."""
        cutoff = now - 60.0
        while window and window[0] < cutoff:
            window.popleft()

    def check(self, session_id: str) -> tuple[bool, str]:
        """
        Check if a call is allowed. Returns (allowed, reason).
        """
        now = time.time()
        window = self._get_window(session_id)
        self._prune_window(window, now)

        # Check cooldown
        last = self._last_call.get(session_id, 0)
        if now - last < self.config.cooldown_seconds:
            return False, f"Cooldown active: wait {self.config.cooldown_seconds - (now - last):.1f}s"

        # Check rate limit
        max_calls = self.config.max_calls_per_minute + self.config.burst_allowance
        if len(window) >= max_calls:
            oldest = window[0]
            wait = 60.0 - (now - oldest)
            return False, f"Rate limit exceeded ({self.config.max_calls_per_minute}/min). Retry in {wait:.1f}s"

        return True, ""

    def record(self, session_id: str):
        """Record a successful call."""
        now = time.time()
        window = self._get_window(session_id)
        window.append(now)
        self._last_call[session_id] = now

    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get current rate limit status for a session."""
        now = time.time()
        window = self._get_window(session_id)
        self._prune_window(window, now)
        used = len(window)
        limit = self.config.max_calls_per_minute + self.config.burst_allowance
        return {
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "window_seconds": 60,
            "cooldown_seconds": self.config.cooldown_seconds,
        }

    def reset(self, session_id: str):
        """Reset the rate limit window for a session."""
        self._windows.pop(session_id, None)
        self._last_call.pop(session_id, None)


# ─── Singleton ───────────────────────────────────────────────────────────────
_limiter_instance: Optional[RateLimiter] = None

def get_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    global _limiter_instance
    if _limiter_instance is None:
        _limiter_instance = RateLimiter(config)
    return _limiter_instance
