# Get Started with Microsoft Agent Framework Foundry Local

Requires Python 3.11 or newer and Foundry Local SDK 2.1 or newer (below 3.0).
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

All clients in a process share the SDK manager and web service. To customize cache
directories or other SDK settings, pass `configuration=Configuration(app_name="my-app", ...)`
when creating the first client, or initialize `FoundryLocalManager` yourself before
creating clients. Register accelerated execution providers through the SDK manager
before selecting GPU/NPU variants. A `device` value of `"CPU"`, `"GPU"`, or `"NPU"`
selects a matching variant; an exact model ID is never replaced by a sibling variant.

`bootstrap=False` requires an already initialized SDK manager with a running web
service in the same process. `prepare_model=False` skips native download/load during
construction. `timeout` applies to HTTP inference requests, not native preparation.

Clients do not close or unload the shared manager. After all clients finish, close
their HTTP clients and call `client.manager.close()` once at application shutdown.
If construction fails after creating a new manager, that manager is closed; an
existing application's manager is left untouched.

## Migration from SDK 0.5.1

This is a breaking SDK migration: Python 3.10 and SDK 0.5.1/1.x are no longer supported.
Update SDK imports from `foundry_local` to `foundry_local_sdk`. Use
`client.manager.catalog.list_models()` instead of `list_catalog_models()`, inspect
metadata through `model.info`, and call `download()`/`load()` on catalog model objects
instead of `download_model()`/`load_model()` on the manager. The SDK now runs in-process;
a separately started CLI service does not satisfy `bootstrap=False`.

## Foundry Local Sample

See the [Foundry Local provider sample](../../samples/02-agents/providers/foundry/foundry_local_agent.py) for a runnable example.
