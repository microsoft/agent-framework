## Microsoft Agent Framework – Purview Integration (Python)

`agent-framework-purview` adds Microsoft Purview (Microsoft Graph dataSecurityAndGovernance) policy evaluation to the Microsoft Agent Framework. It lets you enforce data security / governance policies on both the *prompt* (user input + conversation history) and the *model response* before they proceed further in your workflow.

> Status: **Preview**

### Key Features

- Middleware-based policy enforcement (agent-level and chat-client level)
- Blocks or allows content at both ingress (prompt) and egress (response)
- Works with any `ChatAgent` / agent orchestration using the standard Agent Framework middleware pipeline
- Supports both synchronous `TokenCredential` and `AsyncTokenCredential` from `azure-identity`
- Simple, typed configuration via `PurviewSettings` / `PurviewAppLocation`
- Two middleware types:
	- `PurviewPolicyMiddleware` (Agent pipeline)
	- `PurviewChatPolicyMiddleware` (Chat client middleware list)

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
from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
from azure.identity import InteractiveBrowserCredential

async def main():
	chat_client = AzureOpenAIChatClient()  # uses environment for endpoint + deployment

	purview_middleware = PurviewPolicyMiddleware(
		credential=InteractiveBrowserCredential(),
		settings=PurviewSettings(appName="My Sample App")
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
    tenant_id=None,                    # Optional – used mainly for auth context
    purview_app_location=None,         # Optional PurviewAppLocation for scoping
    graph_base_uri="https://graph.microsoft.com/v1.0/",
    process_inline=False               # Reserved for future inline processing optimizations
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
	appName="Contoso Support",
	purviewAppLocation=PurviewAppLocation(
		location_type=PurviewLocationType.APPLICATION,
		location_value="<app-client-id>"
	)
)
```

### Selecting Agent vs Chat Middleware

Use the agent middleware when you already have / want the full agent pipeline:

```python
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.microsoft import PurviewPolicyMiddleware, PurviewSettings
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()
client = AzureOpenAIChatClient()

agent = ChatAgent(
	chat_client=client,
	instructions="You are helpful.",
	middleware=[PurviewPolicyMiddleware(credential, PurviewSettings(appName="My App"))]
)
```

Use the chat middleware when you attach directly to a chat client (e.g. minimal agent shell or custom orchestration):

```python
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.microsoft import PurviewChatPolicyMiddleware, PurviewSettings
from azure.identity import DefaultAzureCredential

credential = DefaultAzureCredential()

chat_client = AzureOpenAIChatClient(
	deployment_name=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
	endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
	credential=credential,
	middleware=[
		PurviewChatPolicyMiddleware(credential, PurviewSettings(appName="My App (Chat)"))
	],
)

agent = ChatAgent(chat_client=chat_client, instructions="You are helpful.")
```

The policy logic is identical; the difference is only the hook point in the pipeline.

---

## Middleware Lifecycle

1. Before agent execution (`prompt phase`): all `context.messages` are evaluated.
2. If blocked: `context.result` is replaced with a system message and `context.terminate = True`.
3. After successful agent execution (`response phase`): the produced messages are evaluated.
4. If blocked: result messages are replaced with a blocking notice.

When a user identifier is discovered (e.g. in `ChatMessage.additional_properties['user_id']`) during the prompt phase it is reused for the response phase so both evaluations map consistently to the same user.

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
from agent_framework.microsoft import (
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

## Notes
- Provide a `user_id` per request (e.g. in `ChatMessage(..., additional_properties={"user_id": "<guid>"})`) when possible for per-user policy scoping; otherwise supply a default via settings or environment.
- Blocking messages are currently static ("Prompt blocked by policy" / "Response blocked by policy"). 
- Streaming responses: post-response policy evaluation presently applies only to non-streaming chat responses.
- Errors during policy checks are logged and do not fail the run; they degrade gracefully.


