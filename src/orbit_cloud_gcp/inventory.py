# Copyright 2026-present Orbit Contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Async, read-only Google Cloud Asset Inventory adapter."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

from google.api_core import exceptions as google_errors
from google.api_core.retry_async import AsyncRetry
from google.cloud import asset_v1
from google.protobuf.field_mask_pb2 import FieldMask
from orbit_cloud import (
    CloudConfigurationError,
    CloudInventoryPage,
    CloudInventoryQuery,
    CloudOperationError,
    CloudResource,
)

from orbit_cloud_gcp.config import GCPCloudInventoryConfig

_SCOPE = re.compile(r"(?:projects/[A-Za-z0-9-]+|folders/[0-9]+|organizations/[0-9]+)\Z")


class _AssetClient(Protocol):
    async def search_all_resources(self, **kwargs: Any) -> Any:
        """Search Cloud Asset Inventory with a bounded query request."""

    async def close(self) -> None:
        """Close the asynchronous Cloud Asset Inventory client."""


class GCPCloudInventory:
    """List Google Cloud resources through Cloud Asset Inventory search."""

    def __init__(
        self,
        config: GCPCloudInventoryConfig | None = None,
        *,
        client_factory: Callable[[], _AssetClient] | None = None,
    ) -> None:
        self.config = config or GCPCloudInventoryConfig()
        self._client_factory = client_factory or asset_v1.AssetServiceAsyncClient
        self._client: _AssetClient | None = None
        self._client_lock = asyncio.Lock()
        self._condition = asyncio.Condition()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self._active = 0
        self._closing = False
        self._closed = False

    async def _get_client(self) -> _AssetClient:
        async with self._client_lock:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    @asynccontextmanager
    async def _use_client(self) -> AsyncIterator[_AssetClient]:
        async with self._condition:
            if self._closing or self._closed:
                raise CloudOperationError("closed", "Google Cloud inventory provider is closed.")
            self._active += 1
        try:
            async with self._semaphore:
                yield await self._get_client()
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify_all()

    async def list_resources(self, query: CloudInventoryQuery) -> CloudInventoryPage:
        """Search one Google Cloud Resource Manager scope and return one bounded page."""
        if _SCOPE.fullmatch(query.scope) is None:
            raise CloudConfigurationError(
                "scope must be projects/{id}, folders/{number}, or organizations/{number}."
            )
        expression = _build_location_query(query.locations)
        request = asset_v1.SearchAllResourcesRequest(
            scope=query.scope,
            asset_types=list(query.resource_types),
            query=expression,
            page_size=query.page_size,
            page_token=query.page_token or "",
            read_mask=FieldMask(paths=["name", "asset_type", "display_name", "location"]),
        )
        try:
            async with asyncio.timeout(self.config.request_timeout_seconds):
                async with self._use_client() as client:
                    pager = await client.search_all_resources(
                        request=request,
                        timeout=self.config.request_timeout_seconds,
                        retry=AsyncRetry(timeout=self.config.request_timeout_seconds),
                    )
                    response_page = None
                    async for _response_page in pager.pages:
                        response_page = _response_page
                        break
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise CloudOperationError(
                "timeout", "Google Cloud inventory request timed out.", retryable=True
            ) from None
        except google_errors.PermissionDenied:
            raise CloudOperationError(
                "permission-denied", "Google Cloud denied the inventory request."
            ) from None
        except google_errors.ResourceExhausted:
            raise CloudOperationError(
                "throttled", "Google Cloud limited the inventory request.", retryable=True
            ) from None
        except (google_errors.ServiceUnavailable, google_errors.DeadlineExceeded):
            raise CloudOperationError(
                "provider-unavailable",
                "Google Cloud inventory is temporarily unavailable.",
                retryable=True,
            ) from None
        except CloudOperationError:
            raise
        except google_errors.GoogleAPICallError:
            raise CloudOperationError(
                "provider-failure", "Google Cloud inventory request failed."
            ) from None
        except Exception:
            raise CloudOperationError(
                "provider-failure", "Google Cloud inventory request failed."
            ) from None

        if response_page is None:
            return CloudInventoryPage(resources=())
        try:
            resources = tuple(
                CloudResource(
                    provider="gcp",
                    resource_id=_required_string(asset, "name"),
                    resource_type=_required_string(asset, "asset_type"),
                    name=_optional_string(asset, "display_name"),
                    location=_optional_string(asset, "location"),
                )
                for asset in response_page.results
            )
            token = response_page.next_page_token or None
            return CloudInventoryPage(resources=resources, next_page_token=token)
        except (AttributeError, TypeError, ValueError):
            raise CloudOperationError(
                "invalid-response", "Google Cloud inventory returned invalid resource metadata."
            ) from None

    async def aclose(self) -> None:
        """Drain active searches and close the asynchronous Google API client."""
        async with self._condition:
            if self._closed:
                return
            if self._closing:
                await self._condition.wait_for(lambda: self._closed or not self._closing)
                if self._closed:
                    return
            self._closing = True
            try:
                await self._condition.wait_for(lambda: self._active == 0)
            except BaseException:
                self._closing = False
                self._condition.notify_all()
                raise
        try:
            if self._client is not None:
                await self._client.close()
        except asyncio.CancelledError:
            async with self._condition:
                self._closing = False
                self._condition.notify_all()
            raise
        except Exception:
            async with self._condition:
                self._closing = False
                self._condition.notify_all()
            raise CloudOperationError(
                "close-failed", "Google Cloud SDK client could not be closed."
            ) from None
        async with self._condition:
            self._closed = True
            self._closing = False
            self._condition.notify_all()


def _build_location_query(locations: tuple[str, ...]) -> str:
    if not locations:
        return ""
    return "location:(" + " OR ".join(locations) + ")"


def _required_string(asset: object, field: str) -> str:
    value = getattr(asset, field, None)
    if not isinstance(value, str) or not value:
        raise ValueError("invalid resource field")
    return value


def _optional_string(asset: object, field: str) -> str | None:
    value = getattr(asset, field, None)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("invalid resource field")
    return value


__all__ = ["GCPCloudInventory"]
