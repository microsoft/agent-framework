# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that uses **Foundry Toolbox** for tool discovery and hosted using the **Responses protocol**. Foundry Toolbox is a managed tool registry in Microsoft Foundry that lets you define tools centrally and share them across agents.

## Creating a Foundry Toolbox

You can create a Foundry Toolbox by code. Refer to this sample for an example: [Foundry Toolbox CRUD Sample](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/hosted_agents/sample_toolboxes_crud.py).

You can also create a Foundry Toolbox in the Foundry portal. Read more about it [in the Foundry toolbox documentation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox).

> If you set up a project with this sample and provision the resources using `azd provision`, a Foundry Toolbox will be created with the specified tools in [`agent.manifest.yaml`](agent.manifest.yaml).

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It loads a named Foundry Toolbox via `client.get_toolbox(name)` — the toolbox is a server-side bundle of tool configurations (e.g., `code_interpreter`, `web_search`) defined in the Foundry portal or by `azd provision`. Omitting `version` resolves the toolbox's current default version at runtime.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

An extra environoment variable `TOOLBOX_NAME` must be set to the name of the Foundry Toolbox that the agent should load at runtime. This allows the agent host to dynamically retrieve the correct toolbox from Foundry when it starts. Run the following:

```bash
export TOOLBOX_NAME="<your-toolbox-name>"
```

Or in PowerShell:

```powershell
$env:TOOLBOX_NAME="<your-toolbox-name>"
```

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "What tools do you have?"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.
