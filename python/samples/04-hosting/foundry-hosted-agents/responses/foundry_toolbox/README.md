# Agent with Foundry Toolbox (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery, hosted on Microsoft Foundry using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Deploy a hosted agent

For the runnable deployment quickstart, follow the [Foundry Toolbox hosted-agent sample in foundry-samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox). That sample maintains the prerequisites, project initialization, connections, toolbox provisioning, deployment, and invocation instructions together with its `azure.yaml`.

This directory is an Agent Framework integration example for understanding and developing the framework code locally. It is not a second deployment quickstart. Follow the deployment sample in its own project directory with its own source and configuration; do not use its manifest to deploy the code in this directory.

## Creating a Foundry Toolbox

You can create a Foundry Toolbox by code. Refer to this sample for an example: [Foundry Toolbox CRUD Sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/toolboxes/sample_toolboxes_crud.py).

You can also create a Foundry Toolbox in the Foundry portal. Read more about it [in the Foundry toolbox documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox).

This sample consumes a toolbox over its MCP endpoint. It bundles a [`toolbox.yaml`](toolbox.yaml) that defines 6 tools behind one endpoint:

- **Web search**, which grounds responses in real-time public web results.
- **Code interpreter**, which executes Python code in a secure sandbox and returns the output.
- **Azure Specs MCP**, which demonstrates connecting to an MCP server that doesn't require authentication.
- **GitHub MCP**, which demonstrates connecting to the GitHub MCP server using either a Personal Access Token (PAT) or OAuth2 (switch by changing the `project_connection_id` in `toolbox.yaml`).
- **Azure Language MCP with agent identity**, which demonstrates connecting to the Azure Language MCP server using agent identity for authentication.
- **Microsoft Foundry MCP with Entra pass-through**, which demonstrates connecting to the Microsoft Foundry MCP server using Entra pass-through for authentication.

### Authentication Methods

You can connect to MCP servers in Foundry Toolbox that use different authentication methods. This sample demonstrates the following authentication methods:

