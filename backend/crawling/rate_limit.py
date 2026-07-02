from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable

from backend.crawling.records import RateLimitState


@dataclass(slots=True)
class CooldownDecision:

    seconds: float
    reason: str
    consecutive_blocks: int


class AdaptiveRateLimiter:

    def __init__(
        self,
        *,
        delay_min: float,
        delay_max: float,
        cooldown_base: float = 8.0,
        cooldown_max: float = 45.0,
    ) -> None:
        self.delay_min = max(0.0, float(delay_min))
        self.delay_max = max(self.delay_min, float(delay_max))
        self.cooldown_base = max(1.0, float(cooldown_base))
        self.cooldown_max = max(self.cooldown_base, float(cooldown_max))
        self._lock = threading.Lock()
        self._cooldown_until = 0.0
        self._next_request_at = 0.0
        self._consecutive_blocks = 0

    def configure(
        self,
        *,
        delay_min: float | None = None,
        delay_max: float | None = None,
        cooldown_base: float | None = None,
        cooldown_max: float | None = None,
    ) -> None:
        with self._lock:
            if delay_min is not None:
                self.delay_min = max(0.0, float(delay_min))
            if delay_max is not None:
                self.delay_max = max(self.delay_min, float(delay_max))
            if cooldown_base is not None:
                self.cooldown_base = max(1.0, float(cooldown_base))
            if cooldown_max is not None:
                self.cooldown_max = max(self.cooldown_base, float(cooldown_max))

    def wait_before_request(self, should_stop: Callable[[], bool] | None = None) -> None:
        stop = should_stop or _not_stopped
        wait_seconds = self._reserve_request_slot(stop)
        end_at = time.monotonic() + wait_seconds
        while True:
            if stop():
                raise RuntimeError("任务已停止。")
            remaining = end_at - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.25))

    def record_success(self) -> None:
        with self._lock:
            if self._consecutive_blocks > 0:
                self._consecutive_blocks -= 1

    def record_block(self, reason: str) -> CooldownDecision:
        with self._lock:
            self._consecutive_blocks += 1
            exponent = min(self._consecutive_blocks - 1, 4)
            start = min(self.cooldown_base * (1.65**exponent), self.cooldown_max)
            spread = min(7.0, max(3.0, start * 0.45))
            seconds = min(self.cooldown_max, random.uniform(start, start + spread))
            until = time.monotonic() + seconds
            self._cooldown_until = max(self._cooldown_until, until)
            self._next_request_at = max(self._next_request_at, self._cooldown_until)
            return CooldownDecision(seconds, reason, self._consecutive_blocks)

    def state(self) -> RateLimitState:
        with self._lock:
            return RateLimitState(
                cooldown_until=self._cooldown_until,
                consecutive_blocks=self._consecutive_blocks,
                next_request_at=self._next_request_at,
                delay_min=self.delay_min,
                delay_max=self.delay_max,
                cooldown_base=self.cooldown_base,
                cooldown_max=self.cooldown_max,
            )

    def snapshot(self) -> dict[str, float | int]:
        return self.state().to_payload()

    def _reserve_request_slot(self, stop: Callable[[], bool]) -> float:
        while True:
            if stop():
                raise RuntimeError("任务已停止。")
            with self._lock:
                now = time.monotonic()
                if now < self._cooldown_until:
                    wait_seconds = self._cooldown_until - now
                else:
                    request_at = max(now, self._next_request_at)
                    wait_seconds = request_at - now
                    delay = random.uniform(self.delay_min, self.delay_max) if self.delay_max > 0 else 0.0
                    self._next_request_at = request_at + delay
                    return wait_seconds
            time.sleep(min(wait_seconds, 0.25))


def _not_stopped() -> bool:
    return False
