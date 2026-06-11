## Purview Policy Enforcement Sample (Python)

This getting-started sample shows how to attach Microsoft Purview policy evaluation to an Agent Framework `Agent` using the **middleware** approach.

**What this sample demonstrates:**
1. Configure a Foundry chat client
2. Add Purview policy enforcement middleware (`PurviewPolicyMiddleware`)
3. Add Purview policy enforcement at the chat client level (`PurviewChatPolicyMiddleware`)
4. Implement a custom cache provider for advanced caching scenarios
5. Run conversations and observe prompt / response blocking behavior

**Note:** Caching is **automatic** and enabled by default with sensible defaults (30-minute TTL, 200MB max size).

---
## 1. Setup
### Required Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | Azure AI Foundry project endpoint, for example `https://<resource>.services.ai.azure.com/api/projects/<project>` |
| `FOUNDRY_MODEL` | Optional | Model deployment name (defaults to `gpt-4o-mini`) |
| `PURVIEW_CLIENT_APP_ID` | Yes* | Client (application) ID used for Purview authentication |
| `PURVIEW_USE_CERT_AUTH` | Optional (`true`/`false`) | Switch between certificate and interactive auth |
| `PURVIEW_TENANT_ID` | Yes (when cert auth on) | Tenant ID for certificate authentication |
| `PURVIEW_CERT_PATH` | Yes (when cert auth on) | Path to your .pfx certificate |
| `PURVIEW_CERT_PASSWORD` | Optional | Password for encrypted certs |

### 2. Auth Modes Supported

#### A. Interactive Browser Authentication (default)
Opens a browser on first run to sign in.

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<resource>.services.ai.azure.com/api/projects/<project>"
$env:FOUNDRY_MODEL = "gpt-4o-mini"
$env:PURVIEW_CLIENT_APP_ID = "00000000-0000-0000-0000-000000000000"
```

#### B. Certificate Authentication
For headless / CI scenarios.

```powershell
$env:PURVIEW_USE_CERT_AUTH = "true"
$env:PURVIEW_TENANT_ID = "<tenant-guid>"
$env:PURVIEW_CERT_PATH = "C:\path\to\cert.pfx"
$env:PURVIEW_CERT_PASSWORD = "optional-password"
```

Certificate steps (summary): create / register entra app, generate certificate, upload public key, export .pfx with private key, grant required Graph / Purview permissions.

---

## 3. Run the Sample

From repo root:

```powershell
cd python/samples/05-end-to-end/purview_agent
python sample_purview_agent.py
```

If interactive auth is used, a browser window will appear the first time.

---

## 4. How It Works

The sample demonstrates four integration scenarios. Each scenario runs the same three-message sequence via `run_policy_flow(...)`:

1. **good (cold cache)** - a benign prompt that exercises the cold-cache parallel ProtectionScopes warmup + foreground ProcessContent path.
2. **expected block** - a sensitive prompt containing the Visa test credit card number `4111 1111 1111 1111`. If the tenant has a DLP policy for `Microsoft 365 Copilot and AI apps` targeting the Credit Card sensitive info type with a Block action, this prompt returns the configured `blocked_prompt_message` (default: `Prompt blocked by policy`). If no DLP policy applies, the prompt is allowed (the LLM may still decline on its own, but that is a model-level response, not a Purview block).
3. **good (warm cache)** - a second benign prompt that exercises the warm-cache path. The custom cache provider scenario prints `Cache HIT` for the same protection-scopes key, confirming the cache and middleware state survive a prior block.

### A. Agent Middleware (`run_with_agent_middleware`)
1. Builds a Foundry chat client (using the environment project endpoint / deployment)
2. Chooses credential mode (certificate vs interactive)
3. Creates `PurviewPolicyMiddleware` with `PurviewSettings`
4. Injects middleware into the agent at construction
5. Runs the three-message `good -> block -> good` orchestration
6. Prints `ALLOWED` or `BLOCKED` per message, plus the model response
7. Uses default caching automatically

### B. Chat Client Middleware (`run_with_chat_middleware`)
1. Creates a chat client with `PurviewChatPolicyMiddleware` attached directly
2. Policy evaluation happens at the chat client level rather than agent level
3. Demonstrates an alternative integration point for Purview policies
4. Runs the same `good -> block -> good` orchestration
5. Uses default caching automatically

### C. Custom Cache Provider (`run_with_custom_cache_provider`)
1. Implements the `CacheProvider` protocol with a custom class (`SimpleDictCacheProvider`)
2. Shows how to add custom logging and metrics to cache operations
3. The custom provider must implement three async methods:
   - `async def get(self, key: str) -> Any | None`
   - `async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None`
   - `async def remove(self, key: str) -> None`
4. Runs the `good -> block -> good` orchestration and prints `Cache MISS`/`Cache HIT` traces alongside policy outcomes, showing the cold-cache warmup populating the cache and warm-cache requests skipping ProtectionScopes.

### D. Default Cache (`run_with_default_cache`)
1. Same as the agent middleware path but with explicit cache TTL and size limits in `PurviewSettings`
2. Uses the default in-memory `CacheProvider`
3. Runs the `good -> block -> good` orchestration

**Policy Behavior:**
Prompt blocks substitute the configured `blocked_prompt_message` (default `Prompt blocked by policy`) and terminate the agent run early. Response blocks substitute `blocked_response_message`. The LLM is never called for a blocked prompt.

**Seeing a real `BLOCKED` outcome:**
The middle prompt only returns `BLOCKED` if the tenant actually has a Purview DLP policy that matches the request. Specifically, all of the following must be true:

1. The Entra app id used by `PURVIEW_CLIENT_APP_ID` (the same id Agent Framework sends as `policyLocationApplication.value`) is registered as an integrated AI app in Purview (Settings -> AI app and agent locations).
2. A DLP policy in the tenant targets the location `Microsoft 365 Copilot and AI apps`, scoped to that app id (or `All apps`).
3. The policy has a rule with the condition `Content contains -> Sensitive info types -> Credit Card Number` and an action of `Restrict access to Microsoft 365 Copilot and AI apps -> Block`.
4. The policy is `On` (not `Test mode without notifications`).
5. The signed-in user is in the policy's user scope.
6. Required Graph delegated permissions are admin-consented: `ProtectionScopes.Compute.All`, `Content.Process.All`, `ContentActivity.Write`.

If any of those are missing, the credit card prompt is allowed at the Purview layer. The model itself may still decline on its own; that response is a model-level refusal, not a Purview block. The cold/warm cache orchestration is still demonstrated either way - the `Cache MISS -> Cache HIT` trace from the custom cache scenario does not depend on a block firing.

---

## 5. Code Snippets

### Agent Middleware Injection

```python
agent = Agent(
	client=client,
	instructions="You are good at telling jokes.",
	name="Joker",
	middleware=[
		PurviewPolicyMiddleware(credential, PurviewSettings(app_name="Sample App"))
	],
)
```

### Custom Cache Provider Implementation

This is only needed if you want to integrate with external caching systems.

```python
class SimpleDictCacheProvider:
    """Custom cache provider that implements the CacheProvider protocol."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache."""
        return self._cache.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache."""
        self._cache[key] = value

    async def remove(self, key: str) -> None:
        """Remove a value from the cache."""
        self._cache.pop(key, None)

# Use the custom cache provider
custom_cache = SimpleDictCacheProvider()
middleware = PurviewPolicyMiddleware(
    credential,
    PurviewSettings(app_name="Sample App"),
    cache_provider=custom_cache,
)
```

---
