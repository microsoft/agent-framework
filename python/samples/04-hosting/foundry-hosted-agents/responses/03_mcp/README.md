# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that connects to a **remote MCP server** (GitHub) for tool discovery and hosted using the **Responses protocol**. Instead of defining tools locally, the agent discovers and invokes tools at runtime from an MCP-compatible endpoint — in this case, the GitHub Copilot MCP server. This enables dynamic tool integration without redeployment.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It registers a remote MCP tool pointing at `https://api.githubcopilot.com/mcp/`, authenticating with a GitHub Personal Access Token (PAT). When the model decides to call a tool, the framework forwards the call to the MCP server and returns the result to the model for the final reply.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details. Use this README for sample queries you can send to the agent.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. For example:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" -d '{"input": "List all the repositories I own on GitHub."}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.