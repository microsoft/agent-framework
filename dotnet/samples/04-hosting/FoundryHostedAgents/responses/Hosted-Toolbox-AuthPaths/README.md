# Hosted Toolbox — Authentication Paths

A hosted Foundry agent backed by a single Foundry Toolbox that bundles MCP tools using **three different authentication paths**. The educational surface lives in the toolbox configuration (which you provision in the Foundry portal) and in this README — the agent code itself is identical to the existing [`Hosted-Toolbox/`](../Hosted-Toolbox/) sample.

Drive the agent across the auth paths with the shared [`Using-Samples/SimpleAgent/`](../Using-Samples/SimpleAgent/) REPL client, pointed at this agent. For the **OAuth user-consent** path (#4 below), use the dedicated [`Using-Samples/Hosted-Toolbox-AuthPaths-Client/`](../Using-Samples/Hosted-Toolbox-AuthPaths-Client/) REPL, which detects the consent request, **prints the consent link** and waits for you to press Enter once you have signed in, then re-sends. It never auto-opens a browser, so it works in headless, SSH, and container shells.

## What this sample teaches

| Aspect | This sample | Existing siblings |
|---|---|---|
| Toolbox marker pattern | `FoundryAITool.CreateHostedMcpToolbox(name)` + `AddFoundryToolboxes(credential, name)` | Same as [`Hosted-Toolbox/`](../Hosted-Toolbox/) |
| Tools per toolbox | **Three MCP tools, each with a different auth method** | `Hosted-Toolbox/`: typically one demo tool |
| Consumption | Server-side (Foundry resolves the marker) | Same |
| Client | Shared [`Using-Samples/SimpleAgent/`](../Using-Samples/SimpleAgent/) REPL, pointed at this agent | `Hosted-Toolbox/`: any client |

Related samples:
- [`Hosted-Toolbox/`](../Hosted-Toolbox/) — simpler single-tool toolbox.
- [`Hosted-McpTools/`](../Hosted-McpTools/) — contrasts client-side `McpClient` vs server-side `HostedMcpServerTool` for non-toolbox MCP servers.

## Authentication-path matrix

The sample's purpose is to enumerate every authentication path a Foundry toolbox can drive, so each path appears alongside the others. Pick the ones your scenario needs — each connection in a toolbox is independent.

| # | Auth method | MCP target | Connection `authType` | What flows where | When to pick this |
|---|---|---|---|---|---|
| 1 | **Key-based via project connection** | GitHub MCP at `https://api.githubcopilot.com/mcp` | `CustomKeys` | A PAT stored as `Authorization: Bearer <pat>` lives in the Foundry connection. The toolbox proxy reads it server-side and injects on every MCP call. | The upstream service only accepts API keys or PATs. |
| 2 | **Microsoft Entra — agent identity** | Any Azure Cognitive Services MCP endpoint your project can reach (e.g., Language service MCP) | `AgenticIdentityToken` | Foundry mints an Entra token for the agent's own identity (`instance_identity` in the new agent object model), scoped to the connection's `audience`, and forwards it to the MCP server. The agent identity must hold the required role (typically `Cognitive Services User`) on the target resource. | Per-agent least-privilege access to Entra-protected services. Recommended default for new agents. |
| 3 | **Inline `Authorization` (anti-pattern)** | `https://gitmcp.io/Azure/azure-rest-api-specs` | none | A literal bearer string lives on the toolbox tool entry's `authorization` field. **Do not do this in production** — there's no rotation, no secret store, no per-user identity. Shown for completeness. | Local-dev or public MCP servers that accept any (or no) bearer. |
| 4 | **OAuth — per-user consent (delegated)** | Any per-user OAuth-protected MCP target (e.g. delegated Microsoft Graph, a Logic Apps connector) | `OAuth` connection | The first call for a user has no stored token, so the proxy returns `CONSENT_REQUIRED`. The agent surfaces an `oauth_consent_request` with a consent link and marks the response `incomplete`. The user consents out of band; the proxy then stores their delegated token (bound to the user, not the conversation) and performs the on-behalf-of exchange on every subsequent call. | The tool must act **as the end user** against a downstream that requires delegated consent. |

> **Path #4 needs the OAuth-aware client.** The shared `SimpleAgent/` REPL ignores the consent request and the call simply stays incomplete. Use [`Using-Samples/Hosted-Toolbox-AuthPaths-Client/`](../Using-Samples/Hosted-Toolbox-AuthPaths-Client/) instead — it prints the consent link, waits for you to press Enter after you have signed in, then re-sends the prompt. The user's token never touches the container or the client; consent and the OBO exchange happen entirely between the user, the identity provider, and the toolbox proxy.

## Prerequisites

### 0. (Path #2 only) Identify an Entra-authenticated MCP target

Path #2 requires an MCP server that accepts Microsoft Entra tokens. Any **Azure Cognitive Services** resource that exposes an MCP endpoint works — they all accept Entra ID tokens and gate access via standard RBAC.

The reference walkthrough below uses an **Azure Language service** MCP endpoint:

```
https://<your-language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview
```

Substitute any other Cognitive Services MCP endpoint you have. If your project has none, omit tool #2 from your toolbox — the remaining two paths still work.

#### RBAC for path #2

Grant the **`Cognitive Services User`** role on the target resource to the agent's instance identity. Find it on the agent ARM resource (Azure portal → your agent → JSON view) at `instance_identity.principal_id`. This is the principal the Foundry proxy uses when minting tokens for `AgenticIdentityToken` connections.

```powershell
$lang = "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<lang-svc>"

az role assignment create `
    --assignee-object-id <agent-instance-identity-principal-id> `
    --assignee-principal-type ServicePrincipal `
    --role "Cognitive Services User" `
    --scope $lang
```

Repeat for any additional Cognitive Services resources the agent identity needs to call.

> The RBAC grant requires `Microsoft.Authorization/roleAssignments/write` on the target scope. In many enterprise subscriptions this needs a PIM JIT activation.

### 1. Foundry project + Azure AI User role

- An active Microsoft Foundry project ([create one](https://learn.microsoft.com/en-us/azure/foundry/how-to/create-projects)).
- The **Azure AI User** role on the project assigned to:
  - The developer (you) creating the toolbox.
  - The agent identity for tool invocation.

### 2. Create the project connections

The Entra-based connection (path #2) is not available in the Foundry portal connection wizard today. Create it via ARM REST:

```powershell
$armToken = az account get-access-token --query accessToken -o tsv
$h        = @{ Authorization = "Bearer $armToken"; "Content-Type" = "application/json" }
$proj     = "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project>"
$lang     = "https://<lang-svc>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview"

# Path 2 — agent identity
$body2 = @{ properties = @{
    category = "RemoteTool"; target = $lang
    authType = "AgenticIdentityToken"; audience = "https://cognitiveservices.azure.com"
    isSharedToAll = $false
}} | ConvertTo-Json -Depth 5
az rest --method PUT --headers "Content-Type=application/json" `
    --url "https://management.azure.com$proj/connections/lang-mcp-agent-id?api-version=2025-04-01-preview" `
    --body $body2
```

Connection summary:

| Connection name (used by the toolbox) | `category` | `authType` | `audience` |
|---|---|---|---|
| `github-mcp-key` | `CustomKeys` | `CustomKeys` | n/a (key value carries `Authorization: Bearer <pat>`) |
| `lang-mcp-agent-id` | `RemoteTool` | `AgenticIdentityToken` | `https://cognitiveservices.azure.com` |

Path #3 (`gitmcp.io`) needs no connection — the auth lives on the toolbox tool entry itself.

The `audience` value is the token resource identifier of the target service — for any Cognitive Services resource it is `https://cognitiveservices.azure.com`. For other Azure services consult [Agent identity — runtime token exchange](https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity#runtime-token-exchange).

### 3. Create the toolbox

In the Foundry portal → Tools → Add Toolbox. Name it `auth-paths-toolbox` (or whatever you prefer; export the name as `TOOLBOX_NAME`). Add three MCP tool entries:

| Tool `server_label` | `server_url` | Auth |
|---|---|---|
| `github_pat` | `https://api.githubcopilot.com/mcp` | `project_connection_id: github-mcp-key` |
| `lang_agent` | Your Language service MCP URL | `project_connection_id: lang-mcp-agent-id` |
| `gitmcp_inline` | `https://gitmcp.io/Azure/azure-rest-api-specs` | `authorization: "Bearer demo-only-not-real"` (no `project_connection_id`) |

Each entry should also carry:

- `require_approval: never` (this sample is focused on auth, not approval flows; see [`ToolCallingApprovalHostedAgentFixture.cs`](../../../../../tests/Foundry.Hosting.IntegrationTests/Fixtures/ToolCallingApprovalHostedAgentFixture.cs) for that concern).
- A tight `allowed_tools` list. GitHub MCP exposes ~50 tools; restrict to what you actually want the model to invoke. For example: `github_pat` → `["search_issues", "list_pull_requests"]`. **Every name in `allowed_tools` must match a real tool on the upstream server** — an unknown name (e.g., `get_issue`, which GitHub MCP does not expose) makes the whole source fail enumeration. See the partial-failure note below.

### Sidebar — what the toolbox-creation code looks like

This sample assumes the toolbox already exists; it does not provision one programmatically. For an end-to-end code example of toolbox creation from a publisher script (suitable for a CI/CD pipeline), see [`02-agents/AgentProviders/foundry/Agent_Step25_FoundryToolboxMcp/Program.cs`](../../../../02-agents/AgentProviders/foundry/Agent_Step25_FoundryToolboxMcp/Program.cs) — its `CreateSampleToolboxAsync` helper uses `AgentAdministrationClient.GetAgentToolboxes().CreateToolboxVersionAsync(...)` and is the canonical pattern.

## Run the agent

Set environment variables (or copy `.env.example` to `.env` and fill it in):

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT  = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME = "gpt-4o"
$env:TOOLBOX_NAME       = "auth-paths-toolbox"
```

Locally, the `Foundry.Hosting` package reads `AZURE_AI_PROJECT_ENDPOINT` as a fallback when `FOUNDRY_PROJECT_ENDPOINT` is absent. In the hosted Foundry runtime, the platform auto-injects `FOUNDRY_PROJECT_ENDPOINT` and the package builds the toolbox proxy URL as `{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{TOOLBOX_NAME}/mcp?api-version=v1` per [`tools-integration-spec.md`](https://github.com/microsoft/AgentSchema/blob/main/specs/agents/hosted_agents/container-spec/docs/tools-integration-spec.md) §2–§3.

Then sign in (`az login`) and start the server:

```powershell
dotnet run --tl:off
```

The server logs at `http://localhost:8088/`. In Development it also maps the per-agent OpenAI route shape (`MapDevTemporaryLocalAgentEndpoint()`), so the shared `SimpleAgent` REPL client can reach it through `AsAIAgent(agentEndpoint)` — the only supported way to consume a hosted Foundry agent. In a separate terminal:

**Against the local dev server** (point the client at localhost; the `{project}` segment is a wildcard the server ignores):

```powershell
cd ../Using-Samples/SimpleAgent
$env:AZURE_AI_PROJECT_ENDPOINT = "http://localhost:8088/api/projects/local"
$env:AZURE_AI_AGENT_NAME       = "hosted-toolbox-auth-paths-agent"
dotnet run --tl:off
```

**Against a deployed agent** (point the client at the real project endpoint and the deployed agent name):

```powershell
cd ../Using-Samples/SimpleAgent
$env:AZURE_AI_PROJECT_ENDPOINT = "https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_AGENT_NAME       = "hosted-toolbox-auth-paths-agent"
dotnet run --tl:off
```

Either way the client derives the per-agent endpoint URL (`{AZURE_AI_PROJECT_ENDPOINT}/agents/{AZURE_AI_AGENT_NAME}/endpoint/protocols/openai`) and consumes the agent via `AsAIAgent(agentEndpoint)`. Run `az login` first so the client can mint a bearer token.

> **Parallel-run warning**: `Hosted-Toolbox/` and other `Hosted-*` samples default to the same port (8088) and the same agent name slot. Always set a unique `AGENT_NAME` (this sample defaults to `hosted-toolbox-auth-paths-agent`) and stop other hosted samples before starting this one.

## Sample prompts

One per auth path so each tool gets exercised at least once:

```
List the latest 3 issues in microsoft/agent-framework.            # path #1 — GitHub MCP (key)
Detect the language of "Bonjour le monde".                        # path #2 — Language MCP (agent identity)
What's the latest API version for Microsoft.CognitiveServices?    # path #3 — gitmcp.io (inline Authorization)
Send a test email to myself.                                      # path #4 — OAuth user consent (use the OAuth client)
```

> Path #4 triggers the consent flow on first use. Run it from [`Using-Samples/Hosted-Toolbox-AuthPaths-Client/`](../Using-Samples/Hosted-Toolbox-AuthPaths-Client/), not `SimpleAgent/`.

## Troubleshooting / partial-failure semantics

`AddFoundryToolboxes` resolves the toolbox at startup by listing its tools via MCP `tools/list`. For **hard** errors this enumeration is **all-or-nothing**: if *any* single tool source fails to enumerate (a bad `allowed_tools` name, a rejected key or Entra token, an unreachable upstream), the Foundry toolbox proxy returns a top-level JSON-RPC error (`-32007`) instead of a partial list, the hosting package marks the toolbox startup as failed, `/readiness` returns 503, and *every* invoke against the agent returns **HTTP 424** — even for the auth paths that are configured correctly. So one misconfigured connection or one bad `allowed_tools` entry bricks the whole agent at startup. Get each source enumerating cleanly before deploying.

**Exception — OAuth consent (path #4) does not brick the container.** When a source fails enumeration purely because it needs per-user OAuth consent (`CONSENT_REQUIRED`), the hosting package keeps the container **healthy and routable**: `/readiness` stays 200 and the consent requirement is surfaced per-request as an `oauth_consent_request` with a consent link. The user consents (via the [`Hosted-Toolbox-AuthPaths-Client/`](../Using-Samples/Hosted-Toolbox-AuthPaths-Client/) REPL), re-sends, and enumeration is retried so the tool becomes available. A *mix* of `CONSENT_REQUIRED` and any non-consent error is still treated as a hard failure (consent alone cannot make enumeration succeed). Symptoms per auth path:

| Symptom | Likely cause |
|---|---|
| **All invokes return HTTP 424 ("Failed Dependency")** | One or more tool sources failed `tools/list` at startup (see all-or-nothing note above). Common causes: an `allowed_tools` name that does not exist on the upstream server, or an Entra connection whose token is rejected. Reproduce by calling the toolbox `tools/list` directly with your own token — a `-32007` top-level error names the failing source. |
| **HTTP 401 "audience is incorrect"** | The connection's `audience` field is missing or does not match the OAuth resource identifier the target service accepts. For Cognitive Services targets, set `audience: "https://cognitiveservices.azure.com"`. |
| **HTTP 401 / 403 "principal does not have access"** | Path #1: PAT expired or scope insufficient. Path #2: the agent's instance identity is missing the required role on the target resource. |
| **Container reports zero tools but startup succeeded** | `FoundryToolboxService.StartAsync` caches the `tools/list` result at startup. If a connection or RBAC grant changed after the container started, force a fresh container (re-deploy the agent version) — the cache won't pick up the change until then. |
| **HTTP 404 from a tool call** | Toolbox name mismatch (`TOOLBOX_NAME` vs the name in the portal), or the toolbox was deleted. |
| **Server logs a warning "Neither FOUNDRY_PROJECT_ENDPOINT nor AZURE_AI_PROJECT_ENDPOINT is set; toolbox support is disabled"** | Local dev without the env var set. The agent will load with zero tools and respond as if it has none. Set `AZURE_AI_PROJECT_ENDPOINT` (local-dev fallback) or `FOUNDRY_PROJECT_ENDPOINT` to your project endpoint. |
| **Tools appear but model never invokes them** | `instructions:` in `Program.cs` may not surface what each tool is for. Tighten the `allowed_tools` lists and rephrase prompts to mention the upstream service by name. |

## Region and model compatibility

Foundry Toolboxes have region constraints; some tool types are limited to specific models. This sample defaults to `gpt-4o`, which works in all supported regions. For the full matrix, see the [Foundry tools compatibility matrix](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox#region-and-model-compatibility).

## Anti-pattern note for path #3

Inline `authorization` on a toolbox tool entry stores credentials **inside the toolbox definition**. There is no rotation, no per-user scoping, no secret-store integration. Use it only for:

- Public MCP servers that ignore the bearer (the `gitmcp.io` case demonstrated here).
- Local development against a test MCP server with a throwaway token.

For everything else use `project_connection_id` and let the platform inject credentials.
