## Microsoft Agent Framework – Purview Integration (Python)

`agent-framework-purview` adds Microsoft Purview (Microsoft Graph dataSecurityAndGovernance) policy evaluation to the Microsoft Agent Framework. It lets you enforce data security / governance policies on both the *prompt* (user input + conversation history) and the *model response* before they proceed further in your workflow.

> Status: **Preview**

### Key Features

- Middleware-based policy enforcement (no wrapper ceremony)
- Blocks or allows content at both ingress (prompt) and egress (response)
- Works with any `ChatAgent` / agent orchestration using the standard Agent Framework middleware pipeline
- Async-safe – evaluates policies without blocking the event loop
- Supports both synchronous `TokenCredential` and `AsyncTokenCredential` from `azure-identity`
- Simple, typed configuration via `PurviewSettings` / `PurviewAppLocation`
- Helpful exception types: auth, rate limit, request, and service errors

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

## Configuration & Authentication

Environment variables commonly used (set via shell, `.env`, or CI secrets):

| Variable | Required | Purpose |
|----------|----------|---------|
| `AZURE_OPENAI_ENDPOINT` | Yes (for Azure OpenAI chat client) | Endpoint for Azure OpenAI deployment |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Optional | Model deployment name (falls back to library defaults) |
| `PURVIEW_CLIENT_APP_ID` | Yes* | Application (client) ID used for Purview auth (Interactive or Certificate) |
| `PURVIEW_USE_CERT_AUTH` | Optional (`true`/`false`) | Switch between certificate and interactive browser auth |
| `PURVIEW_TENANT_ID` | Yes (certificate mode) | Tenant ID for certificate auth |
| `PURVIEW_CERT_PATH` | Yes (certificate mode) | Path to .pfx file |
| `PURVIEW_CERT_PASSWORD` | Optional | Password if the certificate is encrypted |

*If omitted in some samples a default may be used for demonstration only – always supply your own in production.

### Choosing a Credential

Supported (explicit) credential types for Purview integration:

- `InteractiveBrowserCredential` (local developer interactive sign-in)
- `CertificateCredential` (service principal / automation)

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

### Scopes
`PurviewSettings.get_scopes()` derives the Graph scope list (currently `https://graph.microsoft.com/.default` style). Use it when acquiring tokens manually.

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

## Frequently Asked (Preview) Questions

Q: Does this send my entire conversation to Purview?  
A: Only the messages provided at each enforcement point (prompt phase: incoming conversation window; response phase: agent-produced messages). You control truncation upstream.

Q: Can I customize block messages?  
A: Yes – either subclass the middleware or add a later middleware that rewrites `context.result` when it matches the default block text.

Q: How do I disable response checks but keep prompt checks?  
A: Wrap the middleware and short-circuit the post-phase call to `_processor.process_messages`.

