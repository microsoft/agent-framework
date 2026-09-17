# SimpleAgent

A generic, agent-agnostic chat REPL for any hosted Foundry agent. Point it at a running
`Hosted-*` agent and it streams replies. This is the shared client that `Hosted-Toolbox`,
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
AZURE_AI_AGENT_NAME=<registered-server-side-agent-name>
FOUNDRY_PROJECT_ENDPOINT=https://<host>/api/projects/<project>
```

`AZURE_AI_AGENT_NAME` is always required. `FOUNDRY_PROJECT_ENDPOINT` is the Foundry project
endpoint URL, required only when you target the deployed agent.

## Run

```powershell
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SimpleAgent
$env:AZURE_AI_AGENT_NAME = "hosted-chat-client-agent"
dotnet run
```

On startup the client asks which agent to chat with:

```text
Which agent do you want to chat with?
  [1] Foundry (deployed agent)   [default]
  [2] Local    (dotnet run, http://localhost:8088)
Choice:
```

Pass `--local` or `--remote` to answer up front and skip the prompt, which is what scripted runs
need:

```
dotnet run -- --local
dotnet run -- --remote
```

This mirrors the `--local` flag on `azd ai agent invoke`. Use local while a `Hosted-*` sample is
running with `dotnet run`; use remote to reach the agent deployed to Foundry.

The two choices differ only in how the agent is built:

| Target | How the client reaches it |
|--------|---------------------------|
| Local | An `OpenAIClient` pointed at `http://localhost:8088`, then `GetResponsesClient().AsAIAgent(...)`. That hits the standard `POST /responses` route the local server already serves. The model id and api key are placeholders: the server runs its own agent and ignores both, but the SDK requires them to shape the request. |
| Foundry | An `AIProjectClient` plus the agent's per-agent endpoint (`{projectEndpoint}/agents/{AZURE_AI_AGENT_NAME}/endpoint/protocols/openai`), which the platform routes to the container's `/responses` route. |

The Foundry path also works against a local server that maps the per-agent route: set
`FOUNDRY_PROJECT_ENDPOINT` to an `http://` URL and the client installs a scheme-rewrite policy so
the bearer-token pipeline accepts it. See [Local HTTP dev](../README.md#local-http-dev).

## End-to-end demo

With a hosted agent running:

```text
══════════════════════════════════════════════════════════
Simple Agent Sample
Connected to: http://localhost:8088
Type a message or 'quit' to exit
══════════════════════════════════════════════════════════

You> What tools do you have available, and what can they do?
Agent> I have the following tools from the toolbox: ...

You> quit
Goodbye!
```

The client only sent a chat prompt; the agent resolved its toolbox tools server-side and answered.

## Troubleshooting

**`azd ai agent invoke` fails with `404 not_found: Conversation '<id>' not found`**

`azd` saves the session and conversation per agent and reuses them on the next invoke. Once the
agent is redeployed, deleted, or restarted, that saved conversation no longer exists on the server,
so every following invoke fails even though the agent itself is healthy. Start a fresh one:

```
azd ai agent invoke --new-conversation "Hello!"
```

Add `--new-session` as well if the failure persists.
