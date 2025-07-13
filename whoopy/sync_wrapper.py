"""Synchronous wrapper for the async Whoop API v2 client.

This module provides a synchronous interface to the async WhoopClientV2,
making it easy to use in non-async code while maintaining the benefits
of the modern implementation.

Copyright (c) 2024 Felix Geilert
"""

import asyncio
import functools
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar
from uuid import UUID

import pandas as pd

from .client_v2 import WhoopClientV2
from .models import models_v2 as models
from .utils import RetryConfig, TokenInfo

T = TypeVar("T")


def run_async(coro):
    """Run an async coroutine in a sync context."""
    import contextlib

    loop = None
    with contextlib.suppress(RuntimeError):
        loop = asyncio.get_running_loop()

    if loop is not None:
        # We're already in an async context
        raise RuntimeError("Cannot use sync wrapper from within an async context. Use WhoopClientV2 directly instead.")

    return asyncio.run(coro)


def async_to_sync(method: Callable) -> Callable:
    """Decorator to convert async methods to sync."""

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        coro = method(*args, **kwargs)
        return run_async(coro)

    return wrapper


class SyncUserHandler:
    """Synchronous wrapper for UserHandler."""

    def __init__(self, async_handler):
        self._handler = async_handler

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

    @async_to_sync
    async def get_page(
        self,
        limit: int = 10,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        next_token: str | None = None,
    ):
        """Get a single page of results."""
        return await self._handler.get_page(limit=limit, start=start, end=end, next_token=next_token)

    @async_to_sync
    async def get_all(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ):
        """Get all items across all pages."""
        return await self._handler.get_all(start=start, end=end, limit_per_page=limit_per_page, max_records=max_records)

    def iterate(self, start: str | datetime | None = None, end: str | datetime | None = None, limit_per_page: int = 25):
        """Iterate over all items across all pages."""

        async def _iterate():
            items = []
            async for item in self._handler.iterate(start=start, end=end, limit_per_page=limit_per_page):
                items.append(item)
            return items

        # Return all items as a list since we can't yield from sync
        return run_async(_iterate())

    @async_to_sync
    async def get_dataframe(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ) -> pd.DataFrame:
        """Get all items as a pandas DataFrame."""
        return await self._handler.get_dataframe(
            start=start, end=end, limit_per_page=limit_per_page, max_records=max_records
        )


class SyncCycleHandler(SyncCollectionMixin):
    """Synchronous wrapper for CycleHandler."""

    def __init__(self, async_handler):
        self._handler = async_handler

    @async_to_sync
    async def get_by_id(self, cycle_id: int) -> models.Cycle:
        """Get a cycle by ID."""
        return await self._handler.get_by_id(cycle_id)

    @async_to_sync
    async def get_sleep(self, cycle_id: int) -> models.Sleep:
        """Get the sleep for a specific cycle."""
        return await self._handler.get_sleep(cycle_id)


class SyncSleepHandler(SyncCollectionMixin):
    """Synchronous wrapper for SleepHandler."""

    def __init__(self, async_handler):
        self._handler = async_handler

    @async_to_sync
    async def get_by_id(self, sleep_id: str | UUID) -> models.Sleep:
        """Get a sleep activity by ID."""
        return await self._handler.get_by_id(sleep_id)


class SyncRecoveryHandler(SyncCollectionMixin):
    """Synchronous wrapper for RecoveryHandler."""

    def __init__(self, async_handler):
        self._handler = async_handler

    @async_to_sync
    async def get_for_cycle(self, cycle_id: int) -> models.Recovery:
        """Get the recovery for a specific cycle."""
        return await self._handler.get_for_cycle(cycle_id)


class SyncWorkoutHandler(SyncCollectionMixin):
    """Synchronous wrapper for WorkoutHandler."""

    def __init__(self, async_handler):
        self._handler = async_handler

    @async_to_sync
    async def get_by_id(self, workout_id: str | UUID) -> models.WorkoutV2:
        """Get a workout by ID."""
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
        """Get all workouts for a specific sport."""
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
        """
        self._async_client = WhoopClientV2(
            token_info=token_info,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            retry_config=retry_config,
            auto_refresh_token=auto_refresh_token,
        )

        # Initialize sync handlers
        self._user: SyncUserHandler | None = None
        self._cycles: SyncCycleHandler | None = None
        self._sleep: SyncSleepHandler | None = None
        self._recovery: SyncRecoveryHandler | None = None
        self._workouts: SyncWorkoutHandler | None = None

        # Initialize the client
        self._initialize()

    def _initialize(self):
        """Initialize the async client and create sync handlers."""

        async def _init():
            async with self._async_client as client:
                # Create sync wrappers for handlers
                self._user = SyncUserHandler(client.user)
                self._cycles = SyncCycleHandler(client.cycles)
                self._sleep = SyncSleepHandler(client.sleep)
                self._recovery = SyncRecoveryHandler(client.recovery)
                self._workouts = SyncWorkoutHandler(client.workouts)

                # Store reference to keep session alive
                return client

        # Run initialization
        run_async(_init())

    @property
    def user(self) -> SyncUserHandler:
        """Get the user handler."""
        if self._user is None:
            raise RuntimeError("Client not initialized")
        return self._user

    @property
    def cycles(self) -> SyncCycleHandler:
        """Get the cycles handler."""
        if self._cycles is None:
            raise RuntimeError("Client not initialized")
        return self._cycles

    @property
    def sleep(self) -> SyncSleepHandler:
        """Get the sleep handler."""
        if self._sleep is None:
            raise RuntimeError("Client not initialized")
        return self._sleep

    @property
    def recovery(self) -> SyncRecoveryHandler:
        """Get the recovery handler."""
        if self._recovery is None:
            raise RuntimeError("Client not initialized")
        return self._recovery

    @property
    def workouts(self) -> SyncWorkoutHandler:
        """Get the workouts handler."""
        if self._workouts is None:
            raise RuntimeError("Client not initialized")
        return self._workouts

    @property
    def token_info(self) -> TokenInfo | None:
        """Get current token information."""
        return self._async_client.token_info

    def save_token(self, path: str = ".whoop_credentials.json") -> None:
        """Save current token to file."""
        self._async_client.save_token(path)

    @async_to_sync
    async def refresh_token(self) -> None:
        """Refresh the access token."""
        async with self._async_client as client:
            await client.refresh_token()

    # Class methods for authentication
    @classmethod
    def auth_flow(
        cls,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:1234",
        scopes: list[str] | None = None,
        open_browser: bool = True,
    ) -> "WhoopClientV2Sync":
        """
        Perform OAuth2 authorization flow.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            redirect_uri: OAuth2 redirect URI
            scopes: List of scopes to request
            open_browser: Whether to open the authorization URL in browser

        Returns:
            Authenticated WhoopClientV2Sync instance
        """

        async def _auth():
            client = await WhoopClientV2.auth_flow(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scopes=scopes,
                open_browser=open_browser,
            )
            return client.token_info

        token_info = run_async(_auth())

        return cls(token_info=token_info, client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)

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
        """Create client from existing token."""
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
        """Create client from configuration files."""
        client = WhoopClientV2.from_config(config_path=config_path, token_path=token_path)

        return cls(
            token_info=client.token_info,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri=client.redirect_uri,
        )
