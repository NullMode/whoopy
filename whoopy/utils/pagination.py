"""Pagination helpers for Whoop API v2.

Copyright (c) 2024 Felix Geilert
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from whoopy.constants import DEFAULT_PAGE_SIZE

T = TypeVar("T")


@dataclass
class PaginatedResponse(Generic[T]):
    """Container for paginated API responses."""

    records: list[T]
    next_token: str | None = None

    @property
    def has_more(self) -> bool:
        """Check if there are more pages available."""
        return self.next_token is not None


class PaginationHelper(Generic[T]):
    """Helper class for handling paginated API responses."""

    def __init__(self, fetch_page: Callable[..., Awaitable[PaginatedResponse[T]]], model_class: type[T]):
        """
        Initialize pagination helper.

        Args:
            fetch_page: Async function that fetches a single page
            model_class: Pydantic model class for deserializing records
        """
        self.fetch_page = fetch_page
        self.model_class = model_class

    async def get_page(self, limit: int = 10, next_token: str | None = None, **kwargs: Any) -> PaginatedResponse[T]:
        """
        Fetch a single page of results.

        Args:
            limit: Maximum number of items per page (default: 10, max: 25)
            next_token: Token from previous page for pagination
            **kwargs: Additional parameters passed to fetch_page (e.g., start, end)

        Returns:
            PaginatedResponse containing items and optional next_token
        """
        return await self.fetch_page(limit=limit, next_token=next_token, **kwargs)

    async def get_all(self, limit_per_page: int = 25, max_records: int | None = None, **kwargs: Any) -> list[T]:
        """
        Fetch all records across all pages.

        Args:
            limit_per_page: Number of records per page (max 25)
            max_records: Maximum total records to fetch (None = all)
            **kwargs: Additional parameters to pass to fetch_page

        Returns:
            List of all records
        """
        all_records: list[T] = []
        next_token = None

        while True:
            # Calculate how many records to fetch this page
            if max_records is not None:
                remaining = max_records - len(all_records)
                if remaining <= 0:
                    break
                page_limit = min(limit_per_page, remaining)
            else:
                page_limit = limit_per_page

            # Fetch page
            page = await self.get_page(limit=page_limit, next_token=next_token, **kwargs)

            all_records.extend(page.records)

            # Check if we should continue
            if not page.has_more:
                break

            next_token = page.next_token

            # Check if we've hit the max
            if max_records is not None and len(all_records) >= max_records:
                break

        return all_records[:max_records] if max_records else all_records

    async def iterate(self, limit_per_page: int = 25, **kwargs: Any) -> AsyncIterator[T]:
        """
        Iterate over all records across all pages.

        This is memory-efficient for large datasets as it yields
        records one at a time rather than loading all into memory.

        Args:
            limit_per_page: Number of records per page (max 25)
            **kwargs: Additional parameters to pass to fetch_page

        Yields:
            Individual records
        """
        next_token = None

        while True:
            page = await self.get_page(limit=limit_per_page, next_token=next_token, **kwargs)

            for record in page.records:
                yield record

            if not page.has_more:
                break

            next_token = page.next_token

    async def iterate_pages(self, limit_per_page: int = 25, **kwargs: Any) -> AsyncIterator[PaginatedResponse[T]]:
        """
        Iterate over pages of results.

        Args:
            limit_per_page: Number of records per page (max 25)
            **kwargs: Additional parameters to pass to fetch_page

        Yields:
            Page responses
        """
        next_token = None

        while True:
            page = await self.get_page(limit=limit_per_page, next_token=next_token, **kwargs)

            yield page

            if not page.has_more:
                break

            next_token = page.next_token


def parse_pagination_params(params: dict[str, Any]) -> dict[str, Any]:
    """
    Parse and validate pagination parameters.

    Args:
        params: Dictionary of parameters

    Returns:
        Validated parameters

    Raises:
        ValueError: If parameters are invalid
    """
    validated = {}

    # Validate limit
    if "limit" in params:
        limit = params["limit"]
        if not isinstance(limit, int) or limit < 1 or limit > DEFAULT_PAGE_SIZE:
            raise ValueError("Limit must be an integer between 1 and 25")
        validated["limit"] = limit

    # Pass through other params
    for key in ["start", "end", "nextToken"]:
        if key in params:
            validated[key] = params[key]

    return validated
