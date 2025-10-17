## Purview Policy Enforcement Sample (Python)

This getting-started sample shows how to attach Microsoft Purview policy evaluation to an Agent Framework `ChatAgent` using the **middleware** approach.

1. Configure an Azure OpenAI chat client
2. Add Purview policy enforcement middleware (`PurviewPolicyMiddleware`)
3. Run a short conversation and observe prompt / response blocking behavior

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

*A demo default exists in code for illustration only—always set your own value.

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

Certificate steps (summary): create / register app, generate certificate, upload public key, export .pfx with private key, grant required Graph / Purview permissions.

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

1. Builds an Azure OpenAI chat client (using the environment endpoint / deployment)
2. Chooses credential mode (certificate vs interactive)
3. Creates `PurviewPolicyMiddleware` with `PurviewSettings`
4. Injects middleware into the agent at construction
5. Sends two user messages sequentially
6. Prints results (or policy block messages)

Prompt blocks set a system-level message: `Prompt blocked by policy` and terminate the run early. Response blocks rewrite the output to `Response blocked by policy`.

---

## 5. Code Snippet (Middleware Injection)

```python
agent = ChatAgent(
	chat_client=chat_client,
	instructions="You are good at telling jokes.",
	name="Joker",
	middleware=[
		PurviewPolicyMiddleware(credential, PurviewSettings(app_name="Sample App", default_user_id="<guid>"))
	],
)
```

---
