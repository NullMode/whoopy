"""Base handler for Whoop API v2 resources.

Copyright (c) 2024 Felix Geilert
"""

from __future__ import annotations

from abc import ABC
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from whoopy.client_v2 import WhoopClientV2

import pandas as pd

from whoopy.exceptions import ResourceNotFoundError
from whoopy.models import models_v2 as models
from whoopy.utils import PaginatedResponse, PaginationHelper

T = TypeVar("T", bound=models.BaseWhoopModel)


class BaseHandler(ABC):  # noqa: B024
    """Base handler for API resources."""

    def __init__(self, client: WhoopClientV2):
        """
        Initialize handler.

        Args:
            client: WhoopClientV2 instance
        """
        self.client = client

    async def _get(self, path: str, **kwargs: Any) -> Any:
        """Make a GET request."""
        response = await self.client.request("GET", path, **kwargs)
        return await response.json()

    async def _post(self, path: str, **kwargs: Any) -> Any:
        """Make a POST request."""
        response = await self.client.request("POST", path, **kwargs)
        return await response.json()

    def _parse_datetime(self, dt: str | datetime | None) -> str | None:
        """Parse datetime to ISO format string."""
        if dt is None:
            return None

        if isinstance(dt, str):
            # Assume it's already in correct format
            return dt

        if isinstance(dt, datetime):
            # Ensure datetime is timezone-aware
            if dt.tzinfo is None:
                # Assume UTC for naive datetimes
                from datetime import timezone

                dt = dt.replace(tzinfo=timezone.utc)

            # Convert to ISO format with Z suffix
            return dt.isoformat().replace("+00:00", "Z")

        raise ValueError(f"Invalid datetime type: {type(dt)}")


class ResourceHandler(BaseHandler, Generic[T]):
    """Base handler for single resources."""

    def __init__(self, client: WhoopClientV2, resource_path: str, model_class: type[T]):
        """
        Initialize resource handler.

        Args:
            client: WhoopClientV2 instance
            resource_path: Base path for the resource
            model_class: Pydantic model class for the resource
        """
        BaseHandler.__init__(self, client)
        self.resource_path = resource_path
        self.model_class = model_class

    async def get_by_id(self, resource_id: str | int) -> T:
        """
        Get a single resource by ID.

        Args:
            resource_id: The resource ID

        Returns:
            The resource model instance

        Raises:
            ResourceNotFoundError: If resource not found
        """
        try:
            path = f"{self.resource_path}/{resource_id}"
            data = await self._get(path)
            return self.model_class(**data)
        except Exception as e:
            if "404" in str(e):
                raise ResourceNotFoundError(
                    resource_type=self.model_class.__name__, resource_id=str(resource_id)
                ) from e
            raise


class CollectionHandler(BaseHandler, Generic[T]):
    """Base handler for resource collections with pagination."""

    def __init__(
        self,
        client: WhoopClientV2,
        collection_path: str,
        model_class: type[T],
        response_class: type[PaginatedResponse],
    ):
        """
        Initialize collection handler.

        Args:
            client: WhoopClientV2 instance
            collection_path: Base path for the collection
            model_class: Pydantic model class for items
            response_class: Pydantic model class for paginated response
        """
        BaseHandler.__init__(self, client)
        self.collection_path = collection_path
        self.model_class = model_class
        self.response_class = response_class

        # Create pagination helper
        self._pagination = PaginationHelper(fetch_page=self._fetch_page, model_class=model_class)

    async def _fetch_page(self, **params: Any) -> PaginatedResponse[T]:
        """Fetch a single page of results."""
        # Clean up parameters
        cleaned_params = {}

        if "limit" in params and params["limit"] is not None:
            cleaned_params["limit"] = min(max(1, int(params["limit"])), 25)

        if "start" in params and params["start"] is not None:
            cleaned_params["start"] = self._parse_datetime(params["start"])  # type: ignore[assignment]

        if "end" in params and params["end"] is not None:
            cleaned_params["end"] = self._parse_datetime(params["end"])  # type: ignore[assignment]

        if "next_token" in params and params["next_token"] is not None:
            cleaned_params["nextToken"] = params["next_token"]

        # Make request
        data = await self._get(self.collection_path, params=cleaned_params)

        # Parse response
        response = self.response_class(**data)
        return PaginatedResponse(records=response.records, next_token=response.next_token)

    async def get_page(
        self,
        limit: int = 10,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        next_token: str | None = None,
    ) -> PaginatedResponse[T]:
        """
        Get a single page of results.

        Args:
            limit: Number of items per page (1-25)
            start: Start time filter
            end: End time filter
            next_token: Token for next page

        Returns:
            Paginated response with items and next token
        """
        return await self._pagination.get_page(limit=limit, start=start, end=end, next_token=next_token)

    async def get_all(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ) -> list[T]:
        """
        Get all items across all pages.

        Args:
            start: Start time filter
            end: End time filter
            limit_per_page: Items per page (1-25)
            max_records: Maximum total items to fetch

        Returns:
            List of all items
        """
        return await self._pagination.get_all(
            start=start, end=end, limit_per_page=limit_per_page, max_records=max_records
        )

    async def iterate(
        self, start: str | datetime | None = None, end: str | datetime | None = None, limit_per_page: int = 25
    ) -> AsyncIterator[T]:
        """
        Iterate over all items across all pages.

        Args:
            start: Start time filter
            end: End time filter
            limit_per_page: Items per page (1-25)

        Yields:
            Individual items
        """
        async for item in self._pagination.iterate(start=start, end=end, limit_per_page=limit_per_page):
            yield item

    async def get_dataframe(
        self,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        limit_per_page: int = 25,
        max_records: int | None = None,
    ) -> pd.DataFrame:
        """
        Get all items as a pandas DataFrame.

        Args:
            start: Start time filter
            end: End time filter
            limit_per_page: Items per page (1-25)
            max_records: Maximum total items to fetch

        Returns:
            DataFrame with all items
        """
        items = await self.get_all(start=start, end=end, limit_per_page=limit_per_page, max_records=max_records)

        return models.models_to_dataframe(items)  # type: ignore[arg-type]


class CombinedHandler(ResourceHandler[T], CollectionHandler[T]):
    """Handler that supports both single resource and collection operations."""

    def __init__(
        self,
        client: WhoopClientV2,
        resource_path: str,
        collection_path: str,
        model_class: type[T],
        response_class: type[PaginatedResponse[Any]],
    ):
        """
        Initialize combined handler.

        Args:
            client: WhoopClientV2 instance
            resource_path: Base path for single resources
            collection_path: Base path for collections
            model_class: Pydantic model class
            response_class: Pydantic model class for paginated response
        """
        # Initialize both base classes
        ResourceHandler.__init__(self, client, resource_path, model_class)
        CollectionHandler.__init__(self, client, collection_path, model_class, response_class)

        # Ensure we use the client from BaseHandler
        self.client = client
