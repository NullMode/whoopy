"""Whoop API v2 client with async/await support.

This module provides the main client for interacting with the Whoop API v2.
It features modern async/await patterns, automatic retry logic, and proper
error handling.

Follows api docs: https://api.prod.whoop.com/developer/doc/openapi.json

Copyright (c) 2024 Felix Geilert
"""

import json
import logging
import os
from typing import Any

import aiohttp

from .constants import (
    HTTP_BAD_REQUEST,
    HTTP_INTERNAL_SERVER_ERROR,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_TOO_MANY_REQUESTS,
    HTTP_UNAUTHORIZED,
)
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    RateLimitError,
    RefreshTokenError,
    ResourceNotFoundError,
    ServerError,
    TokenExpiredError,
    ValidationError,
    WhoopException,
)
from .handlers import handlers_v2 as handlers
from .utils import OAuth2Helper, RequestThrottler, RetryableSession, RetryConfig, TokenInfo

API_VERSION = "2"
API_BASE = "https://api.prod.whoop.com/"


class WhoopClientV2:
    """Async client for Whoop API v2."""

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
        Initialize the Whoop API v2 client.

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
        self.token_info = token_info
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.retry_config = retry_config or RetryConfig()
        self.auto_refresh_token = auto_refresh_token
        self.logger = logger or logging.getLogger("whoopy")
        self.request_delay = request_delay
        self.max_concurrent_requests = max_concurrent_requests

        # Session will be created in __aenter__
        self._session: aiohttp.ClientSession | None = None
        self._retry_session: RetryableSession | None = None

        # Request throttler
        self._throttler = RequestThrottler(delay=self.request_delay, max_concurrent=self.max_concurrent_requests)

        # OAuth helper
        if client_id and client_secret:
            self._oauth_helper = OAuth2Helper(
                client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri
            )
        else:
            self._oauth_helper = None  # type: ignore[assignment]

        # API handlers (will be initialized after session is created)
        self._cycles: handlers.CycleHandler | None = None
        self._sleep: handlers.SleepHandler | None = None
        self._recovery: handlers.RecoveryHandler | None = None
        self._workouts: handlers.WorkoutHandler | None = None
        self._user: handlers.UserHandler | None = None

    @property
    def base_url(self) -> str:
        """Get the base URL for API requests."""
        return f"{API_BASE}developer/v{API_VERSION}"

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get the HTTP session."""
        if self._session is None:
            raise RuntimeError("Client session not initialized. Use 'async with' context manager.")
        return self._session

    @property
    def retry_session(self) -> RetryableSession:
        """Get the retry-enabled session."""
        if self._retry_session is None:
            raise RuntimeError("Client session not initialized. Use 'async with' context manager.")
        return self._retry_session

    # Handler properties
    @property
    def cycles(self) -> handlers.CycleHandler:
        """Get the cycles handler."""
        if self._cycles is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._cycles

    @property
    def sleep(self) -> handlers.SleepHandler:
        """Get the sleep handler."""
        if self._sleep is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._sleep

    @property
    def recovery(self) -> handlers.RecoveryHandler:
        """Get the recovery handler."""
        if self._recovery is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._recovery

    @property
    def workouts(self) -> handlers.WorkoutHandler:
        """Get the workouts handler."""
        if self._workouts is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._workouts

    @property
    def user(self) -> handlers.UserHandler:
        """Get the user handler."""
        if self._user is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._user

    async def __aenter__(self) -> "WhoopClientV2":
        """Enter async context manager."""
        # Check if we have authentication
        if self.token_info is None:
            self.logger.error("No authentication token available")
            raise AuthenticationError(
                "No authentication token available. Please authenticate first using "
                "WhoopClientV2.auth_flow() or provide a valid token."
            )

        # Check if token needs refresh before creating session
        if (
            self.token_info.is_expired
            and self.auto_refresh_token
            and self.token_info.refresh_token
            and self._oauth_helper
        ):
            self.logger.info("Token expired, attempting to refresh")
            try:
                # Create temporary session for token refresh
                async with aiohttp.ClientSession() as temp_session:
                    self.token_info = await self._oauth_helper.refresh_access_token(
                        temp_session, self.token_info.refresh_token
                    )
                self.logger.info("Token refreshed successfully")
            except Exception as e:
                # Log but don't fail - let the first API call handle auth errors
                self.logger.warning(f"Failed to refresh expired token: {e}")

        # Create session with proper headers
        headers = {
            "User-Agent": "Whoopy/0.3.0 (Python Whoop API Client)",
            "Accept": "application/json",
        }

        if self.token_info:
            headers["Authorization"] = f"{self.token_info.token_type} {self.token_info.access_token}"

        self._session = aiohttp.ClientSession(headers=headers)
        self._retry_session = RetryableSession(self._session, self.retry_config, self.check_response)

        # Initialize handlers
        self._cycles = handlers.CycleHandler(self)
        self._sleep = handlers.SleepHandler(self)
        self._recovery = handlers.RecoveryHandler(self)
        self._workouts = handlers.WorkoutHandler(self)
        self._user = handlers.UserHandler(self)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        if self._session:
            await self._session.close()

    async def check_response(self, response: aiohttp.ClientResponse) -> None:
        """
        Check API response for errors.

        Args:
            response: The aiohttp response object

        Raises:
            Various WhoopException subclasses based on status code
        """
        if response.status == HTTP_OK:
            return

        # Try to get error details from response
        try:
            error_data = await response.json()
        except Exception:
            error_data = await response.text()

        # Map status codes to exceptions
        if response.status == HTTP_BAD_REQUEST:
            raise ValidationError(
                message="Bad request",
                validation_errors=error_data if isinstance(error_data, dict) else None,
                details={"status": HTTP_BAD_REQUEST, "response": error_data},
            )
        if response.status == HTTP_UNAUTHORIZED:
            if self.auto_refresh_token and self.token_info and self.token_info.refresh_token:
                # Token might be expired, try to refresh
                raise TokenExpiredError(details={"status": HTTP_UNAUTHORIZED, "response": error_data})
            raise AuthenticationError(details={"status": HTTP_UNAUTHORIZED, "response": error_data})
        if response.status == HTTP_NOT_FOUND:
            raise ResourceNotFoundError(
                resource_type="Resource", details={"status": HTTP_NOT_FOUND, "response": error_data}
            )
        if response.status == HTTP_TOO_MANY_REQUESTS:
            retry_after = response.headers.get("Retry-After")
            self.logger.warning(f"Rate limit hit. Retry-After: {retry_after}")
            # Adjust throttler delay when we hit rate limits
            self._throttler.adjust_delay(factor=2.0)
            raise RateLimitError(
                retry_after=int(retry_after) if retry_after else None,
                details={"status": HTTP_TOO_MANY_REQUESTS, "response": error_data},
            )
        if response.status >= HTTP_INTERNAL_SERVER_ERROR:
            raise ServerError(
                status_code=response.status,
                message=f"Server error: {response.status}",
                details={"status": response.status, "response": error_data},
            )
        raise WhoopException(
            f"Unexpected status code: {response.status}", details={"status": response.status, "response": error_data}
        )

    async def refresh_token(self) -> None:
        """
        Refresh the access token using the refresh token.

        This method uses the stored refresh token to obtain a new access token
        from the Whoop OAuth2 endpoint. The token info is automatically updated.

        Raises:
            ConfigurationError: If OAuth helper not configured (missing client_id/secret)
            RefreshTokenError: If refresh fails or no refresh token available
        """
        if not self._oauth_helper:
            raise ConfigurationError("Cannot refresh token without client_id and client_secret")

        if not self.token_info or not self.token_info.refresh_token:
            raise RefreshTokenError("No refresh token available")

        try:
            self.token_info = await self._oauth_helper.refresh_access_token(self.session, self.token_info.refresh_token)

            # Update session headers with new token
            if self._session:
                self._session.headers["Authorization"] = f"{self.token_info.token_type} {self.token_info.access_token}"

        except Exception as e:
            raise RefreshTokenError(f"Failed to refresh token: {e!s}") from e

    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Make an authenticated request to the API.

        This method handles token refresh if needed.

        Args:
            method: HTTP method
            path: API path (relative to base URL)
            params: Query parameters
            json_data: JSON request body
            **kwargs: Additional arguments for aiohttp

        Returns:
            The response object
        """
        url = f"{self.base_url}/{path}"

        # Apply throttling
        async with self._throttler:
            self.logger.debug(f"Request: {method} {url} params={params}")

            # Try the request
            try:
                response = await self.retry_session.request(method, url, params=params, json=json_data, **kwargs)
                self.logger.debug(f"Response: {response.status} for {method} {url}")
                return response  # type: ignore[no-any-return]

            except TokenExpiredError:
                self.logger.info("Token expired during request, refreshing and retrying")
                # Try to refresh token and retry once
                await self.refresh_token()
                response = await self.retry_session.request(method, url, params=params, json=json_data, **kwargs)
                self.logger.debug(f"Retry response: {response.status} for {method} {url}")
                return response  # type: ignore[no-any-return]

    # Authentication methods
    @classmethod
    async def auth_flow(
        cls,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:1234",
        scopes: list[str] | None = None,
        open_browser: bool = True,
    ) -> "WhoopClientV2":
        """
        Perform OAuth2 authorization flow.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            redirect_uri: OAuth2 redirect URI
            scopes: List of scopes to request
            open_browser: Whether to open the authorization URL in browser

        Returns:
            Authenticated WhoopClientV2 instance
        """
        oauth_helper = OAuth2Helper(
            client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri, scopes=scopes
        )

        # Get authorization URL
        auth_url = oauth_helper.get_authorization_url()

        if open_browser:
            print(f"Opening browser to: {auth_url}")
            oauth_helper.open_authorization_url()
        else:
            print(f"Visit this URL to authorize: {auth_url}")

        # Get authorization code from user
        print(f"\nAfter authorization, you'll be redirected to: {redirect_uri}")
        redirect_url = input("Paste the full redirect URL here: ").strip()

        # Extract code from redirect URL
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(redirect_url)
        code = parse_qs(parsed.query).get("code", [None])[0]

        if not code:
            raise AuthenticationError("No authorization code found in redirect URL")

        # Exchange code for token
        async with aiohttp.ClientSession() as session:
            token_info = await oauth_helper.exchange_code_for_token(session, code)

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
    ) -> "WhoopClientV2":
        """
        Create client from existing token.

        Args:
            access_token: The access token
            expires_in: Token expiration time in seconds
            refresh_token: Optional refresh token
            scopes: List of token scopes
            client_id: OAuth2 client ID (for refresh)
            client_secret: OAuth2 client secret (for refresh)

        Returns:
            WhoopClientV2 instance
        """
        token_info = TokenInfo(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh_token,
            scopes=scopes or OAuth2Helper.DEFAULT_SCOPES,
        )

        return cls(token_info=token_info, client_id=client_id, client_secret=client_secret)

    @classmethod
    def from_config(
        cls, config_path: str = "config.json", token_path: str = ".whoop_credentials.json"
    ) -> "WhoopClientV2":
        """
        Create client from configuration files.

        Args:
            config_path: Path to config file with client credentials
            token_path: Path to saved token file

        Returns:
            WhoopClientV2 instance
        """
        # Load config
        if not os.path.exists(config_path):
            raise ConfigurationError(f"Config file not found: {config_path}")

        with open(config_path) as f:
            config_data = json.load(f)

        # Handle both flat and nested config structures
        assert isinstance(config_data, dict)
        config = config_data.get("whoop", config_data)

        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        redirect_uri = config.get("redirect_uri", "http://localhost:1234")

        if not client_id or not client_secret:
            raise ConfigurationError("client_id and client_secret required in config")

        # Try to load existing token
        oauth_helper = OAuth2Helper(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)

        token_info = oauth_helper.load_token(token_path)

        return cls(token_info=token_info, client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)

    def save_token(self, path: str = ".whoop_credentials.json") -> None:
        """
        Save current token to file.

        Saves the current OAuth2 token information to a JSON file for later use.

        Args:
            path: Path to save the token file (default: ".whoop_credentials.json")

        Raises:
            ValueError: If no token to save
        """
        if not self.token_info:
            raise ValueError("No token to save")

        if self._oauth_helper:
            self._oauth_helper.save_token(self.token_info, path)
        else:
            # Save manually
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(self.token_info.to_dict(), f, indent=2)
