## Microsoft Agent Framework – Purview Integration (Python)

`agent-framework-purview` adds Microsoft Purview (Microsoft Graph dataSecurityAndGovernance) policy evaluation to the Microsoft Agent Framework. It lets you enforce data security / governance policies on both the *prompt* (user input + conversation history) and the *model response* before they proceed further in your workflow.

> Status: **Preview**

### Key Features

- Middleware-based policy enforcement (agent-level and chat-client level)
- Blocks or allows content at both ingress (prompt) and egress (response)
- Works with any `Agent` / agent orchestration using the standard Agent Framework middleware pipeline
- Supports both synchronous `TokenCredential` and `AsyncTokenCredential` from `azure-identity`
- Configuration via `PurviewSettings` / `PurviewAppLocation`
- Built-in caching with configurable TTL and size limits for protection scopes in `PurviewSettings`
- Background processing for content activities and offline policy evaluation

### When to Use
Add Purview when you need to:

- **Prevent sensitive data leaks**: Inline blocking of sensitive content based on Data Loss Prevention (DLP) policies.
- **Enable governance**: Log AI interactions in Purview for Audit, Communication Compliance, Insider Risk Management, eDiscovery, and Data Lifecycle Management.
- Prevent sensitive or disallowed content from being sent to an LLM
- Prevent model output containing disallowed data from leaving the system
- Apply centrally managed policies without rewriting agent logic

---

## Prerequisites

- Microsoft Azure subscription with Microsoft Purview configured.
- Microsoft 365 subscription with an E5 license and pay-as-you-go billing setup.
  - For testing, you can use a Microsoft 365 Developer Program tenant. For more information, see [Join the Microsoft 365 Developer Program](https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program).

### Authentication

`PurviewClient` uses the `azure-identity` library for token acquisition. You can use any `TokenCredential` or `AsyncTokenCredential` implementation.

