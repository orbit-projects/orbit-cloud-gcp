# orbit-cloud-gcp

Lists Google Cloud resources from a project, folder, or organization with the asynchronous Cloud Asset Inventory client.

This is the `Cloud Asset Inventory `SearchAllResources` API` adapter for the provider-neutral [`orbit-cloud`](https://github.com/orbit-projects/orbit-cloud) capability. It performs **read-only inventory**. It never provisions, modifies, or deletes cloud resources.

**Status:** pre-alpha. Contract tests use fake SDK clients and need no cloud credentials. No hosted CI, live-provider, production, support, or release-readiness claim is implied.

## Install

```bash
python -m pip install orbit-cloud orbit-cloud-gcp
```

## Use

```python
from orbit_cloud import CloudInventoryQuery
from orbit_cloud_gcp import GCPCloudInventory

provider = GCPCloudInventory()
try:
    page = await provider.list_resources(
        CloudInventoryQuery(
        scope="projects/example-project",
        resource_types=("compute.googleapis.com/Instance",),
        locations=("us-central1-a",),
        page_size=100,
    )
    )
    for resource in page.resources:
        print(resource.resource_type, resource.resource_id)
finally:
    await provider.aclose()
```

The provider owns its async client and closes it during `aclose()`. Calls are bounded by finite request timeouts and a configurable concurrency limit. Cancellation propagates through the asynchronous client. `CloudInventoryPage.next_page_token` is opaque and provider-specific; use it only with the same scope, filters, and page size, and do not log it.

## Provider setup and limits

Enable the Cloud Asset Inventory API and grant the workload identity `cloudasset.assets.searchAllResources` on the requested project, folder, or organization. The adapter uses Google Application Default Credentials; no credential JSON is accepted in package configuration.

Cloud Asset Inventory only returns supported/searchable resource types and data visible to the identity. Inventory can be delayed by the provider. The adapter requests only resource name, type, display name, and location fields; it does not expose raw attributes, IAM policy documents, labels, or tags.

Resource identifiers and names may be sensitive. Orbit deliberately omits raw provider payloads. Do not log resource IDs, scopes, or continuation tokens unless your data handling policy permits it.

## SDK choice

`google-cloud-asset` provides an asynchronous GAPIC client. The adapter is network-I/O-bound; no separate Go/Rust runtime or SDK is included without a measured use case.

The Python adapter is the baseline implementation. Native language alternatives require contract conformance and representative evidence before they are recommended.

## Documentation and development

Read the [architecture](docs/architecture/overview.md), [operations](docs/operations/README.md), [security](docs/security/overview.md), and [development](docs/development/README.md) guides.

```bash
python -m pip install -e '.[dev]' build
pytest
ruff check src tests
ruff format --check src tests
mypy
python -m build
```

Live validation, when added, must be opt-in and use a dedicated non-production account, project, or subscription.

Licensed under Apache-2.0.
