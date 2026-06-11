"""Latency helpers for eval runners."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass
class TimerResult:
    elapsed_ms: float = 0.0


@contextmanager
def measure_latency() -> Iterator[TimerResult]:
    result = TimerResult()
    start = time.perf_counter()
    try:
        yield result
    finally:
        result.elapsed_ms = (time.perf_counter() - start) * 1000

