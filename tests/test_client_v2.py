"""Unit tests for Whoop API v2 client.

Copyright (c) 2024 Felix Geilert
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from aioresponses import aioresponses

from whoopy.client_v2 import WhoopClientV2
from whoopy.exceptions import (
    RateLimitError,
    ResourceNotFoundError,
    ServerError,
    TokenExpiredError,
    ValidationError,
)
from whoopy.utils import RetryConfig, TokenInfo


class TestWhoopClientV2:
    """Test WhoopClientV2 functionality."""

    @pytest.fixture
    def token_info(self):
        """Create test token info."""
        return TokenInfo(
            access_token="test_access_token",
            expires_in=3600,
            refresh_token="test_refresh_token",
            scopes=["read:cycles", "read:sleep", "offline"],
        )

    @pytest.fixture
    def client(self, token_info):
        """Create test client."""
        return WhoopClientV2(token_info=token_info, client_id="test_client_id", client_secret="test_client_secret")

    @pytest.mark.asyncio
    async def test_client_context_manager(self, client):
        """Test client context manager creates and closes session."""
        async with client as whoop:
            assert whoop._session is not None
            assert isinstance(whoop._session, aiohttp.ClientSession)
            assert whoop._retry_session is not None
            assert whoop.cycles is not None
            assert whoop.sleep is not None
            assert whoop.recovery is not None
            assert whoop.workouts is not None
            assert whoop.user is not None

        # After exiting, session should be closed
        assert client._session.closed

    @pytest.mark.asyncio
    async def test_client_headers(self, client, token_info):
        """Test client sets proper headers."""
        async with client as whoop:
            headers = whoop.session.headers
            assert headers["Authorization"] == f"Bearer {token_info.access_token}"
            assert "User-Agent" in headers
            assert headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_check_response_success(self, client):
        """Test successful response check."""
        async with client as whoop:
            response = Mock()
            response.status = 200

            # Should not raise any exception
            await whoop.check_response(response)

    @pytest.mark.asyncio
    async def test_check_response_errors(self, client):
        """Test error response handling."""
        async with client as whoop:
            # 400 Bad Request
            response = Mock()
            response.status = 400
            response.json = AsyncMock(return_value={"error": "bad request"})

            with pytest.raises(ValidationError):
                await whoop.check_response(response)

            # 401 Unauthorized
            response.status = 401
            with pytest.raises(TokenExpiredError):
                await whoop.check_response(response)

            # 404 Not Found
            response.status = 404
            with pytest.raises(ResourceNotFoundError):
                await whoop.check_response(response)

            # 429 Rate Limited
            response.status = 429
            response.headers = {"Retry-After": "60"}
            with pytest.raises(RateLimitError) as exc_info:
                await whoop.check_response(response)
            assert exc_info.value.retry_after == 60

            # 500 Server Error
            response.status = 500
            response.headers = {}
            with pytest.raises(ServerError):
                await whoop.check_response(response)

    @pytest.mark.asyncio
    async def test_refresh_token(self, client):
        """Test token refresh functionality."""
        async with client as whoop:
            with aioresponses() as m:
                new_token_data = {
                    "access_token": "new_access_token",
                    "expires_in": 3600,
                    "refresh_token": "new_refresh_token",
                    "token_type": "Bearer",
                }

                m.post("https://api.prod.whoop.com/oauth/oauth2/token", payload=new_token_data)

                await whoop.refresh_token()

                assert whoop.token_info.access_token == "new_access_token"
                assert whoop.token_info.refresh_token == "new_refresh_token"
                assert whoop.session.headers["Authorization"] == "Bearer new_access_token"

    @pytest.mark.asyncio
    async def test_request_with_token_refresh(self, client):
        """Test automatic token refresh on 401."""
        async with client as whoop:
            with aioresponses() as m:
                # First request returns 401
                m.get("https://api.prod.whoop.com/developer/v2/test", status=401)

                # Token refresh
                m.post(
                    "https://api.prod.whoop.com/oauth/oauth2/token",
                    payload={
                        "access_token": "new_access_token",
                        "expires_in": 3600,
                        "refresh_token": "new_refresh_token",
                        "token_type": "Bearer",
                    },
                )

                # Retry request succeeds
                m.get("https://api.prod.whoop.com/developer/v2/test", payload={"data": "test"})

                response = await whoop.request("GET", "test")
                data = await response.json()
                assert data == {"data": "test"}
                assert whoop.token_info.access_token == "new_access_token"


class TestAuthenticationMethods:
    """Test authentication class methods."""

    @pytest.mark.asyncio
    async def test_from_token(self):
        """Test creating client from token."""
        client = WhoopClientV2.from_token(
            access_token="test_token",
            expires_in=3600,
            refresh_token="refresh_token",
            scopes=["read:cycles"],
            client_id="client_id",
            client_secret="client_secret",
        )

        assert client.token_info.access_token == "test_token"
        assert client.token_info.refresh_token == "refresh_token"
        assert client.client_id == "client_id"
        assert client.client_secret == "client_secret"

    @pytest.mark.asyncio
    async def test_from_config(self, tmp_path):
        """Test creating client from config files."""
        # Create config file
        config_file = tmp_path / "config.json"
        config_file.write_text("""{
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "redirect_uri": "http://localhost:1234"
        }""")

        # Create token file
        token_file = tmp_path / ".whoop_credentials.json"
        token_file.write_text(f"""{{
            "access_token": "saved_token",
            "expires_in": 3600,
            "refresh_token": "saved_refresh",
            "scopes": ["read:cycles"],
            "token_type": "Bearer",
            "created_at": "{datetime.now(timezone.utc).isoformat()}"
        }}""")

        client = WhoopClientV2.from_config(config_path=str(config_file), token_path=str(token_file))

        assert client.token_info.access_token == "saved_token"
        assert client.client_id == "test_client_id"
        assert client.client_secret == "test_client_secret"

    def test_save_token(self, tmp_path):
        """Test saving token to file."""
        token_info = TokenInfo(
            access_token="test_token", expires_in=3600, refresh_token="refresh_token", scopes=["read:cycles"]
        )

        client = WhoopClientV2(token_info=token_info)

        token_file = tmp_path / "token.json"
        client.save_token(str(token_file))

        assert token_file.exists()

        # Load and verify
        import json

        with open(token_file) as f:
            saved_data = json.load(f)

        assert saved_data["access_token"] == "test_token"
        assert saved_data["refresh_token"] == "refresh_token"
        assert saved_data["scopes"] == ["read:cycles"]


class TestRetryLogic:
    """Test retry functionality."""

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self):
        """Test retry on 500 error."""
        token_info = TokenInfo(access_token="test_token", expires_in=3600, refresh_token=None, scopes=[])

        retry_config = RetryConfig(max_attempts=3, base_delay=0.1, jitter=False)

        client = WhoopClientV2(token_info=token_info, retry_config=retry_config, auto_refresh_token=False)

        async with client as whoop:
            with aioresponses() as m:
                # First two attempts fail
                m.get("https://api.prod.whoop.com/developer/v2/test", status=500)
                m.get("https://api.prod.whoop.com/developer/v2/test", status=500)
                # Third attempt succeeds
                m.get("https://api.prod.whoop.com/developer/v2/test", payload={"data": "success"})

                response = await whoop.request("GET", "test")
                data = await response.json()
                assert data == {"data": "success"}

    @pytest.mark.asyncio
    async def test_retry_with_rate_limit(self):
        """Test retry with rate limit header."""
        token_info = TokenInfo(access_token="test_token", expires_in=3600, refresh_token=None, scopes=[])

        retry_config = RetryConfig(max_attempts=2, base_delay=0.1, jitter=False)

        client = WhoopClientV2(token_info=token_info, retry_config=retry_config, auto_refresh_token=False)

        async with client as whoop:
            with aioresponses() as m:
                # First attempt rate limited
                m.get("https://api.prod.whoop.com/developer/v2/test", status=429, headers={"Retry-After": "1"})
                # Second attempt succeeds
                m.get("https://api.prod.whoop.com/developer/v2/test", payload={"data": "success"})

                start_time = asyncio.get_event_loop().time()
                response = await whoop.request("GET", "test")
                end_time = asyncio.get_event_loop().time()

                data = await response.json()
                assert data == {"data": "success"}
                # Should have waited at least 1 second
                assert end_time - start_time >= 0.9  # Allow small variance
