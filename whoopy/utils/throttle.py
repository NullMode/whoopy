"""Request throttling for rate limit prevention.

Copyright (c) 2024 Felix Geilert
"""

import asyncio
import time
from typing import Any


class RequestThrottler:
    """Throttle requests to prevent rate limiting."""

    def __init__(self, delay: float = 0.0, max_concurrent: int = 10):
        """
        Initialize the throttler.

        Args:
            delay: Minimum delay in seconds between requests
            max_concurrent: Maximum number of concurrent requests
        """
        self.delay = delay
        self.max_concurrent = max_concurrent
        self._last_request_time = 0.0
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire permission to make a request."""
        async with self._semaphore:
            if self.delay > 0:
                async with self._lock:
                    # Calculate time to wait
                    current_time = time.time()
                    time_since_last = current_time - self._last_request_time
                    wait_time = max(0, self.delay - time_since_last)

                    if wait_time > 0:
                        await asyncio.sleep(wait_time)

                    self._last_request_time = time.time()

    def __enter__(self) -> "RequestThrottler":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""

    async def __aenter__(self) -> "RequestThrottler":
        """Async context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""

    def adjust_delay(self, factor: float = 2.0) -> None:
        """
        Adjust the delay between requests.

        Args:
            factor: Multiplication factor for delay adjustment
        """
        self.delay = min(self.delay * factor, 5.0)  # Cap at 5 seconds
