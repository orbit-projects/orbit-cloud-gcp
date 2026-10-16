# Architecture

`orbit-cloud-gcp` implements `orbit_cloud.CloudInventoryProvider` using the asynchronous Google
Cloud Asset Inventory client and `SearchAllResources`. It adapts the provider-neutral
[`orbit-cloud`](https://github.com/orbit-projects/orbit-cloud) query and result models.

```text
CloudInventoryQuery
  ├── scope: projects/{id}, folders/{number}, organizations/{number}
  ├── resource_types → asset_types
  ├── locations → provider location expression
  └── page_size/token → API pagination
        ↓
Cloud Asset Inventory SearchAllResources
        ↓
CloudInventoryPage with normalized name/type/display name/location
```

The adapter owns Application Default Credentials integration, API request and retry deadlines,
client lifecycle, query translation, pagination, and safe provider error mapping. It lazily creates
one async client, bounds concurrent requests, propagates cancellation, drains active searches on
`aclose()`, and then closes the client.

The API request mask intentionally selects only `name`, `asset_type`, `display_name`, and
`location`. Provider-specific asset attributes, labels, tags, and IAM policies are not returned.
Only supported searchable asset types and data visible to the caller are available. Indexing delay,
permission inheritance, and provider limits can affect completeness; the adapter does not claim
organization-wide or compliance-grade inventory.

No live Google Cloud service validation is claimed by the fake-client test suite.
