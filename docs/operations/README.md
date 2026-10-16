# Operations

`GCPCloudInventory` queries Google Cloud Asset Inventory's `SearchAllResources` API. It accepts
project, folder, or organization scopes and only returns the fields requested in its read mask:
resource name, asset type, display name, and location. It does not fetch raw asset attributes,
labels, tags, or IAM policy documents.

## API setup and identity

Enable the Cloud Asset Inventory API and grant the runtime identity
`cloudasset.assets.searchAllResources` for the requested scope. The adapter resolves identity via
Google Application Default Credentials and accepts no service-account JSON or static token in its
configuration. Prefer workload identity in deployed environments; do not commit credential files.
Verify effective permissions at the exact project, folder, or organization level used by the
application.

## Query and pagination

The common resource type filters map to `asset_types`; locations map to a Cloud Asset Inventory
location expression. Pass the returned page token only with the same scope, resource types,
locations, and page size. The cursor is opaque, provider-specific, and may expire. Do not log or
rewrite it. Cloud Asset Inventory returns only supported and searchable asset types visible to the
identity; indexing delay and scope permissions can make results incomplete.

## Timeouts and lifecycle

The async client is created lazily and shared across requests. `max_concurrency` limits operations
inside the client; `request_timeout_seconds` is enforced both around the overall operation and in
the Google API retry budget. Retry uses Google's transient-error predicate, exponential delays with
a 1-second initial interval, a 2x multiplier, and a 60-second maximum interval. Google API Core
randomizes each delay from zero up to the current exponential interval; the request timeout caps the
entire retry sequence. Caller cancellation propagates. `aclose()` stops new searches, waits for
active operations to drain, then closes the client; call it during application shutdown. After close
failure or cancellation the provider remains unavailable and retains its client context for a later
retry. Set the application's shutdown deadline to account for outstanding API calls.

## Operational validation

Use a dedicated non-production project to check API enablement, inherited IAM, supported resource
types, location filters, pagination, indexing delay, quotas, retry deadlines, cancellation,
credential refresh, and shutdown with active calls. Fake-client tests do not establish live API
coverage or complete asset inventory.
