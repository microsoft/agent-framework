# Agent with Foundry Toolbox (Responses Protocol)

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox**
for tool discovery, hosted on Microsoft Foundry using the **Responses protocol**. Foundry Toolbox
is a managed tool registry that lets you define tools centrally and share them across agents.

## Foundry Toolbox configuration

The unified [`azure.yaml`](azure.yaml) replaces the legacy agent manifests and standalone toolbox
definition. It declares the Foundry project, model deployment, authenticated connections, toolbox,
and hosted agent together. The `uses` dependencies deploy connections before the toolbox and the
toolbox before the agent.

The toolbox exposes six tool sources over one MCP endpoint:

| Source | Authentication | Connection |
|--------|----------------|------------|
| Web search | Built-in tool | None |
| Code interpreter | Built-in tool | None |
| Azure Specs MCP | No authentication | None |
| GitHub MCP | PAT in an Authorization header | `ghmcppat` |
| Azure Language MCP | Project managed identity | `langmcpconn` |
| Microsoft Foundry MCP | Calling user's Entra token | `foundrymcpconn` |

The toolbox's `connection` references resolve to project connection IDs at deployment time.
The PAT is read from the azd environment and sent as an `Authorization: Bearer` header; no
credentials belong in the YAML. To use OAuth instead, change the GitHub connection's authentication
configuration using the [managed OAuth guide](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-oauth-managed.md).
Changing only a toolbox reference does not configure OAuth.

For other tool types and authentication modes, see the
[supported toolbox scenarios](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/README.md)
and [Foundry toolbox documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox).

## How it works

### Model integration

The agent uses `FoundryChatClient` to create an OpenAI-compatible Responses client. `FoundryToolbox`
authenticates toolbox MCP requests and forwards the current platform headers while discovering
and invoking tools. It resolves `TOOLBOX_ENDPOINT`, or falls back to the default-version endpoint
built from `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_NAME`.

