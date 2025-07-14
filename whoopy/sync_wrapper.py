"""Synchronous wrapper for the async Whoop API v2 client.

This module provides a synchronous interface to the async WhoopClientV2,
making it easy to use in non-async code while maintaining the benefits
of the modern implementation.

Copyright (c) 2024 Felix Geilert
"""

import asyncio
import functools
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from whoopy.handlers import handlers_v2
from uuid import UUID

import pandas as pd

from .client_v2 import WhoopClientV2
from .models import models_v2 as models
from .utils import RetryConfig, TokenInfo

T = TypeVar("T")


class EventLoopThread:
    """Thread with its own event loop for running async code."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread: threading.Thread | None = None
        self._started = threading.Event()

    def start(self) -> None:
        """Start the event loop thread."""
        if self.thread is not None:
            return

        def _run_loop() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self._started.set()
            self.loop.run_forever()

        self.thread = threading.Thread(target=_run_loop, daemon=True)
        self.thread.start()
        self._started.wait()  # Wait for loop to be ready

    def run_coroutine(self, coro: Any) -> Any:
        """Run a coroutine in the event loop."""
        if self.loop is None:
            self.start()

        if self.loop is None:
            raise RuntimeError("Event loop not initialized")
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def stop(self) -> None:
        """Stop the event loop and thread."""
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread is not None:
            self.thread.join(timeout=1)
            self.thread = None
            self.loop = None


def async_to_sync(method: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to convert async methods to sync.

    Args:
        method: The async method to wrap

    Returns:
        A synchronous wrapper function
    """

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Ensure we have an event loop thread
        if not hasattr(self, "_loop_thread") or self._loop_thread is None:
            raise RuntimeError("Event loop thread not initialized")

        coro = method(self, *args, **kwargs)
        return self._loop_thread.run_coroutine(coro)

    return wrapper


class SyncUserHandler:
    """Synchronous wrapper for UserHandler."""

    def __init__(self, async_handler: "handlers_v2.UserHandler", loop_thread: EventLoopThread) -> None:
        """
        Initialize SyncUserHandler.

        Args:
            async_handler: The async UserHandler to wrap
            loop_thread: Event loop thread for running async code
        """
        self._handler = async_handler
        self._loop_thread = loop_thread

    @async_to_sync
    async def get_profile(self) -> models.UserBasicProfile:
        """Get the authenticated user's basic profile."""
        return await self._handler.get_profile()

    @async_to_sync
    async def get_body_measurements(self) -> models.UserBodyMeasurement:
        """Get the authenticated user's body measurements."""
        return await self._handler.get_body_measurements()


class SyncCollectionMixin:
    """Mixin for synchronous collection operations."""

    _handler: Any  # Will be set by subclasses
    _loop_thread: EventLoopThread  # Will be set by subclasses

    @async_to_sync
    async def get_page(
        self,
        limit: int = 10,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        next_token: str | None = None,
    ) -> Any:
        """
        Get a single page of results.

        Args:
            limit: Maximum number of items per page (default: 10)
            start: Start datetime for filtering results
            end: End datetime for filtering results
            next_token: Token for pagination to get next page

        Returns:
            Paginated response containing items and next_token
        """
        return await self._handler.get_page(limit=limit, start=start, end=end, next_token=next_token)

    @async_to_sync
    async def get_all(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ) -> list[Any]:
        """
        Get all items across all pages.

        Args:
            start: Start datetime for filtering results
            end: End datetime for filtering results
            limit_per_page: Items per page (default: 25)
            max_records: Maximum total records to fetch (None for all)

        Returns:
            List of all items across all pages
        """
        return await self._handler.get_all(start=start, end=end, limit_per_page=limit_per_page, max_records=max_records)

    def iterate(
        self, start: str | datetime | None = None, end: str | datetime | None = None, limit_per_page: int = 25
    ) -> list[Any]:
        """
        Iterate over all items across all pages.

        Note: In sync mode, this returns all items as a list rather than yielding.

        Args:
            start: Start datetime for filtering results
            end: End datetime for filtering results
            limit_per_page: Items per page (default: 25)

        Returns:
            List of all items
        """

        async def _iterate() -> list[Any]:
            items = []
            async for item in self._handler.iterate(start=start, end=end, limit_per_page=limit_per_page):
                items.append(item)
            return items

        # Return all items as a list since we can't yield from sync
        return self._loop_thread.run_coroutine(_iterate())

    @async_to_sync
    async def get_dataframe(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ) -> pd.DataFrame:
        # type: ignore[misc]
        """
        Get all items as a pandas DataFrame.

        Args:
            start: Start datetime for filtering results
            end: End datetime for filtering results
            limit_per_page: Items per page (default: 25)
            max_records: Maximum total records to fetch (None for all)

        Returns:
            DataFrame containing all items with flattened structure
        """
        return await self._handler.get_dataframe(
            start=start, end=end, limit_per_page=limit_per_page, max_records=max_records
        )