- [**No authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-unauthenticated.md): The tool does not require any authentication. The agent can invoke the tool without providing any credentials. Sample MCP server: `https://gitmcp.io/Azure/azure-rest-api-specs`
- [**Key-based authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-key-auth.md): The tool requires a key to authenticate. Sample MCP server: `https://api.githubcopilot.com/mcp` (GitHub MCP server) with a Personal Access Token (PAT) for authentication.
- [**OAuth2 authentication (managed)**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-managed.md): The tool requires OAuth2 to authenticate. Sample MCP server: `https://api.githubcopilot.com/mcp` (GitHub MCP server) with OAuth2 for authentication.
- [**Agent identity authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md): The tool requires an agent identity token to authenticate. Sample MCP server: `https://{foundry-resource-name}.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview` ([Azure Language MCP server](https://learn.microsoft.com/en-us/azure/ai-services/language-service/concepts/foundry-tools-agents#azure-language-mcp-server-preview)) with agent identity for authentication.
- [**Entra Pass-through authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-user-entra-token.md): The tool requires an Entra pass-through token to authenticate; Foundry forwards the calling user's Entra token to the MCP server. Sample MCP server: the [Microsoft Foundry MCP server](https://learn.microsoft.com/en-us/azure/foundry/mcp/get-started?view=foundry&tabs=user), which exposes Foundry model-catalog, evaluation, agent, and session tools and requires only that the caller have access to the Foundry project (no extra license).

There are also Non-MCP tools in the toolbox that support different authentication methods. Learn more at the [Foundry sample repository](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/README.md).

### Finding the Entra audience for an MCP server

An Entra pass-through connection requires an **audience** — the Entra resource that the MCP server validates tokens against. For the Microsoft Foundry MCP server (`https://mcp.ai.azure.com`), read it from the server's OAuth protected-resource metadata:

```bash
curl https://mcp.ai.azure.com/.well-known/oauth-protected-resource
```

```jsonc
{
  "resource": "https://mcp.ai.azure.com",
  "authorization_servers": ["https://login.microsoftonline.com/common/v2.0"],
  "scopes_supported": ["https://mcp.ai.azure.com/Foundry.Mcp.Tools"]
}
```

Use the `resource` value (`https://mcp.ai.azure.com`) as the audience.

> For connector-backed MCP servers (for example Microsoft 365 / WorkIQ servers such as Outlook Mail), the audience is instead published in the Foundry Tools Catalog. Look it up with the helper scripts in [`scripts/`](scripts/): run `./scripts/list-foundry-connectors.ps1 -ConnectorName <name>` (or `./scripts/list-foundry-connectors.sh -n <name>`) and read `AzureActiveDirectoryResourceId` (equivalently `resourceUri`) under `properties.x-ms-connection-parameters`. Run the script with no connector name to list every connector with its name, title, and auth type.

### Project connections

The bundled `toolbox.yaml` references project connections named `ghmcppat` (or `ghmcpoauth` for OAuth2), `langmcpconn`, and `foundrymcpconn`. These connections hold the authentication configuration for the corresponding tools; they must exist in the project hosting that toolbox. See the [Foundry toolbox documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox) for toolbox and connection setup. For an end-to-end deployment, use the separate [foundry-samples quickstart](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox) and its configuration rather than combining the two projects.

## How it works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via `FoundryToolbox`, which discovers and invokes the toolbox's tools over MCP at runtime. Set `TOOLBOX_ENDPOINT` to the toolbox's versioned MCP endpoint for local development.

See [main.py](main.py) for the full implementation.

### Request-owned resources

The host receives `agent=create_agent`, not a process-wide agent instance.
Every request creates a fresh client and Toolbox MCP connection, then closes
them afterward. This gives the sample one clear owner for its model transports,
credential and Toolbox lifecycle. `FoundryToolbox` also supports long-lived
instances: it resolves the current platform headers before each operation and
reconnects the MCP session when that identity changes, so a shared instance does
not retain an earlier caller's `x-agent-foundry-call-id`.

The sample client closes only its own model/project transports and credential,
including when MCP entry fails or the request is cancelled. Local authentication
uses `AzureCliCredential`; deployed authentication uses managed identity.
`history_source="agent_server"` reconstructs the outer Responses transcript and
disables inner model storage. Caller `store=false` prevents host-managed state,
not external tool side effects.

Toolbox connections remain explicitly configured in the Foundry project.
PAT-backed tools act as the configured external account; user-identity tools
require the appropriate pass-through connection and the current call ID. A fresh
Python object does not by itself grant external permissions. GitHub PAT/OAuth
connections, project roles and consent are separate setup, not offline coverage.
Native code-interpreter file citations are a separate tracked behavior
(microsoft/agent-framework#7916), not implemented by this lifecycle change.

## Local framework development

Use the current workspace environment described in the [Python development setup](../../../../../DEV_SETUP.md) and the [local hosting guide](../../README.md#running-the-agent-host-locally). The sample's [inline script metadata](main.py) lists its dependencies. Use workspace packages when developing the current hosting APIs; older published packages might not contain them.

Before running locally, you need an existing Foundry project, a model deployment, and a toolbox with its required project connections and permissions. Local execution does not provision these resources. Copy [`.env.example`](.env.example) to `.env` in this sample directory and set:

| Variable | Value |
| --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | The project endpoint, such as `https://your-account.services.ai.azure.com/api/projects/your-project`. |
| `FOUNDRY_MODEL` | The model deployment name in that project. |
| `TOOLBOX_ENDPOINT` | The versioned MCP endpoint of the toolbox you want to use. |

Authenticate with `az login`. From the repository's `python` directory, run the local source using the configured workspace environment:

```powershell
uv run --no-sync python samples\04-hosting\foundry-hosted-agents\responses\foundry_toolbox\main.py
```

The agent host starts on `http://localhost:8088`. Send a Responses request from another terminal:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8088/responses -ContentType "application/json" -Body '{"input": "What tools do you have?", "store": false}'
```

The agent discovers the configured toolbox's tools and answers using the selected model. A local run uses your Azure CLI identity; it does not reproduce hosted caller identity or validate hosted deployment. See the authentication boundaries above and below.

## Troubleshooting

### A single failing MCP source can fail the whole agent

A toolbox aggregates every tool source behind one MCP endpoint. If **any** referenced MCP server fails while the toolbox enumerates tools (`tools/list`), the toolbox fails the entire enumeration, so the agent can't load its tools and every request returns an error (HTTP 500) until that source recovers.

For example, a flaky third-party MCP source can intermittently return `HTTP 502 (Bad Gateway)` during enumeration, which surfaces as:

```
tools/list failed for 1 tool source(s), succeeded for 5 tool source(s)
{"errors":[{"name":"<server_label>","type":"mcp","error":{"code":"HTTP_502", ...}}]}
```

This is an upstream/service hiccup, not a problem with the agent code. Mitigations:

- Retry the request — these failures are usually transient.
- If a source is persistently unavailable, temporarily remove its tool entry (and connection) from `toolbox.yaml`, recreate the toolbox, and update `TOOLBOX_ENDPOINT`.
- Inspect deployed agent logs with `azd ai agent monitor` to identify which source failed.

### Entra pass-through forwards the caller's identity

The Foundry MCP tool authenticates with **Entra pass-through** (`foundrymcpconn`): Foundry forwards the
calling user's Entra token to `https://mcp.ai.azure.com`. The token is forwarded both from the Foundry
portal **Agent Playground** (signed-in user) and by `azd ai agent invoke` (the developer's Entra token),
so the tools operate as that user and only act on resources the user can already access. The Foundry MCP
server requires no extra license — just access to the Foundry project.

Because the tool acts as a specific user, running the agent **locally** (`python main.py`) or calling the
endpoint with a raw token uses whatever identity that token represents (`az login` user locally, the
agent's managed identity when hosted). If that identity has no access to the target resources, the tool
returns an authorization error even though it is discovered and called correctly.

> Some other Entra pass-through MCP servers add their **own** entitlement checks on top of the token. For
> example, the Microsoft 365 / WorkIQ servers (Outlook Mail, Teams) require the caller to hold a
> **Microsoft 365 Copilot (Business Chat)** license; without it they fail with
> `WorkIQ license check failed. Required service plan(s): [M365_COPILOT_BUSINESS_CHAT]`. That is a
> property of those servers, not of Entra pass-through itself.

## Next steps

- [Foundry Toolbox deployment quickstart](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox) — runnable project with deployment instructions and configuration
- [Tool catalog](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/tool-catalog) — browse available tools to extend your agent (Bing Search, Azure AI Search, file search, code interpreter, and more)
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
- [Basic agent](../basic/) — minimal agent with no tools
- [Add local tools](../tools/) — sample with locally-defined Python tool functions
- [Build multi-agent workflows](../workflows/) — sample with chained agent pipelines
