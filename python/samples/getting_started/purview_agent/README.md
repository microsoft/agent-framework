## Purview Policy Enforcement Sample (Python)

This getting-started sample shows how to attach Microsoft Purview policy evaluation to an Agent Framework `ChatAgent` using the **middleware** approach.

**What this sample demonstrates:**
1. Configure an Azure OpenAI chat client
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
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint (https://<name>.openai.azure.com) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Optional | Model deployment name (defaults inside SDK if omitted) |
| `PURVIEW_CLIENT_APP_ID` | Yes* | Client (application) ID used for Purview authentication |
| `PURVIEW_USE_CERT_AUTH` | Optional (`true`/`false`) | Switch between certificate and interactive auth |
| `PURVIEW_TENANT_ID` | Yes (when cert auth on) | Tenant ID for certificate authentication |
| `PURVIEW_CERT_PATH` | Yes (when cert auth on) | Path to your .pfx certificate |
| `PURVIEW_CERT_PASSWORD` | Optional | Password for encrypted certs |

### 2. Auth Modes Supported

#### A. Interactive Browser Authentication (default)
Opens a browser on first run to sign in.

```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://your-openai-instance.openai.azure.com"
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
cd python/samples/getting_started/purview_agent
python sample_purview_agent.py
```

If interactive auth is used, a browser window will appear the first time.

---

## 4. How It Works

The sample demonstrates three different scenarios:

### A. Agent Middleware (`run_with_agent_middleware`)
1. Builds an Azure OpenAI chat client (using the environment endpoint / deployment)
2. Chooses credential mode (certificate vs interactive)
3. Creates `PurviewPolicyMiddleware` with `PurviewSettings`
4. Injects middleware into the agent at construction
5. Sends two user messages sequentially
6. Prints results (or policy block messages)
7. Uses default caching automatically

### B. Chat Client Middleware (`run_with_chat_middleware`)
1. Creates a chat client with `PurviewChatPolicyMiddleware` attached directly
2. Policy evaluation happens at the chat client level rather than agent level
3. Demonstrates an alternative integration point for Purview policies
4. Uses default caching automatically

### C. Custom Cache Provider (`run_with_custom_cache_provider`)
1. Implements the `CacheProvider` protocol with a custom class (`SimpleDictCacheProvider`)
2. Shows how to add custom logging and metrics to cache operations
3. The custom provider must implement three async methods:
   - `async def get(self, key: str) -> Any | None`
   - `async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None`
   - `async def remove(self, key: str) -> None`

**Policy Behavior:**
Prompt blocks set a system-level message: `Prompt blocked by policy` and terminate the run early. Response blocks rewrite the output to `Response blocked by policy`.

---

## 5. Code Snippets

### Agent Middleware Injection

```python
agent = ChatAgent(
	chat_client=chat_client,
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