class SyncCycleHandler(SyncCollectionMixin):
    """Synchronous wrapper for CycleHandler."""

    def __init__(self, async_handler: Any, loop_thread: EventLoopThread) -> None:
        """
        Initialize SyncCycleHandler.

        Args:
            async_handler: The async CycleHandler to wrap
            loop_thread: Event loop thread for running async code
        """
        self._handler = async_handler
        self._loop_thread = loop_thread

    @async_to_sync
    async def get_by_id(self, cycle_id: int) -> models.Cycle:
        """
        Get a cycle by ID.

        Args:
            cycle_id: The unique identifier of the cycle

        Returns:
            The requested Cycle object

        Raises:
            ResourceNotFoundError: If cycle not found
        """
        return await self._handler.get_by_id(cycle_id)

    @async_to_sync
    async def get_sleep(self, cycle_id: int) -> models.Sleep:
        """
        Get the sleep for a specific cycle.

        Args:
            cycle_id: The unique identifier of the cycle

        Returns:
            Sleep data associated with the cycle

        Raises:
            ResourceNotFoundError: If cycle or sleep not found
        """
        return await self._handler.get_sleep(cycle_id)


class SyncSleepHandler(SyncCollectionMixin):
    """Synchronous wrapper for SleepHandler."""

    def __init__(self, async_handler: Any, loop_thread: EventLoopThread) -> None:
        """
        Initialize SyncSleepHandler.

        Args:
            async_handler: The async SleepHandler to wrap
            loop_thread: Event loop thread for running async code
        """
        self._handler = async_handler
        self._loop_thread = loop_thread

    @async_to_sync
    async def get_by_id(self, sleep_id: str | UUID) -> models.Sleep:
        """
        Get a sleep activity by ID.

        Args:
            sleep_id: The UUID of the sleep activity (as string or UUID object)

        Returns:
            The requested Sleep object

        Raises:
            ResourceNotFoundError: If sleep not found
        """
        return await self._handler.get_by_id(sleep_id)


class SyncRecoveryHandler(SyncCollectionMixin):
    """Synchronous wrapper for RecoveryHandler."""

    def __init__(self, async_handler: Any, loop_thread: EventLoopThread) -> None:
        """
        Initialize SyncRecoveryHandler.

        Args:
            async_handler: The async RecoveryHandler to wrap
            loop_thread: Event loop thread for running async code
        """
        self._handler = async_handler
        self._loop_thread = loop_thread

    @async_to_sync
    async def get_for_cycle(self, cycle_id: int) -> models.Recovery:
        """
        Get the recovery for a specific cycle.

        Args:
            cycle_id: The unique identifier of the cycle

        Returns:
            Recovery data for the specified cycle

        Raises:
            ResourceNotFoundError: If recovery not found for cycle
        """
        return await self._handler.get_for_cycle(cycle_id)


class SyncWorkoutHandler(SyncCollectionMixin):
    """Synchronous wrapper for WorkoutHandler."""

    def __init__(self, async_handler: Any, loop_thread: EventLoopThread) -> None:
        """
        Initialize SyncWorkoutHandler.

        Args:
            async_handler: The async WorkoutHandler to wrap
            loop_thread: Event loop thread for running async code
        """
        self._handler = async_handler
        self._loop_thread = loop_thread

    @async_to_sync
    async def get_by_id(self, workout_id: str | UUID) -> models.WorkoutV2:
        """
        Get a workout by ID.

        Args:
            workout_id: The UUID of the workout (as string or UUID object)

        Returns:
            The requested WorkoutV2 object

        Raises:
            ResourceNotFoundError: If workout not found
        """
        return await self._handler.get_by_id(workout_id)

    @async_to_sync
    async def get_by_sport(
        self,
        sport_name: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ) -> list[models.WorkoutV2]:
        """
        Get all workouts for a specific sport.

        Args:
            sport_name: Name of the sport to filter by
            start: Start datetime for filtering results
            end: End datetime for filtering results
            limit_per_page: Items per page (default: 25)
            max_records: Maximum total records to fetch (None for all)

        Returns:
            List of workouts matching the sport name
        """
        return await self._handler.get_by_sport(
            sport_name=sport_name, start=start, end=end, limit_per_page=limit_per_page, max_records=max_records
        )


