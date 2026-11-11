# Custom session storage (Responses protocol)

This sample implements custom **MAF agent-session persistence**, including user
and sandbox isolation and optimistic concurrency. The outer Responses store
remains host-managed. Pending tool approvals are part of the saved
`AgentSession`, so the store needs only `get`/`set`/`delete`. This is not a
workflow example.

## Identity and storage keys

For hosted requests, `FoundryRequestScope.from_context(config, platform_context)`
requires the platform-configured sandbox ID and trusted user/call IDs. A request
whose `agent_session_id` differs from `FOUNDRY_AGENT_SESSION_ID` fails closed.
The provider resolves this scope **before** creating a backend client.

The Cosmos partition key is `/scope_key`: the same bounded, framed hash of
**trusted user + sandbox** used by the default hosted store. Each item ID hashes
the host's response/conversation lookup key inside that partition. Changing the
call ID does not change the namespace. Changing either the user or the sandbox
does. No raw platform IDs or tokens are written into document keys or logs.

The storage key is not `AgentSession.session_id`. A host may save one MAF
snapshot under a response ID and a conversation ID; each key has its own ETag.
The snapshot's inner `session_id` is preserved when loading. Keys are not built
from caller model options or an inner model-service session ID.

Cosmos items have a 2 MB service limit. Before a create or replacement, this
sample checks the complete compact, escaped-JSON snapshot against a conservative
**2,000,000-byte budget**, leaving room for service metadata. Oversized state
fails explicitly before a backend write; a service 413 also becomes an
actionable size error. Reduce the state or start a new conversation instead of
retrying an oversized snapshot. This per-item check is not a retention policy
or aggregate storage quota; those remain tracked in
microsoft/agent-framework#8901.

**Existing unscoped data is not migrated.** The old `/user_id` container layout
and connection-string configuration are intentionally replaced. Use a new
container partitioned by `/scope_key` and start fresh conversations; do not fall
back to user-only documents or silently copy old snapshots.

## Conditional writes and deletes

Each request receives a new store view with its own per-key ETags; only the
Cosmos client/pool is shared. A loaded snapshot is replaced with
`MatchConditions.IfNotModified` and the **loaded ETag**. A missing or never-loaded
key is **create-only**, never an unconditional upsert. Successful writes refresh
that key's ETag without changing another key's token.

HTTP 409/412 conflicts raise an explicit error. Reload and reconsider the turn;
do not retry the stale write as an unconditional update. A delete also uses the
loaded ETag (loading first if necessary), so it cannot remove another request's
newer snapshot. An absent delete is idempotent. Missing ETags and mismatched
stored scope fail closed; other Cosmos failures propagate without a local
fallback.

For local runs, each `CustomSessionStoreProvider` owns its in-memory snapshots.
Only the stores from that provider in **one process and event loop** coordinate
their conditional writes. Separate provider instances do not share snapshots,
even in the same process. Use one provider and one worker for local development.
Snapshots are lost when the provider and its stores are discarded or the
process exits. They are **single-user development only**: local headers and
session selectors are not a trusted platform authentication boundary. Explicit
local sessions have separate namespaces.

## Cosmos prerequisites

Create the database/container separately and set:

```text
AZURE_COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
COSMOS_DATABASE_NAME=<database>
COSMOS_CONTAINER_NAME=<container-with-partition-key-/scope_key>
```

The hosted provider uses `azure.identity.aio.ManagedIdentityCredential`, with
the platform-provided `FOUNDRY_AGENT_INSTANCE_CLIENT_ID` when present. Grant that
managed identity **Cosmos DB Built-in Data Contributor** at the narrowest
applicable container scope using Cosmos **data-plane RBAC**, not an account
management role. No Cosmos account key, connection string, password or raw
credential is deployed. The container is not provisioned by `main.py`.

The model also requires access to the configured Foundry project. Local model
calls use `AzureCliCredential` (`az login`); they do not require Cosmos.

## Run

Set `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`, then follow
the [parent local-host instructions](../../README.md#running-the-agent-host-locally).

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Hi"}'
```

The host uses `history_source="host_managed"` and a request-owned agent/client
factory. It reconstructs history from the outer transcript rather than retaining
it on Python instances or enabling inner model storage. Outer `store=false`
does not access/write this custom session store.

For hosted use, configure the endpoint/database/container in the manifest and
follow the [parent deployment instructions](../../README.md#deploying-the-agent-to-foundry).
The provider closes the Cosmos client and its own credential at shutdown.
After a request client enters, its context closes its own transports and
credential on exit, including cancellation. If a request ends before client
entry, those allocations may not be cleaned up.

Live Cosmos access and deployment need separately approved resources and
permissions.