- **Entra registration**: Register your agent and add the required Microsoft Graph permissions (`dataSecurityAndGovernance`) to the Service Principal. For more information, see [Register an application in Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app) and [dataSecurityAndGovernance resource type](https://learn.microsoft.com/en-us/graph/api/resources/datasecurityandgovernance). You'll need the Microsoft Entra app ID in the next step.

- **Graph Permissions**:
- ProtectionScopes.Compute.All : [userProtectionScopeContainer](https://learn.microsoft.com/en-us/graph/api/userprotectionscopecontainer-compute)
- Content.Process.All : [processContent](https://learn.microsoft.com/en-us/graph/api/userdatasecurityandgovernance-processcontent)
- ContentActivity.Write : [contentActivity](https://learn.microsoft.com/en-us/graph/api/activitiescontainer-post-contentactivities)

- **Purview policies**: Configure Purview policies using the Microsoft Entra app ID to enable agent communications data to flow into Purview. For more information, see [Configure Microsoft Purview](https://learn.microsoft.com/purview/developer/configurepurview).

#### Scopes
`PurviewSettings.get_scopes()` derives the Graph scope list (currently `https://graph.microsoft.com/.default` style).

---

## Quick Start

```python
import asyncio
from agent_framework import Agent, Message, Role
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
from azure.identity import InteractiveBrowserCredential

async def main():
	client = OpenAIChatCompletionClient()  # uses environment for endpoint + deployment

	purview_middleware = PurviewPolicyMiddleware(
		credential=InteractiveBrowserCredential(),
		settings=PurviewSettings(app_name="My Sample App")
	)

	agent = Agent(
		client=client,
		instructions="You are a helpful assistant.",
		middleware=[purview_middleware]
	)

	response = await agent.run(Message("user", ["Summarize zero trust in one sentence."]))
	print(response)

asyncio.run(main())
```

If a policy violation is detected on the prompt, the middleware terminates the run and substitutes a system message: `"Prompt blocked by policy"`. If on the response, the result becomes `"Response blocked by policy"`.

If you attach other middleware as well, put the Purview middleware last — see [Middleware order matters](#middleware-order-matters).

---

## Configuration

### `PurviewSettings`

```python
PurviewSettings(
    app_name="My App",                         # Required: Display / logical name
    app_version=None,                          # Optional: Version string of the application
    tenant_id=None,                            # Optional: Tenant id (guid), used mainly for auth context
    purview_app_location=None,                 # Optional: PurviewAppLocation for scoping
    graph_base_uri="https://graph.microsoft.com/v1.0/",
    blocked_prompt_message="Prompt blocked by policy",      # Custom message for blocked prompts
    blocked_response_message="Response blocked by policy",  # Custom message for blocked responses
    ignore_exceptions=False,                   # If True, non-payment exceptions are logged but not thrown
    ignore_payment_required=False,             # If True, 402 payment required errors are logged but not thrown
    cache_ttl_seconds=14400,                   # Cache TTL in seconds (default 4 hours)
    max_cache_size_bytes=200 * 1024 * 1024     # Max cache size in bytes (default 200MB)
)
```

### Caching

The Purview integration includes built-in caching for protection scopes responses to improve performance and reduce API calls:

- **Default TTL**: 4 hours (14400 seconds)
- **Default Cache Size**: 200MB
- **Cache Provider**: `InMemoryCacheProvider` is used by default, but you can provide a custom implementation via the `CacheProvider` protocol
- **Cache Invalidation**: Cache is automatically invalidated when protection scope state is modified
- **Exception Caching**: 402 Payment Required errors are cached to avoid repeated failed API calls

You can customize caching behavior in `PurviewSettings`:

```python
from agent_framework.microsoft import PurviewSettings

settings = PurviewSettings(
    app_name="My App",
    cache_ttl_seconds=14400,           # 4 hours
    max_cache_size_bytes=200 * 1024 * 1024  # 200MB
)
```

Or provide your own cache provider:

```python
from typing import Any
from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings, CacheProvider
from azure.identity import DefaultAzureCredential

class MyCustomCache(CacheProvider):
    async def get(self, key: str) -> Any | None:
        # Your implementation
        pass

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        # Your implementation
        pass

    async def remove(self, key: str) -> None:
        # Your implementation
        pass

credential = DefaultAzureCredential()
settings = PurviewSettings(app_name="MyApp")

middleware = PurviewPolicyMiddleware(
    credential=credential,
    settings=settings,
    cache_provider=MyCustomCache()
)
```

To scope evaluation by location (application, URL, or domain):

```python
from agent_framework.microsoft import (
	PurviewAppLocation,
	PurviewLocationType,
	PurviewSettings,
)

settings = PurviewSettings(
	app_name="Contoso Support",
	purview_app_location=PurviewAppLocation(
		location_type=PurviewLocationType.APPLICATION,
		location_value="<app-client-id>"
	)
)
```

### Customizing Blocked Messages

By default, when Purview blocks a prompt or response, the middleware returns a generic system message. You can customize these messages by providing your own text in the `PurviewSettings`:

```python
from agent_framework.microsoft import PurviewSettings

settings = PurviewSettings(
	app_name="My App",
	blocked_prompt_message="Your request contains content that violates our policies. Please rephrase and try again.",
	blocked_response_message="The response was blocked due to policy restrictions. Please contact support if you need assistance."
)
```

### Exception Handling Controls

The Purview integration provides fine-grained control over exception handling to support graceful degradation scenarios:

```python
from agent_framework.microsoft import PurviewSettings

# Ignore all non-payment exceptions (continue execution even if policy check fails)
settings = PurviewSettings(
    app_name="My App",
    ignore_exceptions=True  # Log errors but don't throw
)

# Ignore only 402 Payment Required errors (useful for tenants without proper licensing)
settings = PurviewSettings(
    app_name="My App",
    ignore_payment_required=True  # Continue even without Purview Consumptive Billing Setup
)

# Both can be combined
settings = PurviewSettings(
    app_name="My App",
    ignore_exceptions=True,
    ignore_payment_required=True
)
```

### Selecting Agent vs Chat Middleware

Both middlewares apply the same policy logic, but they are handed different content, so
they do not evaluate the same thing. **Prefer the chat middleware for data loss
prevention**; use the agent middleware when a single check at the run boundary is what
you want.

| | Agent middleware | Chat middleware |
|---|---|---|
| Caller's input messages | evaluated | evaluated |
| Context provider output (for example retrieval results or memory) | not evaluated | evaluated |
| Conversation history replayed into the request | not evaluated | evaluated |
| A model's tool call, before the tool executes | not evaluated | evaluated |
| Tool results | evaluated at the end of the run | evaluated on the next request |
| Final response | evaluated | evaluated |
| A blocked response | replaced for the caller, but [kept in history](#blocked-content-and-conversation-history) | [replaced before the turn is stored](#blocked-content-and-conversation-history), unless history is written per service call |
| How often it evaluates | once per run | once per model request |

The agent middleware receives the messages passed to `Agent.run()`. Content added while
the run executes — context provider output, replayed history, and the tool calls and
results produced by the function calling loop — is assembled downstream of it, so it is
visible only in the final response, after any tool has already run.

The chat middleware sits below the function calling loop and receives the fully prepared
request on every model round trip. A tool call returned by the model is therefore
evaluated before that tool executes, and its result is evaluated on the following round
trip.

Use the agent middleware when you already have / want the full agent pipeline:

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
client = OpenAIChatCompletionClient()

agent = Agent(
	client=client,
	instructions="You are helpful.",
	middleware=[PurviewPolicyMiddleware(credential, PurviewSettings(app_name="My App"))]
)
```

Use the chat middleware when you attach directly to a chat client (e.g. minimal agent shell or custom orchestration):

```python
import os
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework.microsoft import PurviewChatPolicyMiddleware, PurviewSettings
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()

client = OpenAIChatCompletionClient(
	model=os.environ["AZURE_OPENAI_MODEL"],
	azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
	credential=credential,
	middleware=[
		PurviewChatPolicyMiddleware(credential, PurviewSettings(app_name="My App (Chat)"))
	],
)

agent = Agent(client=client, instructions="You are helpful.")
```

Both middlewares can be attached at the same time. The chat middleware then evaluates
each model round trip and the agent middleware evaluates the run boundary.

In either list, attach the Purview middleware last — see
[Middleware order matters](#middleware-order-matters).

---

## Middleware Lifecycle

1. **Before agent execution** (`prompt phase`): all `context.messages` are evaluated.
   - A valid user_id is required; if none can be resolved, the request fails rather than proceeding unevaluated
   - Protection scopes are retrieved (with caching)
   - Applicable scopes are checked to determine execution mode
   - In inline mode: content is evaluated immediately
   - In offline mode: evaluation is queued in background
2. **If blocked**: `context.result` is replaced with a system message and `context.terminate = True`.
3. **After successful agent execution** (`response phase`): the produced messages are evaluated using the same user_id from the prompt phase.
4. **If blocked**: result messages are replaced with a blocking notice.

The user identifier is discovered from `Message.additional_properties['user_id']` during the prompt phase and reused for the response phase, ensuring both evaluations map consistently to the same user. See [Fail-closed behaviour](#fail-closed-behaviour) for what happens when no user identifier can be resolved.

You can customize the blocking messages using the `blocked_prompt_message` and `blocked_response_message` fields in `PurviewSettings`. For more advanced scenarios, you can wrap the middleware or post-process `context.result` in later middleware.

### Middleware order matters

**Attach the Purview middleware last in the middleware list.**

```python
agent = Agent(
    ...,
    middleware=[logging_middleware, caching_middleware, purview_middleware],
    #                                                   ^ last
)
```

Middleware are free to replace the response, and those replacements are applied in
middleware order. Whichever middleware comes last gets the final say over what the caller
receives. So any middleware attached *after* Purview can return a response that Purview
never evaluated, and no error or warning is raised when this happens — the response is
simply delivered unevaluated.

Attaching Purview last also means it evaluates the response *after* other middleware have
finished changing it, so the content that was evaluated is the content the caller
receives.

The same applies to `PurviewChatPolicyMiddleware` in a chat client's middleware list.

### Blocked content and conversation history

Which middleware you use decides whether a blocked response can still be read back from
conversation history.

**Chat middleware** (`PurviewChatPolicyMiddleware`, in a chat client's middleware list) —
the response is evaluated and replaced during the model call, before an agent run stores
the turn, so the replacement is what becomes durable and the model's own content does not
reach the history provider.

**Agent middleware** (`PurviewPolicyMiddleware`, in an agent's middleware list) — an agent
run writes its messages to history as part of the run, and this middleware wraps the whole
run, so the turn has already been written by the time the response is evaluated. A blocked
response is replaced for the caller, but the original content can still be read back from
history on a later turn. Use the chat middleware where history must not retain blocked
content.

Both cover the history providers the agent run writes through. Neither covers code that
writes somewhere else of its own accord, such as a tool that saves its own output.

#### Not recommended: history written per service call

The chat middleware description above assumes history is written once per run, which is
the default. An agent configured with `require_per_service_call_history_persistence=True`
instead writes history as each model call returns.

That writer is added by the agent itself and placed *below* anything in your chat
middleware list, closer to the model. It therefore stores the model's own response before
the chat middleware evaluates it, and a blocked response can still be read back from
history on a later turn. No ordering of your own middleware can change this, because the
writer is always placed below them.

Avoid per-service-call history persistence where history must not retain blocked content.

#### Exception: history kept by the service

Both of the above cover history the framework stores. Some chat clients instead keep the
conversation on the service and return an id to continue from — for example a
Responses-style API run with `store=True`, which is the default for some clients.

In that mode the framework does not attach a local history provider of its own, and the
service records the prompt and the response as part of the model call, before the response
comes back to be evaluated. The service's copy is outside the framework's reach. The
session's continuation id also advances to that turn, so the next turn resumes from a
conversation that still contains the blocked content.

Purview still replaces what the caller receives. It cannot remove what the service kept.

If blocked content must not be retained, set `store` to `False` so the framework owns the
conversation, and attach a history provider:

```python
client = ChatClient(...)
client.chat_middleware = [PurviewChatPolicyMiddleware(credential, settings)]

agent = Agent(
    client=client,
    context_providers=[InMemoryHistoryProvider()],
    default_options={"store": False},
)
```

`store` can also be set per run, with `agent.run(..., options={"store": False})`.

---

## Exceptions

| Exception | Scenario |
|-----------|----------|
| `PurviewPaymentRequiredError` | 402 Payment Required - tenant lacks proper Purview licensing or consumptive billing setup |
| `PurviewAuthenticationError` | Token acquisition / validation issues |
| `PurviewRateLimitError` | 429 responses from service |
| `PurviewRequestError` | 4xx client errors (bad input, unauthorized, forbidden) |
| `PurviewServiceError` | 5xx or unexpected service errors |

### Exception Handling

All exceptions inherit from `PurviewServiceError`. You can catch specific exceptions or use the base class:

```python
from agent_framework.microsoft import (
    PurviewPaymentRequiredError,
    PurviewAuthenticationError,
    PurviewRateLimitError,
    PurviewRequestError,
    PurviewServiceError
)

try:
    # Your code here
    pass
except PurviewPaymentRequiredError as ex:
    # Handle licensing issues specifically
    print(f"Purview licensing required: {ex}")
except (PurviewAuthenticationError, PurviewRateLimitError, PurviewRequestError, PurviewServiceError) as ex:
    # Handle other errors
    print(f"Purview enforcement skipped: {ex}")
```

---

## Security Considerations

### Identity is a trusted input

Purview evaluates DLP policy **for a specific user**. The identity this integration resolves therefore
decides *which* policy is applied, and it is resolved in this order:

1. The `user_id` from the configured credential's token, when the credential resolves to a user.
2. The `user_id` argument passed to the processor.
3. `message.additional_properties["user_id"]`.
4. `message.author_name`, when it is a GUID.

Only source 1 is verified. Sources 2–4 are supplied by the hosting application, so **a host must not
populate them from data that has crossed a trust boundary**. If an end user, an upstream service or a
model response can influence `additional_properties["user_id"]` or `author_name`, that party can
select a different user's DLP policy — typically one with weaker rules — and evade enforcement. Where
identity must come from a request, derive it from a validated token on the server, never from the
request body. Prefer a user-delegated credential (source 1) whenever possible.

The `purview_app_location` in `PurviewSettings` is trusted in the same way: it selects which policy
locations apply and must be configured by the host, not by the caller.

### Fail-closed behaviour

Policy evaluation fails closed. If no user id can be resolved, or the tenant or app location cannot be
determined, the processor raises rather than letting content through unevaluated. Use
`ignore_exceptions` if you deliberately want availability over enforcement — but understand that it
disables enforcement for every error, not just transient ones.

### What is evaluated

Every content item on a message is submitted for evaluation, not just its text: binary/data content is
sent as Purview binary content, and function calls, function results and other structured content are
serialized to text. Only `usage` content is skipped, because it carries token counts rather than user
data.

Evaluation covers the response as it stands when the middleware runs. Because middleware can replace
the response afterwards, what is evaluated depends on where the middleware is attached — see
[Middleware order matters](#middleware-order-matters).

### Remote references are not dereferenced

Purview classifies the content it is handed; a reference to content is not the content.

Content that carries its own bytes is evaluated as bytes: a `data:` URI is decoded and the decoded bytes
are submitted as Purview binary content.

A *remote* reference is not. A `uri` content pointing at a remote location, a hosted file reference, or a
link nested inside a tool result is submitted as the reference itself, and the bytes it points at are
never fetched or evaluated. A host that needs those bytes evaluated must resolve them and pass the
resolved content through the middleware.

### Streaming responses

A streamed response is buffered in full and evaluated before any update is released, so it receives the
same evaluation as a non-streaming response. Content is therefore not delivered incrementally while
either middleware is attached: the first update is released only once the whole response has been
evaluated.

This uses an experimental core API, so attaching the middleware to a streaming call emits an
`ExperimentalWarning`.

A streamed response is evaluated once it has been assembled, at the same point a
non-streaming response is, so [Middleware order matters](#middleware-order-matters)
applies to streaming in exactly the same way.

---

## Notes
- **User Identification**: When the configured credential resolves to a user token, that token's `user_id` is used for per-user policy scoping. For app-token credentials, provide a `user_id` per request (e.g. in `Message(..., additional_properties={"user_id": "<guid>"})`). If no user_id can be provided or inferred, the request fails rather than proceeding unevaluated — see [Security Considerations](#security-considerations).
- **Blocking Messages**: Can be customized via `blocked_prompt_message` and `blocked_response_message` in `PurviewSettings`. By default, they are "Prompt blocked by policy" and "Response blocked by policy" respectively.
- **Middleware Order**: Attach the middleware last in the middleware list. Anything attached after it can return a response it never evaluated — see [Middleware order matters](#middleware-order-matters).
- **Streaming Responses**: Streamed responses are buffered and evaluated in full before any update is released, so content is not delivered incrementally while the middleware is attached — see [Streaming responses](#streaming-responses).
- **Blocked Content and History**: The chat middleware replaces a blocked response before the turn is stored; the agent middleware replaces it only for the caller, and history keeps the original. Per-service-call history persistence is not recommended with either — see [Blocked content and conversation history](#blocked-content-and-conversation-history).
- **Error Handling**: Use `ignore_exceptions` and `ignore_payment_required` settings for graceful degradation. When enabled, errors are logged but don't fail the request.
- **Caching**: Protection scopes responses and 402 errors are cached by default with a 4-hour TTL. Cache is automatically invalidated when protection scope state changes.
- **Cold-cache parallelization**: On a `ProtectionScopes` cache miss, scopes are refreshed in the background while `ProcessContent` runs in the foreground.
- **Background Processing**: Content Activities and offline Process Content requests are handled asynchronously using background tasks to avoid blocking the main execution flow.