class WhoopClientV2Sync:
    """Synchronous wrapper for WhoopClientV2."""

    def __init__(
        self,
        token_info: TokenInfo | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str = "http://localhost:1234",
        retry_config: RetryConfig | None = None,
        auto_refresh_token: bool = True,
        logger: logging.Logger | None = None,
        request_delay: float = 0.0,
        max_concurrent_requests: int = 10,
    ):
        """
        Initialize the synchronous Whoop API v2 client.

        Args:
            token_info: OAuth2 token information
            client_id: OAuth2 client ID (required for token refresh)
            client_secret: OAuth2 client secret (required for token refresh)
            redirect_uri: OAuth2 redirect URI
            retry_config: Configuration for retry behavior
            auto_refresh_token: Automatically refresh expired tokens
            logger: Logger instance (creates default if None)
            request_delay: Delay in seconds between requests (default: 0)
            max_concurrent_requests: Maximum concurrent requests (default: 10)
        """
        self._async_client = WhoopClientV2(
            token_info=token_info,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            retry_config=retry_config,
            auto_refresh_token=auto_refresh_token,
            logger=logger,
            request_delay=request_delay,
            max_concurrent_requests=max_concurrent_requests,
        )

        # Initialize sync handlers
        self._user: SyncUserHandler | None = None
        self._cycles: SyncCycleHandler | None = None
        self._sleep: SyncSleepHandler | None = None
        self._recovery: SyncRecoveryHandler | None = None
        self._workouts: SyncWorkoutHandler | None = None

        # Event loop thread for running async code
        self._loop_thread: EventLoopThread | None = None

        # Initialize the client
        self._initialize()

    def _initialize(self) -> None:
        """Initialize the async client and create sync handlers."""
        # We'll initialize handlers lazily when first accessed
        self._initialized = False
        self._session_context: WhoopClientV2 | None = None

    def _ensure_initialized(self) -> None:
        """Ensure the async client is initialized with an active session."""
        if not self._initialized:
            # Check if we have authentication before initializing
            if self._async_client.token_info is None:
                from .exceptions import AuthenticationError

                raise AuthenticationError(
                    "No authentication token available. Please authenticate first using "
                    "WhoopClientV2Sync.auth_flow() or provide a valid token."
                )

            # Create event loop thread
            self._loop_thread = EventLoopThread()
            self._loop_thread.start()

            async def _init() -> None:
                # Enter the async context to create session
                self._session_context = await self._async_client.__aenter__()

                # Create sync wrappers for handlers
                assert self._loop_thread is not None  # Type guard
                self._user = SyncUserHandler(self._session_context.user, self._loop_thread)
                self._cycles = SyncCycleHandler(self._session_context.cycles, self._loop_thread)
                self._sleep = SyncSleepHandler(self._session_context.sleep, self._loop_thread)
                self._recovery = SyncRecoveryHandler(self._session_context.recovery, self._loop_thread)
                self._workouts = SyncWorkoutHandler(self._session_context.workouts, self._loop_thread)

                self._initialized = True

            self._loop_thread.run_coroutine(_init())

    @property
    def user(self) -> SyncUserHandler:
        """Get the user handler."""
        self._ensure_initialized()
        if self._user is None:
            raise RuntimeError("Client not initialized")
        return self._user

    @property
    def cycles(self) -> SyncCycleHandler:
        """Get the cycles handler."""
        self._ensure_initialized()
        if self._cycles is None:
            raise RuntimeError("Client not initialized")
        return self._cycles

    @property
    def sleep(self) -> SyncSleepHandler:
        """Get the sleep handler."""
        self._ensure_initialized()
        if self._sleep is None:
            raise RuntimeError("Client not initialized")
        return self._sleep

    @property
    def recovery(self) -> SyncRecoveryHandler:
        """Get the recovery handler."""
        self._ensure_initialized()
        if self._recovery is None:
            raise RuntimeError("Client not initialized")
        return self._recovery

    @property
    def workouts(self) -> SyncWorkoutHandler:
        """Get the workouts handler."""
        self._ensure_initialized()
        if self._workouts is None:
            raise RuntimeError("Client not initialized")
        return self._workouts

    @property
    def token_info(self) -> TokenInfo | None:
        """Get current token information."""
        return self._async_client.token_info

    def save_token(self, path: str = ".whoop_credentials.json") -> None:
        """
        Save current token to file.

        Args:
            path: Path to save the token file (default: ".whoop_credentials.json")

        Raises:
            ValueError: If no token to save
        """
        self._async_client.save_token(path)

    def __enter__(self) -> "WhoopClientV2Sync":
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and clean up resources."""
        self.close()

    def close(self) -> None:
        """Close the client and clean up resources."""
        if self._initialized and self._session_context:

            async def _cleanup() -> None:
                await self._async_client.__aexit__(None, None, None)

            if self._loop_thread:
                self._loop_thread.run_coroutine(_cleanup())
                self._loop_thread.stop()
                self._loop_thread = None

            self._initialized = False
            self._session_context = None

    @async_to_sync
    async def refresh_token(self) -> None:
        """Refresh the access token."""
        self._ensure_initialized()
        await self._async_client.refresh_token()

    # Class methods for authentication
    @classmethod
    def auth_flow(
        cls,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:1234",
        scopes: list[str] | None = None,
        open_browser: bool = True,
        request_delay: float = 0.0,
        max_concurrent_requests: int = 10,
    ) -> "WhoopClientV2Sync":
        """
        Perform OAuth2 authorization flow.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            redirect_uri: OAuth2 redirect URI
            scopes: List of scopes to request
            open_browser: Whether to open the authorization URL in browser
            request_delay: Delay in seconds between requests (default: 0)
            max_concurrent_requests: Maximum concurrent requests (default: 10)

        Returns:
            Authenticated WhoopClientV2Sync instance
        """

        async def _auth() -> TokenInfo:
            client = await WhoopClientV2.auth_flow(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scopes=scopes,
                open_browser=open_browser,
            )
            token = client.token_info
            if token is None:
                raise RuntimeError("Failed to authenticate")
            return token

        # Use asyncio.run for class method since no instance exists yet
        token_info = asyncio.run(_auth())

        return cls(
            token_info=token_info,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            request_delay=request_delay,
            max_concurrent_requests=max_concurrent_requests,
        )

    @classmethod
    def from_token(
        cls,
        access_token: str,
        expires_in: int = 3600,
        refresh_token: str | None = None,
        scopes: list[str] | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> "WhoopClientV2Sync":
        """
        Create client from existing token.

        Args:
            access_token: OAuth2 access token
            expires_in: Token validity duration in seconds (default: 3600)
            refresh_token: OAuth2 refresh token for token renewal
            scopes: List of OAuth2 scopes granted to the token
            client_id: OAuth2 client ID (required for token refresh)
            client_secret: OAuth2 client secret (required for token refresh)

        Returns:
            Configured WhoopClientV2Sync instance
        """
        client = WhoopClientV2.from_token(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            scopes=scopes,
            client_id=client_id,
            client_secret=client_secret,
        )

        return cls(token_info=client.token_info, client_id=client_id, client_secret=client_secret)

    @classmethod
    def from_config(
        cls, config_path: str = "config.json", token_path: str = ".whoop_credentials.json"
    ) -> "WhoopClientV2Sync":
        """
        Create client from configuration files.

        Args:
            config_path: Path to JSON config file containing client credentials
            token_path: Path to save/load token file

        Returns:
            Configured WhoopClientV2Sync instance

        Raises:
            ConfigurationError: If config file not found or invalid
        """
        client = WhoopClientV2.from_config(config_path=config_path, token_path=token_path)

        return cls(
            token_info=client.token_info,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri=client.redirect_uri,
        )
