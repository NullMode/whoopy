"""OAuth2 authentication helpers for Whoop API v2.

Copyright (c) 2024 Felix Geilert
"""

import json
import os
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar
from urllib.parse import urlencode

import aiohttp

from whoopy.constants import HTTP_OK
from whoopy.exceptions import AuthenticationError, RefreshTokenError


@dataclass
class TokenInfo:
    """Container for OAuth2 token information."""

    access_token: str
    expires_in: int
    refresh_token: str | None
    scopes: list[str]
    token_type: str = "Bearer"
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired."""
        if self.created_at is None:
            return True  # Consider expired if no creation time

        current_time = datetime.now(timezone.utc)
        expiry_time = self.created_at + timedelta(seconds=self.expires_in)

        # Add 60 second buffer to account for clock skew
        is_expired = current_time >= expiry_time - timedelta(seconds=60)

        if is_expired:
            time_since_expiry = current_time - expiry_time
            print(f"Token expired {time_since_expiry.total_seconds():.0f} seconds ago")

        return is_expired

    @property
    def expires_at(self) -> datetime:
        """Get the expiration time of the token."""
        if self.created_at is None:
            # Should not happen due to __post_init__, but mypy doesn't know that
            return datetime.now(timezone.utc)
        return self.created_at + timedelta(seconds=self.expires_in)

    @property
    def time_until_expiry(self) -> timedelta:
        """Get time remaining until token expires."""
        return self.expires_at - datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "access_token": self.access_token,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scopes": self.scopes,
            "token_type": self.token_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenInfo":
        """
        Create TokenInfo from dictionary.

        Args:
            data: Dictionary containing token information with keys:
                - access_token: OAuth2 access token (required)
                - expires_in: Token validity duration in seconds (required)
                - refresh_token: Optional refresh token
                - scopes: Optional list of granted scopes
                - token_type: Token type (default: "Bearer")
                - created_at: Optional ISO format creation timestamp

        Returns:
            TokenInfo instance
        """
        created_at = data.get("created_at")
        if created_at:
            created_at = datetime.fromisoformat(created_at)

        return cls(
            access_token=data["access_token"],
            expires_in=data["expires_in"],
            refresh_token=data.get("refresh_token"),
            scopes=data.get("scopes", []),
            token_type=data.get("token_type", "Bearer"),
            created_at=created_at or datetime.now(timezone.utc),
        )


class OAuth2Helper:
    """Helper class for OAuth2 authentication flow."""

    AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
    TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

    DEFAULT_SCOPES: ClassVar[list[str]] = [
        "offline",
        "read:recovery",
        "read:cycles",
        "read:sleep",
        "read:workout",
        "read:profile",
        "read:body_measurement",
    ]

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:1234",
        scopes: list[str] | None = None,
    ):
        """
        Initialize OAuth2Helper.

        Args:
            client_id: OAuth2 client ID from Whoop developer portal
            client_secret: OAuth2 client secret from Whoop developer portal
            redirect_uri: Redirect URI for OAuth2 flow (default: "http://localhost:1234")
            scopes: List of OAuth2 scopes to request (default: all read scopes)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or self.DEFAULT_SCOPES

    def get_authorization_url(self, state: str | None = None) -> str:
        """
        Generate the authorization URL for the OAuth2 flow.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL to redirect user to
        """
        if state is None:
            state = str(uuid.uuid4())

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
        }

        return f"{self.AUTH_URL}?{urlencode(params)}"

    def open_authorization_url(self, state: str | None = None) -> str:
        """
        Open the authorization URL in the default browser.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            The state parameter used (generated if not provided)
        """
        url = self.get_authorization_url(state)
        webbrowser.open(url)
        return url

    async def exchange_code_for_token(self, session: aiohttp.ClientSession, code: str) -> TokenInfo:
        """Exchange authorization code for access token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
        }

        async with session.post(self.TOKEN_URL, data=data) as response:
            if response.status != HTTP_OK:
                error_data = await response.text()
                raise AuthenticationError(
                    f"Failed to exchange code for token: {response.status}",
                    details={"status": response.status, "response": error_data},
                )

            token_data = await response.json()

        return TokenInfo(
            access_token=token_data["access_token"],
            expires_in=token_data["expires_in"],
            refresh_token=token_data.get("refresh_token"),
            scopes=token_data.get("scope", "").split() if token_data.get("scope") else self.scopes,
            token_type=token_data.get("token_type", "Bearer"),
        )

    async def refresh_access_token(self, session: aiohttp.ClientSession, refresh_token: str) -> TokenInfo:
        """
        Refresh an expired access token.

        Args:
            session: aiohttp session for making the request
            refresh_token: Refresh token from previous authentication

        Returns:
            TokenInfo containing the new access token and metadata

        Raises:
            RefreshTokenError: If token refresh fails
        """
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with session.post(self.TOKEN_URL, data=data) as response:
            if response.status != HTTP_OK:
                error_data = await response.text()
                raise RefreshTokenError(
                    f"Failed to refresh token: {response.status}",
                    details={"status": response.status, "response": error_data},
                )

            token_data = await response.json()

        return TokenInfo(
            access_token=token_data["access_token"],
            expires_in=token_data["expires_in"],
            refresh_token=token_data.get("refresh_token", refresh_token),
            scopes=token_data.get("scope", "").split() if token_data.get("scope") else self.scopes,
            token_type=token_data.get("token_type", "Bearer"),
        )

    def save_token(self, token: TokenInfo, path: str = ".whoop_credentials.json") -> None:
        """
        Save token to file.

        Args:
            token: TokenInfo to save
            path: Path to save the token file (default: ".whoop_credentials.json")
        """
        # Create directory if it doesn't exist
        dir_path = os.path.dirname(path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        with open(path, "w") as f:
            json.dump(token.to_dict(), f, indent=2)

    def load_token(self, path: str = ".whoop_credentials.json") -> TokenInfo | None:
        """
        Load token from file.

        Args:
            path: Path to load the token file from (default: ".whoop_credentials.json")

        Returns:
            TokenInfo if file exists and is valid, None otherwise
        """
        if not os.path.exists(path):
            return None

        try:
            with open(path) as f:
                data = json.load(f)
            return TokenInfo.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None
