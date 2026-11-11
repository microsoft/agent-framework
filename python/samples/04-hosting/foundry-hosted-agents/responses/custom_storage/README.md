# Custom session storage (Responses protocol)

This sample implements custom **MAF agent-session persistence**, including user
and sandbox isolation and optimistic concurrency. The outer Responses store
remains host-managed. The same custom store also holds the host's agent
approval state, so it implements revision-based conditional writes (see
[Approval state](#approval-state-and-revisioned-writes)). This is not a
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

## Approval state and revisioned writes

The host keeps agent tool-approval state in the configured session store, not
in a separate approval store. Each tool-approval request needs a single atomic
claim. A custom store that holds approval state must therefore add two async
methods next to `get`/`set`/`delete`:

```python
async def get_with_revision(self, session_id: str) -> tuple[AgentSession | None, str | None]: ...
async def compare_and_set(
    self, session_id: str, session: AgentSession, *, expected_revision: str | None
) -> str: ...
```

The host detects these methods structurally. Do not import or subclass a
private hosting type. The sample stores follow these rules:

- `get_with_revision` returns an independent snapshot and an opaque, non-empty
  revision for that exact stored version. An absent key returns
  `(None, None)`. Revision reads do not change the per-request ETags that
  `get`/`set` use.
- `expected_revision=None` is an atomic **create-only** write. A revision means
  an update only when the stored version still matches. A conflict raises
  `RuntimeError`. The store never falls back to an upsert or retries the write
  on its own. On success it returns the new revision.
- Keys are opaque strings. They can differ from `AgentSession.session_id` and
  can contain characters such as `/`. Cosmos item IDs hash the key.
- Cosmos uses `create_item` and `replace_item` with the ETag and
  `MatchConditions.IfNotModified`. The service enforces both conditions.
  A write result without an ETag fails.
- A write that fails or is cancelled may still have been committed. Reload the
  state before you decide what to do next. Do not assume that the write did
  not happen.

The local store implements the same methods for development. Its conditional
write is atomic only among stores from the same provider in one event loop.
Use a store with server-side conditional writes, such as Cosmos, when separate
providers, workers, or processes can serve the same conversation.

Without these methods, the host can still use the store for ordinary session
history. A non-hosted request that needs approval state fails with a
`RuntimeError` that names the missing methods.

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
The provider closes the Cosmos client and its own credential at shutdown;
request clients are closed after their request, including failed tool entry and
cancellation.

Live Cosmos access and deployment need separately approved resources and
permissions.