Deployment maps the versioned `TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT` output to the agent's
`TOOLBOX_ENDPOINT`. See [main.py](main.py) for the implementation.

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
([microsoft/agent-framework#7916](https://github.com/microsoft/agent-framework/issues/7916)),
not implemented by this configuration migration.

## Running the agent

### Option 1: Azure Developer CLI (`azd`)

#### Prerequisites

Prepare external credentials and permissions **before initializing**; init can prompt for the PAT
and Language endpoint.

1. **GitHub PAT**: [Create a fine-grained personal access token](https://github.com/settings/personal-access-tokens/new).
   Limit repository access and permissions to the GitHub MCP tools you intend to use. Supply the token
   without a `Bearer` prefix; the connection adds it. Keep the PAT out of source control.
2. **Azure Language resource**: obtain its
   [Language MCP endpoint](https://learn.microsoft.com/en-us/azure/ai-services/language-service/concepts/foundry-tools-agents#azure-language-mcp-server-preview).
   The Foundry project's managed identity needs **Cognitive Services Language Owner** on this resource.
   Arrange permission to make that role assignment. For an existing project, assign the role after init
   and before `azd up`. For a new project, the identity exists only after `azd provision`; see
   [Provision and deploy dependencies and agent](#provision-and-deploy-dependencies-and-agent).
3. **Foundry access**: the account you use with azd needs access to the selected Foundry project.
   The Foundry MCP connection forwards the calling user's Entra token and does not grant additional access.
4. **Azure Developer CLI (`azd`)**: [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)
   1.32.0 or later. The minimum extension versions are declared in `azure.yaml`.
5. Install the unified Foundry CLI extension bundle (provides agent, connection, inspector, project,
   routine, skill, and toolbox commands):
   ```bash
   # If you previously installed individual extensions, uninstall them first:
   # azd ext uninstall azure.ai.agents
   # azd ext uninstall azure.ai.toolboxes
   azd ext install microsoft.foundry
   ```
6. Authenticate deployment commands:
   ```bash
   azd auth login
   ```

#### Initialize the agent project

No cloning required. Create an empty folder and adopt this Agent Framework sample's unified
configuration. Here `--src .` selects the current folder as the **project destination**, not a separate
source directory:

```bash
mkdir my-toolbox-agent
cd my-toolbox-agent

azd ai agent init --template https://github.com/microsoft/agent-framework/blob/main/python/samples/04-hosting/foundry-hosted-agents/responses/foundry_toolbox/azure.yaml --src .
```

Follow the prompts to create or select the Foundry project and provide external inputs if requested.
For an existing Foundry project, append `--model-deployment <existing-deployment-name>` to select its
deployment explicitly. This works around the current
[Azure/azure-dev#10519 model-picker issue](https://github.com/Azure/azure-dev/issues/10519).
For a new deployment, the template declares `gpt-4.1`.

Initialization places `azure.yaml`, `main.py`, `requirements.txt`, and the `.azure` environment in
`my-toolbox-agent`. The agent's `project: .` keeps its source in that same root. Run all commands below
from this root; there is no generated `src/<agent-name>` directory. Do not initialize again after success.
For a repository checkout, work from this sample directory and run `azd ai agent init .`. Accept reuse
of the existing configuration rather than adopting a second manifest over the existing `azure.yaml`.

The project managed identity needs **Cognitive Services Language Owner** on the Language resource. See the
[identity authorization guide](https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/SUPPORTED_TOOLBOX_SCENARIOS/tools/mcp-microsoft-entra.md#step-2--authorize-the-identity).
When you grant it depends on your project:

- **Existing Foundry project:** grant the role after init and before `azd up`.
- **New Foundry project:** init only writes configuration, and provisioning creates the project and its
  identity. Run `azd provision`, grant the role, and then run `azd deploy --all` instead of `azd up`.

#### Configure external inputs

If init did not request these values, or you need to correct them, set them in the initialized
project's azd environment:

```bash
azd env set GITHUB_MCP_PAT "<your-GitHub-MCP-PAT>"
azd env set AZURE_LANGUAGE_MCP_ENDPOINT "https://<language-service>.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview"
```

If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, these
references describe the endpoint, authentication, and platform-header contract:

- [Toolbox overview](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/toolbox/toolbox.md)
- [Use toolbox in a hosted agent](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugins/azure-skills/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md)

#### Provision and deploy dependencies and agent

```bash
azd up
```

For a new Foundry project, run `azd provision`, grant the Language role to the new project identity, and
then run `azd deploy --all` instead of `azd up`. Otherwise `azd up` provisions the project/model as needed and deploys connections, toolbox, and agent in dependency
order. `azd provision` alone does not deploy the connections or toolbox. The versioned toolbox output
is mapped into the agent automatically; do not replace it with an unversioned endpoint or a
self-assignment. To inspect the deployed toolbox and endpoint:

```bash
azd ai toolbox show agent-tools
azd ai toolbox versions list agent-tools
azd env get-value TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT
```

#### Run the agent locally

Run `azd up` first. Local hosting does not create remote connections or the toolbox. Also authenticate
the local credential with `az login` (Azure CLI); `azd auth login` authenticates deployment commands.

```bash
az login
azd ai agent run
```

The agent host starts on `http://localhost:8088`. In a separate terminal, from the project root:

```bash
azd ai agent invoke --local "What tools do you have?"
```

#### Deploy changes to Foundry

After editing tools, connections, or agent code, deploy every service so the agent receives the new
versioned toolbox endpoint:

```bash
azd deploy --all
azd ai agent invoke "What tools do you have?"
```

Edit the services in `azure.yaml` rather than mutating a separately managed toolbox. You do not need
to publish a default toolbox version for this agent because it uses the deployed version's endpoint.
See [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
for the full deployment guide.

### Option 2: VS Code (Foundry Toolkit)

#### Prerequisites

1. Install [VS Code with Foundry Toolkit](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/get-started-projects-vs-code)
   and the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python).
2. Sign in to Azure in VS Code.
3. Complete CLI initialization, external inputs, identity grants, and `azd up` above before local
   testing. The Toolkit's agent-only deploy flow does not provision or update toolbox dependencies.

#### Open the initialized project

Open `my-toolbox-agent`, the directory containing `azure.yaml`, in VS Code. This sample uses the unified
configuration, not the legacy gallery flow that generates `agent.yaml`. Use the CLI template command
above to obtain this sample; do not initialize it through a legacy manifest gallery.

Create a Python 3.13 virtual environment in this directory:

```bash
python -m venv .venv
```

Select `.venv` with **Python: Select Interpreter**, open a new VS Code terminal to activate it, then run:

```bash
python -m pip install --pre -r requirements.txt
```

Copy [`.env.example`](.env.example) to `.env` and set the Foundry project endpoint, model deployment
name, and `TOOLBOX_ENDPOINT`. For the latter, use the output of
`azd env get-value TOOLBOX_AGENT_TOOLS_MCP_ENDPOINT`. Do not put the GitHub PAT in the agent's `.env`;
it belongs to the remote project connection. The agent also accepts `FOUNDRY_MODEL` as a local model override.

#### Run and debug the agent

Run `az login`, then start `python main.py` from the project root. To debug, open `main.py` and use
**Python Debugger: Debug Python File**. The host listens on `http://localhost:8088`.

Open the Command Palette (`Ctrl+Shift+P`), run **Foundry Toolkit: Open Agent Inspector**, and send
messages to the running agent.

#### Deploy to Foundry

Run `azd deploy --all` from the initialized root to deploy connections, toolbox, and agent together.
The Toolkit's agent-only deploy wizard is not a replacement for this dependency deployment.

## Finding the Entra audience for an MCP server

An Entra pass-through connection requires an **audience**, the Entra resource that the MCP server
validates tokens against. For Microsoft Foundry MCP, read its OAuth protected-resource metadata:

```bash
curl https://mcp.ai.azure.com/.well-known/oauth-protected-resource
```

The `resource` value is `https://mcp.ai.azure.com`; use it as the audience.

For connector-backed MCP servers such as Microsoft 365 / WorkIQ, the audience is published in the
Foundry Tools Catalog. Use the helper scripts in [`scripts/`](scripts/):
`./scripts/list-foundry-connectors.ps1 -ConnectorName <name>` or
`./scripts/list-foundry-connectors.sh -n <name>`. Read `AzureActiveDirectoryResourceId` (equivalently
`resourceUri`) under `properties.x-ms-connection-parameters`. Omit the connector name to list connectors.

## Troubleshooting

### A single failing MCP source can fail the whole agent

If any referenced MCP server fails during `tools/list`, the toolbox can fail the entire enumeration
and the agent cannot load its tools. A transient source failure can surface as HTTP 500 with an error
such as `tools/list failed for 1 tool source(s), succeeded for 5 tool source(s)`.

Retry transient failures. For a persistently unavailable source, remove its tool entry and unused
connection service and `uses` dependency from `azure.yaml`, then run `azd deploy --all` to update the
toolbox and agent together. Inspect deployed logs with `azd ai agent monitor` to identify the failed source.

### Entra pass-through forwards the caller's identity

The Foundry MCP connection forwards the calling user's Entra token to `https://mcp.ai.azure.com`.
The Foundry portal Agent Playground and `azd ai agent invoke` supply the developer's token, so tools
can act only on resources that user can access. Foundry MCP requires project access, not an extra license.

Local authentication uses the `az login` account; hosted authentication uses managed identity and
platform request context. A credential or a fresh Python object does not grant resource permissions.
If the effective identity has no access, tools return authorization errors.

Other MCP servers can add their own entitlement checks. Microsoft 365 / WorkIQ servers, for example,
require a **Microsoft 365 Copilot (Business Chat)** license. That requirement belongs to those servers,
not to Entra pass-through itself.

## Next steps

- [Quickstart: Create a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent)
- [Tool catalog](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/tool-catalog)
- [Manage hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-agent)
- [Basic agent](../basic/README.md)
- [Add local tools](../tools/README.md)
- [Build multi-agent workflows](../workflows/README.md)
