# Security

## Identity

Use Google Application Default Credentials and prefer workload identity or another managed
credential source. Do not place service-account key JSON, access tokens, or other secrets in
adapter configuration, query scopes, source control, or logs. Grant only
`cloudasset.assets.searchAllResources` at the narrowest scope required and verify inherited access
with the cloud administrator. This package does not create identities or inspect IAM policy.

## Inventory data

Resource names, project/folder/organization scope, type, location, and page tokens can reveal
account topology. The adapter requests a limited read mask and omits raw provider payloads, labels,
tags, and IAM policies. This reduces returned detail but does not make resource IDs or names public.
Restrict result access, avoid logging pages and opaque cursors, and apply your data classification
and retention rules.

The common models redact sensitive fields from normal representations, but explicit serialization,
application logs, traces, memory dumps, and SDK diagnostics may still expose them. Provider errors
are translated to generic categories; avoid recording raw Google SDK exception context.

## Network and API behavior

Use authenticated Google API transport with certificate verification and restrict egress according
to deployment policy. Inventory is limited to supported/searchable types and the caller's
permissions and may be delayed. Do not use missing inventory results as proof of nonexistence or as
a compliance decision.

## Vulnerability reporting

Report security issues using the repository's [private security process](../../SECURITY.md).
