# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery and hosted using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Creating a Foundry Toolbox

You can create a Foundry Toolbox by code. Refer to this sample for an example: [Foundry Toolbox CRUD Sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/hosted_agents/sample_toolboxes_crud.py).

You can also create a Foundry Toolbox in the Foundry portal. Read more about it [in the Foundry toolbox documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox).

> If you set up a project with this sample and provision the resources using `azd provision`, a Foundry Toolbox will be created with the specified tools in [`agent.manifest.yaml`](agent.manifest.yaml).

### Authentication Methods

You can connect to MCP servers in Foundry Toolbox that use different authentication methods. This sample demonstrates the following authentication methods:

- **No authentication**: The tool does not require any authentication. The agent can invoke the tool without providing any credentials. Sample MCP server: `https://gitmcp.io/Azure/azure-rest-api-specs`
- **Key-based authentication**: The tool requires a key to authenticate. Sample MCP server: `https://api.githubcopilot.com/mcp` (GitHub MCP server) with a Personal Access Token (PAT) for authentication.
- **OAuth2 authentication (managed)**: The tool requires OAuth2 to authenticate. Sample MCP server: `https://api.githubcopilot.com/mcp` (GitHub MCP server) with OAuth2 for authentication.
- **Agent identity authentication**: The tool requires an agent identity token to authenticate. Sample MCP server: `https://{foundry-resource-name}.cognitiveservices.azure.com/language/mcp?api-version=2025-11-15-preview` (Azure Language MCP server) with agent identity for authentication.
- **Entra Pass-through authentication**: The tool requires an Entra pass-through token to authenticate. Sample MCP server: Microsoft Outlook MCP server with Entra pass-through for authentication.

> Definitions of these authentication methods can be found in the [agent.manifest.yaml](agent.manifest.yaml) file in this sample.

There are also Non-MCP tools in the toolbox that support different authentication methods. Learn more at the [Foundry sample repository](https://github.com/microsoft-foundry/foundry-samples/tree/main/samples/python/toolbox/azd#supported-scenarios).

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via `MCPStreamableHTTPTool`, which discovers and invokes the toolbox's tools over MCP at runtime. The endpoint URL is provided through the `FOUNDRY_TOOLBOX_ENDPOINT` environment variable.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

An extra environment variable must be set to point to the toolbox MCP endpoint. You can provide it in one of two ways:

**Option A – Set `FOUNDRY_TOOLBOX_ENDPOINT` directly** (recommended for local development):

```bash
export FOUNDRY_TOOLBOX_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>/toolsets/<name>/mcp?api-version=v1"
```

Or in PowerShell:

```powershell
$env:FOUNDRY_TOOLBOX_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>/toolsets/<name>/mcp?api-version=v1"
```

**Option B – Set `TOOLBOX_NAME`** (used automatically by the Foundry hosting scaffolding after `azd provision`):

The agent derives the endpoint at runtime as:
```
{FOUNDRY_PROJECT_ENDPOINT}/toolsets/{TOOLBOX_NAME}/mcp?api-version=v1
```

When deployed via `azd provision`, the scaffolding injects `TOOLBOX_NAME=agent-tools` and `FOUNDRY_PROJECT_ENDPOINT` automatically from the provisioned resources declared in [`agent.manifest.yaml`](agent.manifest.yaml).

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What tools do you have?"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
