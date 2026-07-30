"""Rate Limiter."""
import time
from typing import Dict
from collections import defaultdict


class RateLimiter:
    """Token bucket rate limiter per client."""

    def __init__(self, rps: int = 10, burst: int = 20):
        self.rps = rps
        self.burst = burst
        self.buckets: Dict[str, dict] = defaultdict(lambda: {"tokens": burst, "last": time.time()})

    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = self.buckets[key]
        elapsed = now - bucket["last"]
        bucket["tokens"] = min(self.burst, bucket["tokens"] + elapsed * self.rps)
        bucket["last"] = now
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        return False

    def status(self, key: str) -> dict:
        return {
            "remaining": int(self.buckets[key]["tokens"]),
            "limit": self.burst,
            "reset": int(self.buckets[key]["last"] + (self.burst - self.buckets[key]["tokens"]) / self.rps)
        }
