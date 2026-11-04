"""Injectable time sources so resilience code is testable without real sleeping."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]

monotonic: Clock = time.monotonic
wall: Clock = time.time  # for windows aligned to calendar days (UTC)
sleep: Sleeper = asyncio.sleep
