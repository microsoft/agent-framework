## Purview Policy Enforcement Sample (Python)

This getting-started sample shows how to attach Microsoft Purview policy evaluation to an Agent Framework `ChatAgent` using the new **middleware** approach.

It mirrors the .NET `AgentWithPurview` sample but uses Python idioms and async primitives.

### What You Will Learn

1. Configure an Azure OpenAI chat client
2. Add Purview policy enforcement middleware (`PurviewPolicyMiddleware`)
3. Run a short conversation and observe prompt / response blocking behavior

---

## 1. Prerequisites

Install (from the repo root `python/` directory) with uv (preferred) or pip:

```powershell
uv sync --all-extras --dev
# or minimal
uv add agent-framework-purview
```

### Required Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint (https://<name>.openai.azure.com) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Optional | Model deployment name (defaults inside SDK if omitted) |
| `PURVIEW_CLIENT_APP_ID` | Yes* | Client (application) ID used for Purview auth |
| `PURVIEW_USE_CERT_AUTH` | Optional (`true`/`false`) | Switch between certificate and interactive auth |
| `PURVIEW_TENANT_ID` | Yes (when cert auth on) | Tenant ID for certificate authentication |
| `PURVIEW_CERT_PATH` | Yes (when cert auth on) | Path to your .pfx certificate |
| `PURVIEW_CERT_PASSWORD` | Optional | Password for encrypted certs |

*A demo default may exist in code for illustration only—always set your own value.

### 2 Auth Modes Supported

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

Certificate steps (summary): create / register app, generate certificate, upload public key, export .pfx with private key, grant required Graph / Purview permissions.

---

## 2. Run the Sample

From repo root:

```powershell
cd python/samples/getting_started/purview_agent
python sample_purview_agent.py
```

If interactive auth is used, a browser window will appear the first time.

---

## 3. How It Works

1. Builds an Azure OpenAI chat client (using the environment endpoint / deployment)
2. Chooses credential mode (certificate vs interactive)
3. Creates `PurviewPolicyMiddleware` with `PurviewSettings`
4. Injects middleware into the agent at construction
5. Sends two user messages sequentially
6. Prints results (or policy block messages)

Prompt blocks set a system-level message: `Prompt blocked by policy` and terminate the run early. Response blocks rewrite the output to `Response blocked by policy`.

---

## 4. Code Snippet (Middleware Injection)

```python
agent = ChatAgent(
	chat_client=chat_client,
	instructions="You are good at telling jokes.",
	name="Joker",
	middleware=[
		PurviewPolicyMiddleware(credential, PurviewSettings(appName="Sample App", defaultUserId="<guid>"))
	],
)
```

---

## 5. Customizing Behavior

- Change block messages by subclassing the middleware and overriding post-processing
- Add additional middlewares (tracing, logging) – Purview typically sits early to short‑circuit expensive downstream calls when blocked
- Provide a `PurviewAppLocation` to scope policy evaluation

---

## 6. Troubleshooting

| Symptom | Possible Cause | Fix |
|---------|----------------|-----|
| Immediate block every time | Misconfigured policy returning deny | Inspect Purview policy definitions / client logs |
| Auth error (401/403) | Wrong tenant / certificate / missing permission | Verify app registration & Graph delegated/application permissions |
| 429 errors | Rate limit from service | Implement retry or exponential backoff (future helper planned) |

Enable verbose logging (example):

```powershell
$env:AZURE_LOG_LEVEL = "info"
```

---

## 7. Next Steps

- Combine with other agent tools & multi-agent orchestration
- Add tests mocking `PurviewClient` for deterministic block scenarios
- Wrap in a web API or queue worker for batch content vetting

---

## 8. Related Links

- Package README: `python/packages/purview/README.md`
- Core Agent Getting Started: `python/packages/core/README.md`
- All Python Samples: `python/samples/getting_started`
- Issues / Feedback: https://github.com/microsoft/agent-framework/issues

---

MIT Licensed. Contributions welcome.
