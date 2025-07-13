"""Retry logic with exponential backoff for API requests.

Copyright (c) 2024 Felix Geilert
"""

import asyncio
import random
from dataclasses import dataclass
from typing import TypeVar, Callable, Optional, Union, Type, Tuple
from functools import wraps

from ..exceptions import RateLimitError, ServerError

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: Tuple[Type[Exception], ...] = (RateLimitError, ServerError)
    

def calculate_backoff_delay(
    attempt: int, 
    config: RetryConfig,
    retry_after: Optional[int] = None
) -> float:
    """Calculate the delay before the next retry attempt."""
    if retry_after is not None:
        # If server provides retry-after, use it (with small jitter)
        delay = float(retry_after)
        if config.jitter:
            delay += random.uniform(0, 1)
        return min(delay, config.max_delay)
    
    # Exponential backoff calculation
    delay = config.base_delay * (config.exponential_base ** attempt)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        delay *= random.uniform(0.8, 1.2)
    
    return min(delay, config.max_delay)


def retry_with_backoff(config: Optional[RetryConfig] = None):
    """Decorator for adding retry logic to async functions."""
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
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
                    
                    # Sleep before retry
                    await asyncio.sleep(delay)
            
            # This shouldn't be reached, but just in case
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


class RetryableSession:
    """A session wrapper that automatically retries failed requests."""
    
    def __init__(self, session, retry_config: Optional[RetryConfig] = None):
        self.session = session
        self.retry_config = retry_config or RetryConfig()
    
    async def request(self, method: str, url: str, **kwargs):
        """Make a request with automatic retry logic."""
        @retry_with_backoff(self.retry_config)
        async def _request():
            return await self.session.request(method, url, **kwargs)
        
        return await _request()
    
    async def get(self, url: str, **kwargs):
        """GET request with retry."""
        return await self.request('GET', url, **kwargs)
    
    async def post(self, url: str, **kwargs):
        """POST request with retry."""
        return await self.request('POST', url, **kwargs)
    
    async def put(self, url: str, **kwargs):
        """PUT request with retry."""
        return await self.request('PUT', url, **kwargs)
    
    async def delete(self, url: str, **kwargs):
        """DELETE request with retry."""
        return await self.request('DELETE', url, **kwargs)