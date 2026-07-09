# Using-Samples — client REPLs for the hosted agents

This folder holds small **client** console apps that connect to the **server** samples in the
sibling `Hosted-*` folders. Each `Hosted-*` project is an agent you host (locally with
`dotnet run` or deployed to Foundry); the projects here are the thing that *talks* to them.

## Why these exist

A hosted Foundry agent is an HTTP server, not a chat UI. It exposes only the per-agent OpenAI
endpoint shape that the platform routes to:

```
{FOUNDRY_PROJECT_ENDPOINT}/agents/{AZURE_AI_AGENT_NAME}/endpoint/protocols/openai
```

There is no built-in console to poke it with. To actually exercise an agent — send a prompt,
watch it call its tools, read the streamed answer — you need a client that builds a
`FoundryAgent` against that endpoint and drives a conversation. That is all these REPLs do:

1. Read `FOUNDRY_PROJECT_ENDPOINT` + `AZURE_AI_AGENT_NAME` from the environment.
2. Derive the per-agent OpenAI endpoint URL.
3. `AIProjectClient(...).AsAIAgent(agentEndpoint)` → `FoundryAgent`.
4. Loop: read a line, `RunStreamingAsync`, print the streamed reply.

The client is deliberately dumb. It knows nothing about tools, files, toolboxes, or auth — all
of that is the hosted agent's concern on the server side. Swapping which agent you chat with is
just a matter of changing `AZURE_AI_AGENT_NAME`.

## Local HTTP dev

When the target is a local `http://localhost:8088` dev server, the REPLs install a small
`HttpSchemeRewritePolicy`: `AIProjectClient`/`BearerTokenPolicy` require HTTPS, so the client
presents the endpoint as `https://` to satisfy the TLS check, then rewrites the scheme back to
`http://` right before the request hits the wire. This is local-development only.

## The clients

| Client | What it targets | Notes |
|---|---|---|
| [`SimpleAgent/`](./SimpleAgent/) | Any hosted agent | Generic, agent-agnostic REPL. Point it at any `Hosted-*` server via `AZURE_AI_AGENT_NAME`. Used by `Hosted-Toolbox`, `Hosted-Toolbox-AuthPaths`, and `Hosted-McpTools`. |
| [`SessionFilesClient/`](./SessionFilesClient/) | [`Hosted-Files`](../Hosted-Files/) | Same shape as `SimpleAgent`, framed around the bundled-files demo. |

## Configuration (common to all clients)

```env
FOUNDRY_PROJECT_ENDPOINT=https://<host>/api/projects/<project>
AZURE_AI_AGENT_NAME=<registered-server-side-agent-name>
```

Both are required. Authenticate with `az login` before running. See each client's own README for
its end-to-end walkthrough.
