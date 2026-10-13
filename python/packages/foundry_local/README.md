# Get Started with Microsoft Agent Framework Foundry Local

Requires Python 3.11-3.14 and Foundry Local SDK 2.1 or newer (below 3.0).
Install the integration:

```bash
pip install agent-framework-foundry-local --pre
```

and see the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.

## Usage

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryLocalClient

client = FoundryLocalClient(model="phi-4-mini")
agent = Agent(client=client, instructions="You are a helpful assistant.")
response = await agent.run("Why is the sky blue?")
print(response.text)
```

The client initializes the Foundry Local SDK singleton, prepares the selected model,
and starts its built-in OpenAI-compatible HTTP service. Streaming, middleware, and
function invocation continue to use Agent Framework's OpenAI transport.

All clients in a process share the SDK manager and web service. Concurrent client
construction is serialized through model preparation and failed-setup cleanup.
To customize cache directories or other SDK settings, pass
`configuration=Configuration(app_name="my-app", ...)`
when creating the first client, or initialize `FoundryLocalManager` yourself before
creating clients. Register accelerated execution providers through the SDK manager
before selecting GPU/NPU variants. A `device` value of `"CPU"`, `"GPU"`, or `"NPU"`
selects a matching variant; an exact model ID is never replaced by a sibling variant.

`bootstrap=False` requires an already initialized SDK manager with a running web
service in the same process. `prepare_model=False` skips native download/load during
construction; the exact selected variant must already be loaded or be prepared
manually before inference. The HTTP service does not load it automatically.
`timeout` applies to HTTP inference requests, not native preparation.

`download_progress_callback` receives download percentages from 0 to 100, and
`download_cancel_event` accepts a `threading.Event` to cancel the download.
Both apply only when `prepare_model=True`. They do not cancel model loading or
inference; asynchronous request cancellation uses the normal Agent Framework API.

Clients do not close or unload the shared manager. After all clients finish, close
their HTTP clients and call `client.manager.close()` once at application shutdown.
If construction fails after creating a new manager, that manager is closed; an
existing application's manager is not closed. If failed construction started
its web service, that service is stopped; a previously running service is left running.

## Chat Options

`FoundryLocalChatOptions` includes the standard generation settings and native
`top_k`, `do_sample`, and `early_stopping` controls. The client encodes these three
controls as the HTTP service's string-valued decoder metadata, preserving zero
and `False` values. Explicit controls take precedence over conflicting values in
`metadata` or `extra_body["metadata"]`. Other native settings can be supplied
through these dictionaries.

Pydantic response models and JSON schemas use the native HTTP service's bare-schema
format automatically. JSON-object mode constrains output to an object; it does
not guarantee particular fields or values. Supported settings and structured
output capabilities depend on the model and runtime. Backend errors remain
visible as `ChatClientException`.

```python
from agent_framework import Message
from agent_framework.foundry import FoundryLocalChatOptions, FoundryLocalClient
from pydantic import BaseModel


class Answer(BaseModel):
    answer: int


client = FoundryLocalClient(model="phi-4-mini")
options: FoundryLocalChatOptions[Answer] = {
    "response_format": Answer,
    "max_tokens": 128,
    "temperature": 0.0,
    "top_k": 1,
    "do_sample": False,
}
response = await client.get_response(
    [Message(role="user", contents=["What is 2 + 2?"])],
    options=options,
)
assert isinstance(response.value, Answer)
print(response.value.answer)
```

Agent sessions, middleware, streaming, and automatic tool execution retain their
standard Agent Framework APIs. A per-request `model` option overrides inference
targeting only: that public-catalog variant must also be loaded in the shared manager.
When a tool is required (including a named tool), the request uses the native tool
grammar first, then applies the requested structured format to the final reply
after automatic tool execution. With automatic execution disabled, the caller
must handle the returned function call before requesting a structured final reply.

## Scope

This adapter targets the SDK's public model catalog and HTTP chat service.
BYOM/local-catalog model selection is intentionally not exposed by this adapter.
SDK 2.1 supports registered local models through `/catalogs/local/v1`, but this
adapter uses the public-catalog `/v1` route. Native-session-only features,
audio transcription, and embeddings are outside this chat integration.

Image content follows the OpenAI transport's serialization, but a successful HTTP
request or the presence of vision assets does not establish that a particular
model/runtime consumes those images. Verify multimodal behavior for the selected
configuration before relying on it.

## Migration from SDK 0.5.1

This is a breaking SDK migration: Python 3.10 and SDK 0.5.1/1.x are no longer supported.
Python 3.15 is excluded because SDK 2.1 pins ONNX Runtime 1.30.0, which does not yet
publish Python 3.15 wheels.
Update SDK imports from `foundry_local` to `foundry_local_sdk`. Use
`client.manager.catalog.list_models()` instead of `list_catalog_models()`, inspect
metadata through `model.info`, and call `download()`/`load()` on catalog model objects
instead of `download_model()`/`load_model()` on the manager. The SDK now runs in-process;
a separately started CLI service does not satisfy `bootstrap=False`.

## Foundry Local Sample

See the [Foundry Local provider sample](../../samples/02-agents/providers/foundry/foundry_local_agent.py) for a runnable example.
