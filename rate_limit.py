from __future__ import annotations

import ipaddress
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request


def client_ip(request: Request, *, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        for candidate in reversed(forwarded_for.split(",")):
            value = candidate.strip()
            if not value:
                continue
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                continue

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@dataclass
class _AttemptState:
    failures: list[float] = field(default_factory=list)
    blocked_until: float = 0.0


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: int = 10 * 60,
        block_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._clock = clock
        self._states: dict[str, _AttemptState] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            self._cleanup(now)
            state = self._states.get(key)
            if not state or state.blocked_until <= now:
                return 0
            return max(1, math.ceil(state.blocked_until - now))

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            self._cleanup(now)
            state = self._states.setdefault(key, _AttemptState())
            cutoff = now - self.window_seconds
            state.failures = [attempt for attempt in state.failures if attempt >= cutoff]
            state.failures.append(now)
            if len(state.failures) >= self.max_failures:
                state.blocked_until = now + self.block_seconds

    def reset(self, key: str) -> None:
        with self._lock:
            self._states.pop(key, None)

    def _cleanup(self, now: float) -> None:
        cutoff = now - self.window_seconds
        expired = [
            key
            for key, state in self._states.items()
            if state.blocked_until <= now
            and not any(attempt >= cutoff for attempt in state.failures)
        ]
        for key in expired:
            self._states.pop(key, None)
