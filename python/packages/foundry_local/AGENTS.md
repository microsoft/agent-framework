# Foundry Local Package (agent-framework-foundry-local)

Integration with Microsoft Foundry Local for local model inference.

Uses `foundry_local_sdk` (SDK 2.1+, below 3.0) on Python 3.11-3.14. Clients share
`FoundryLocalManager.instance` and use its built-in web service with the existing
OpenAI transport. Model lifecycle operations live on catalog model objects.
The adapter defaults to the public catalog and `/v1`. Use `catalog_type="local"`
or `foundry_local_sdk.catalog.CatalogType.LOCAL` for SDK-registered BYOM models:
both lookup and HTTP inference use the local catalog and `/catalogs/local/v1`.
Catalogs never fall back to each other; per-request model overrides remain in the
selected catalog. The application owns local-model registration and assets.

`FoundryLocalClient` exposes the SDK `Configuration` for initial manager setup,
download progress/cancellation controls, and exact device/variant selection.
Skipping preparation requires the selected variant to be loaded before inference.
Clients own their HTTP connections, not the shared native manager.
Failed setup stops a web service it started on an existing manager without closing
that manager or stopping a previously running service.

`FoundryLocalChatOptions` adds `top_k`, `do_sample`, and `early_stopping`.
Request preparation maps these to string-valued native decoder metadata and
unwraps OpenAI's JSON-schema envelope for the HTTP service. Explicit decoder
controls override conflicting metadata without mutating caller options.
Required tool calls use tool grammar before structured-output grammar; the standard
function loop applies the structured format to the final reply.

## Main Classes

- **`FoundryLocalClient`** - Chat client for Foundry Local models
- **`FoundryLocalChatOptions`** - Options TypedDict for Foundry Local parameters
- **`FoundryLocalSettings`** - Settings TypedDict for model configuration

## Usage

```python
from agent_framework import Message
from agent_framework.foundry import FoundryLocalClient

client = FoundryLocalClient(model="your-local-model")
response = await client.get_response([Message(role="user", contents=["Hello"])])
```

## Import Path

```python
from agent_framework.foundry import FoundryLocalClient
```
