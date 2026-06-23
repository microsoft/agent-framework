# SimpleAgent

A generic, agent-agnostic chat REPL for any hosted Foundry agent. Point it at a running
`Hosted-*` agent via `AZURE_AI_AGENT_NAME`, and it builds a `FoundryAgent` against that agent's
per-agent OpenAI endpoint and streams replies. This is the shared client that `Hosted-Toolbox`,
`Hosted-Toolbox-AuthPaths`, and `Hosted-McpTools` reference for their end-to-end demos.

It knows nothing about the agent's tools, toolboxes, files, or auth — those are entirely the
server's concern. Changing which agent you chat with is just a different `AZURE_AI_AGENT_NAME`.
See [`../README.md`](../README.md) for why these client REPLs exist at all.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- A running hosted agent (any `Hosted-*` sample, locally via `dotnet run` or deployed to Foundry)
- Azure CLI logged in (`az login`)

## Configuration

```env
FOUNDRY_PROJECT_ENDPOINT=https://<host>/api/projects/<project>
AZURE_AI_AGENT_NAME=<registered-server-side-agent-name>
```

Both are required. `FOUNDRY_PROJECT_ENDPOINT` is the Foundry project endpoint URL and
`AZURE_AI_AGENT_NAME` is the registered server-side agent name. The sample builds the per-agent
OpenAI endpoint URL (`{FOUNDRY_PROJECT_ENDPOINT}/agents/{AZURE_AI_AGENT_NAME}/endpoint/protocols/openai`)
from these.

## Run

Against a local Hosted-Toolbox agent listening on `http://localhost:8088`:

```powershell
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
$env:FOUNDRY_PROJECT_ENDPOINT = "http://localhost:8088/api/projects/local"
$env:AZURE_AI_AGENT_NAME = "hosted-toolbox-agent"
dotnet run
```

When the project endpoint is `http://`, the client presents it as `https://` to satisfy the
bearer-token TLS check, then rewrites the scheme back to `http://` right before transport
(local-development only).

## End-to-end demo

With a hosted agent running:

```text
══════════════════════════════════════════════════════════
Simple Agent Sample
Connected to: https://localhost:8088/api/projects/local/agents/hosted-toolbox-agent/endpoint/protocols/openai
Type a message or 'quit' to exit
══════════════════════════════════════════════════════════

You> What tools do you have available, and what can they do?
Agent> I have the following tools from the toolbox: ...

You> quit
Goodbye!
```

The client only sent a chat prompt; the agent resolved its toolbox tools server-side and answered.
