## Microsoft Agent Framework – Purview Integration (Python)

`agent-framework-purview` adds Microsoft Purview (Microsoft Graph dataSecurityAndGovernance) policy evaluation to the Microsoft Agent Framework. It lets you enforce data security / governance policies on both the *prompt* (user input + conversation history) and the *model response* before they proceed further in your workflow.

> Status: **Preview**

### Key Features

- Middleware-based policy enforcement
- Blocks or allows content at both ingress (prompt) and egress (response)
- Works with any `ChatAgent` / agent orchestration using the standard Agent Framework middleware pipeline
- Supports both synchronous `TokenCredential` and `AsyncTokenCredential` from `azure-identity`
- Simple, typed configuration via `PurviewSettings` / `PurviewAppLocation`

### When to Use
Add Purview when you need to:

- Prevent sensitive or disallowed content from being sent to an LLM
- Prevent model output containing disallowed data from leaving the system
- Apply centrally managed policies without rewriting agent logic

---

## Quick Start

```python
import asyncio
from agent_framework import ChatAgent, ChatMessage, Role
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_purview import PurviewPolicyMiddleware, PurviewSettings
from azure.identity import InteractiveBrowserCredential

async def main():
	chat_client = AzureOpenAIChatClient()  # uses environment for endpoint + deployment

	purview_middleware = PurviewPolicyMiddleware(
		credential=InteractiveBrowserCredential(),
		settings=PurviewSettings(appName="My Sample App", defaultUserId="<user-guid>")
	)

	agent = ChatAgent(
		chat_client=chat_client,
		instructions="You are a helpful assistant.",
		middleware=[purview_middleware]
	)

	response = await agent.run(ChatMessage(role=Role.USER, text="Summarize zero trust in one sentence."))
	print(response)

asyncio.run(main())
```

If a policy violation is detected on the prompt, the middleware terminates the run and substitutes a system message: `"Prompt blocked by policy"`. If on the response, the result becomes `"Response blocked by policy"`.

---

## Authentication

`PurviewClient` uses the `azure-identity` library for token acquisition. You can use any `TokenCredential` or `AsyncTokenCredential` implementation.

The APIs require the following Graph Permissions:
- ProtectionScopes.Compute.All : (userProtectionScopeContainer)[https://learn.microsoft.com/en-us/graph/api/userprotectionscopecontainer-compute]
- Content.Process.All : (processContent)[https://learn.microsoft.com/en-us/graph/api/userdatasecurityandgovernance-processcontent]
- ContentActivity.Write : (contentActivity)[https://learn.microsoft.com/en-us/graph/api/activitiescontainer-post-contentactivities]

### Scopes
`PurviewSettings.get_scopes()` derives the Graph scope list (currently `https://graph.microsoft.com/.default` style).

---

## Configuration

### `PurviewSettings`

```python
PurviewSettings(
    app_name="My App",                # Display / logical name
    default_user_id="<guid>",         # Fallback user id if not derivable from messages
    tenant_id=None,                    # Optional – used mainly for auth context
    purview_app_location=None,         # Optional PurviewAppLocation for scoping
    graph_base_uri="https://graph.microsoft.com/v1.0/",
    process_inline=False               # Reserved for future inline processing optimizations
)
```

To scope evaluation by location (application, URL, or domain):

```python
from agent_framework_purview import (
	PurviewAppLocation,
	PurviewLocationType,
	PurviewSettings,
)

settings = PurviewSettings(
	appName="Contoso Support",
	purviewAppLocation=PurviewAppLocation(
		location_type=PurviewLocationType.APPLICATION,
		location_value="<app-client-id>")
)
```

---

## Middleware Lifecycle

1. Before agent execution (`prompt phase`): all `context.messages` are evaluated.
2. If blocked: `context.result` is replaced with a system message and `context.terminate = True`.
3. After successful agent execution (`response phase`): the produced messages are evaluated.
4. If blocked: result messages are replaced with a blocking notice.

You can customize your blocking messages by wrapping the middleware or post-processing `context.result` in later middleware.

---

## Exceptions

| Exception | Scenario |
|-----------|----------|
| `PurviewAuthenticationError` | Token acquisition / validation issues |
| `PurviewRateLimitError` | 429 responses from service |
| `PurviewRequestError` | 4xx client errors (bad input, unauthorized, forbidden) |
| `PurviewServiceError` | 5xx or unexpected service errors |

Catch broadly if you want unified fallback:

```python
from agent_framework_purview import (
	PurviewAuthenticationError, PurviewRateLimitError,
	PurviewRequestError, PurviewServiceError
)

try:
	...
except (PurviewAuthenticationError, PurviewRateLimitError, PurviewRequestError, PurviewServiceError) as ex:
	# Log / degrade gracefully
	print(f"Purview enforcement skipped: {ex}")
```

---

