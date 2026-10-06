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
"""Google Cloud query translation, safe errors, and resource lifecycle tests."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import PermissionDenied, ResourceExhausted
from orbit_cloud import CloudInventoryQuery, CloudOperationError

from orbit_cloud_gcp import GCPCloudInventory


class FakePager:
    def __init__(self, response: Any) -> None:
        self.response = response

    @property
    def pages(self) -> Any:
        async def iterate() -> Any:
            yield self.response

        return iterate()


class FakeClient:
    def __init__(self) -> None:
        self.request: Any = None
        self.response = SimpleNamespace(
            results=[
                SimpleNamespace(
                    name="//compute.googleapis.com/projects/demo/zones/us-central1-a/instances/web",
                    asset_type="compute.googleapis.com/Instance",
                    display_name="web",
                    location="us-central1-a",
                )
            ],
            next_page_token="opaque-google-token",
        )
        self.failure: Exception | None = None
        self.closed = False

    async def search_all_resources(self, **kwargs: Any) -> FakePager:
        self.request = kwargs
        if self.failure is not None:
            raise self.failure
        return FakePager(self.response)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_inventory_maps_query_and_returns_bounded_resource_page() -> None:
    client = FakeClient()
    provider = GCPCloudInventory(client_factory=lambda: client)

    page = await provider.list_resources(
        CloudInventoryQuery(
            scope="projects/demo",
            resource_types=("compute.googleapis.com/Instance",),
            locations=("us-central1-a", "us-east1-b"),
            page_size=25,
            page_token="prior-token",
        )
    )

    request = client.request["request"]
    assert request.scope == "projects/demo"
    assert request.asset_types == ["compute.googleapis.com/Instance"]
    assert request.query == "location:(us-central1-a OR us-east1-b)"
    assert request.page_size == 25
    assert request.page_token == "prior-token"
    assert "additional_attributes" not in request.read_mask.paths
    assert page.resources[0].provider == "gcp"
    assert page.resources[0].name == "web"
    assert page.next_page_token == "opaque-google-token"
    assert "opaque-google-token" not in repr(page)
    await provider.aclose()
    assert client.closed


@pytest.mark.asyncio
async def test_rejects_invalid_scope_before_sdk_call() -> None:
    client = FakeClient()
    provider = GCPCloudInventory(client_factory=lambda: client)

    with pytest.raises(ValueError, match="scope must be"):
        await provider.list_resources(CloudInventoryQuery(scope="projects/demo OR *"))

    assert client.request is None
    await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "code", "retryable"),
    [
        (PermissionDenied("secret provider detail"), "permission-denied", False),
        (ResourceExhausted("secret provider detail"), "throttled", True),
    ],
)
async def test_provider_errors_are_sanitized(
    failure: Exception, code: str, retryable: bool
) -> None:
    client = FakeClient()
    client.failure = failure
    provider = GCPCloudInventory(client_factory=lambda: client)

    with pytest.raises(CloudOperationError) as caught:
        await provider.list_resources(CloudInventoryQuery(scope="organizations/123"))

    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert "secret provider detail" not in str(caught.value)
    await provider.aclose()


@pytest.mark.asyncio
async def test_cancel_propagates_and_close_is_idempotent() -> None:
    started = asyncio.Event()

    class BlockingClient(FakeClient):
        async def search_all_resources(self, **kwargs: Any) -> FakePager:
            self.request = kwargs
            started.set()
            await asyncio.Event().wait()
            return FakePager(self.response)

    client = BlockingClient()
    provider = GCPCloudInventory(client_factory=lambda: client)
    task = asyncio.create_task(provider.list_resources(CloudInventoryQuery(scope="folders/456")))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await provider.aclose()
    await provider.aclose()
    assert client.closed
