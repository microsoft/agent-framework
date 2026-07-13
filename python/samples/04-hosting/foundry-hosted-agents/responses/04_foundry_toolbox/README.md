# Agent with Foundry Toolbox (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery, hosted on Microsoft Foundry using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Creating a Foundry Toolbox

You can create a Foundry Toolbox by code. Refer to this sample for an example: [Foundry Toolbox CRUD Sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/hosted_agents/sample_toolboxes_crud.py).

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

- [**No authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS.md#5-mcp-no-auth): The tool does not require any authentication. The agent can invoke the tool without providing any credentials. Sample MCP server: `https://gitmcp.io/Azure/azure-rest-api-specs`
- [**Key-based authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS.md#4-mcp-key-auth-github): The tool requires a key to authenticate. Sample MCP server: `https://api.githubcopilot.com/mcp` (GitHub MCP server) with a Personal Access Token (PAT) for authentication.
- [**OAuth2 authentication (managed)**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS.md#6-mcp-oauth-managed-connector): The tool requires OAuth2 to authenticate. Sample MCP server: `https://api.githubcopilot.com/mcp` (GitHub MCP server) with OAuth2 for authentication.
- [**Agent identity authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS.md#8-mcp-agent-identity): The tool requires an agent identity token to authenticate. Sample MCP server: `https://{foundry-resource-name}.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview` ([Azure Language MCP server](https://learn.microsoft.com/en-us/azure/ai-services/language-service/concepts/foundry-tools-agents#azure-language-mcp-server-preview)) with agent identity for authentication.
- [**Entra Pass-through authentication**](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS.md#13-mcp-oauth-entra-passthrough): The tool requires an Entra pass-through token to authenticate; Foundry forwards the calling user's Entra token to the MCP server. Sample MCP server: the [Microsoft Foundry MCP server](https://learn.microsoft.com/en-us/azure/foundry/mcp/get-started?view=foundry&tabs=user), which exposes Foundry model-catalog, evaluation, agent, and session tools and requires only that the caller have access to the Foundry project (no extra license).

There are also Non-MCP tools in the toolbox that support different authentication methods. Learn more at the [Foundry sample repository](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS.md).

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

### Creating Connections

Before creating the toolbox, create project connections for any tools that require authentication. The connection defines the authentication details and credentials for the tool, and the toolbox references the connection to authenticate tool invocations at runtime. The following connections are needed for this sample (used in `toolbox.yaml`):

For `ghmcppat`, run the following command to create a PAT-based connection to the GitHub MCP server:

```powershell
azd ai connection create ghmcppat --kind remote-tool --target https://api.githubcopilot.com/mcp --auth-type custom-keys --custom-key "Authorization=Bearer <github_pat>" -p https://<account>.services.ai.azure.com/api/projects/<project>
```

For `ghmcpoauth`, create an OAuth2-based connection to the GitHub MCP server:

```powershell
azd ai connection create ghmcpoauth --kind remote-tool --target https://api.githubcopilot.com/mcp --auth-type oauth2 --connector-name foundrygithubmcp -p https://<account>.services.ai.azure.com/api/projects/<project>
```

> This sample uses `ghmcppat` by default, but you can switch to `ghmcpoauth` in the `toolbox.yaml` file.

For `langmcpconn`, create an agent-identity-based connection to the Azure Language MCP server:

```powershell
azd ai connection create langmcpconn --kind remote-tool --target https://<language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview --auth-type project-managed-identity --audience https://cognitiveservices.azure.com/ -p https://<account>.services.ai.azure.com/api/projects/<project>
```

For `foundrymcpconn`, create an Entra pass-through connection to the Microsoft Foundry MCP server:

```powershell
azd ai connection create foundrymcpconn --kind remote-tool --target https://mcp.ai.azure.com --auth-type user-entra-token --audience https://mcp.ai.azure.com -p https://<account>.services.ai.azure.com/api/projects/<project>
```

### Creating the toolbox

You create the toolbox once from `toolbox.yaml`, then copy the versioned MCP endpoint it prints into the `TOOLBOX_ENDPOINT` environment variable. The agent connects to that endpoint at runtime.

```powershell
azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project>
```

## How it works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via `MCPStreamableHTTPTool`, which discovers and invokes the toolbox's tools over MCP at runtime. The agent resolves the endpoint from the `TOOLBOX_ENDPOINT` environment variable. If that variable isn't set, it builds the unversioned (default-version) endpoint from `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_NAME`.

See [main.py](main.py) for the full implementation.

## Running the agent

### Option 1: Azure Developer CLI (`azd`)

#### Prerequisites

1. **Azure Developer CLI (`azd`)** — [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.25 or later)
2. Install the unified Foundry CLI extension bundle (provides `azd ai agent`, `connection`, `inspector`, `project`, `routine`, `skill`, and `toolbox`):
   ```bash
   # If you previously installed individual extensions, uninstall them first:
   #   azd ext uninstall azure.ai.agents
   #   azd ext uninstall azure.ai.toolboxes
   azd ext install microsoft.foundry
   ```
3. Authenticate:
   ```bash
   azd auth login
   ```

#### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-toolbox-agent && cd my-toolbox-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox/agent.manifest.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one. Initializing also sets the selected project as the active project for the `azd ai` commands that follow.

#### Create the toolbox with `azd ai`

> [!TIP]
> If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, the following skill references describe the same endpoint contract (env var, headers, MCP protocol, citation patterns, and troubleshooting) that the agent must implement:
>
> - [Toolbox reference](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/foundry-agent/create/references/toolbox-reference.md) — endpoint format, MCP protocol, OAuth consent handling, citation patterns, and troubleshooting.
> - [Use toolbox in a hosted agent](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md) — endpoint resolution, env-var contract, payload shape, code integration patterns, and tracing.

The agent reads the toolbox's MCP endpoint from `TOOLBOX_ENDPOINT`. Create the toolbox once from the bundled [`toolbox.yaml`](toolbox.yaml):

```bash
azd ai toolbox create agent-tools --from-file ./toolbox.yaml --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project>
```

The first version becomes the default automatically. Use `azd ai toolbox list`, `azd ai toolbox show agent-tools`, and `azd ai toolbox version list agent-tools` to inspect, and `azd ai toolbox delete agent-tools --force` to remove it.

To stage incremental changes safely, use `azd ai toolbox connection add/remove` and `azd ai toolbox skill add/list/remove`; each creates a new toolbox version that carries forward existing connections and skills but **doesn't** change the default. Promote a version with `azd ai toolbox publish agent-tools <version>` when you're ready to make it active.

`azd ai toolbox create` prints the toolbox's versioned MCP endpoint. Copy that endpoint and store it in your `azd` environment so the agent connects to it:

```bash
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/agent-tools/versions/1/mcp?api-version=v1"
```

#### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

#### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

#### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "What tools do you have?"
```

#### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

#### Invoke the deployed agent

```bash
azd ai agent invoke "What tools do you have?"
```

### Option 2: VS Code (Foundry Toolkit)

#### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/get-started-projects-vs-code)** extension installed.
2. Sign in to Azure in VS Code.
3. The `agent-tools` toolbox must exist in your Foundry project. Create it from the bundled [`toolbox.yaml`](toolbox.yaml) (`azd ai toolbox create agent-tools --from-file ./toolbox.yaml`) or in the Foundry portal before you run the agent.

#### Create the project

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Create Hosted Agent**.
2. Select this sample from the gallery. The extension scaffolds the project into a new workspace and generates `agent.yaml`, `.env`, and `.vscode/tasks.json` + `launch.json` automatically.
3. Complete the **Foundry Project Setup** to pick the subscription and Foundry project (or create a new one).

#### Run and debug the agent

Press **F5** to start the agent in debug mode. The agent host will start on `http://localhost:8088`.

#### Test with Agent Inspector

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Open Agent Inspector**.
2. The Inspector connects to the running agent. Send messages to chat and view streamed responses.

#### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

### Creating a Foundry Toolbox

You can create a Foundry Toolbox by code. Refer to this sample for an example: [Foundry Toolbox CRUD Sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/hosted_agents/sample_toolboxes_crud.py).

You can also create a Foundry Toolbox in the Foundry portal. Read more about it [in the Foundry toolbox documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox).

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

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — end-to-end walkthrough using `azd`
- [Tool catalog](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/tool-catalog) — browse available tools to extend your agent (Bing Search, Azure AI Search, file search, code interpreter, and more)
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent) — monitor and manage deployed agents
- [Basic agent](../01_basic/) — minimal agent with no tools
- [Add local tools](../02_tools/) — sample with locally-defined Python tool functions
- [Build multi-agent workflows](../05_workflows/) — sample with chained agent pipelines
