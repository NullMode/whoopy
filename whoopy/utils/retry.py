"""Retry logic with exponential backoff for API requests.

Copyright (c) 2024 Felix Geilert
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar, cast

from whoopy.exceptions import RateLimitError, ServerError

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 5  # Increased for better rate limit handling
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: tuple[type[Exception], ...] = (RateLimitError, ServerError)


def calculate_backoff_delay(attempt: int, config: RetryConfig, retry_after: int | None = None) -> float:
    """
    Calculate the delay before the next retry attempt.

    Args:
        attempt: The attempt number (0-based)
        config: Retry configuration parameters
        retry_after: Server-provided retry delay in seconds (overrides backoff)

    Returns:
        Delay in seconds before next retry
    """
    if retry_after is not None:
        # If server provides retry-after, use it (with small jitter)
        delay = float(retry_after)
        if config.jitter:
            delay += random.uniform(0, 1)
        return min(delay, config.max_delay)

    # Exponential backoff calculation
    delay = config.base_delay * (config.exponential_base**attempt)

    # Add jitter to prevent thundering herd
    if config.jitter:
        delay *= random.uniform(0.8, 1.2)

    return min(delay, config.max_delay)


def retry_with_backoff(
    config: RetryConfig | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator for adding retry logic to async functions.

    Args:
        config: Retry configuration (uses defaults if None)

    Returns:
        Decorator function that adds retry logic
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retry_on as e:
                    last_exception = e

                    # Check if this is the last attempt
                    if attempt == config.max_attempts - 1:
                        raise

                    # Calculate delay
                    retry_after = None
                    if isinstance(e, RateLimitError):
                        retry_after = e.retry_after

                    delay = calculate_backoff_delay(attempt, config, retry_after)

                    # Log retry attempt
                    logger = logging.getLogger("whoopy")
                    logger.warning(
                        f"Retrying after {type(e).__name__}. "
                        f"Attempt {attempt + 2}/{config.max_attempts}. "
                        f"Waiting {delay:.1f}s"
                    )

                    # Sleep before retry
                    await asyncio.sleep(delay)

            # This shouldn't be reached, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry logic error")

        return cast(Callable[..., Awaitable[T]], wrapper)

    return decorator


class RetryableSession:
    """A session wrapper that automatically retries failed requests."""

    def __init__(
        self,
        session: Any,
        retry_config: RetryConfig | None = None,
        check_response_func: Callable[[Any], Awaitable[None]] | None = None,
    ) -> None:
        """
        Initialize RetryableSession.

        Args:
            session: The underlying session (e.g., aiohttp.ClientSession)
            retry_config: Configuration for retry behavior (uses defaults if None)
            check_response_func: Optional function to check response validity
        """
        self.session = session
        self.retry_config = retry_config or RetryConfig()
        self.check_response_func = check_response_func

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """
        Make a request with automatic retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Additional arguments passed to the underlying session request

        Returns:
            Response from the underlying session

        Raises:
            Various exceptions based on retry configuration
        """

        @retry_with_backoff(self.retry_config)
        async def _request() -> Any:
            response = await self.session.request(method, url, **kwargs)
            if self.check_response_func:
                await self.check_response_func(response)
            return response

        return await _request()

    async def get(self, url: str, **kwargs: Any) -> Any:
        """
        GET request with retry.

        Args:
            url: URL to request
            **kwargs: Additional arguments passed to the request

        Returns:
            Response from the underlying session
        """
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> Any:
        """
        POST request with retry.

        Args:
            url: URL to request
            **kwargs: Additional arguments passed to the request

        Returns:
            Response from the underlying session
        """
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> Any:
        """
        PUT request with retry.

        Args:
            url: URL to request
            **kwargs: Additional arguments passed to the request

        Returns:
            Response from the underlying session
        """
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Any:
        """
        DELETE request with retry.

        Args:
            url: URL to request
            **kwargs: Additional arguments passed to the request

        Returns:
            Response from the underlying session
        """
        return await self.request("DELETE", url, **kwargs)
