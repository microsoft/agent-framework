# SessionFilesClient

A thin chat REPL that connects to a deployed [`Hosted-Files`](../../Hosted-Files/) agent via `FoundryAgent` and lets you ask questions whose answers come from the files bundled with that agent. Same shape as [`SimpleAgent`](../SimpleAgent/) — point it at an `AGENT_ENDPOINT`, build a `FoundryAgent`, run.

The agent's container-side `ListFiles` and `ReadFile` tools surface the bundled file contents to the model. The client knows nothing about files; that is entirely the agent's concern.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- A running [`Hosted-Files`](../../Hosted-Files/) agent (locally via `dotnet run` or deployed to Foundry)
- Azure CLI logged in (`az login`)

## Configuration

```env
FOUNDRY_PROJECT_ENDPOINT=https://<host>/api/projects/<project>
AZURE_AI_AGENT_NAME=hosted-files
```

Both are required. `FOUNDRY_PROJECT_ENDPOINT` is the Foundry project endpoint URL and `AZURE_AI_AGENT_NAME` is the registered server-side agent name. The sample builds the per-agent OpenAI endpoint URL from these.

## Run

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Using-Samples/SessionFilesClient
$env:FOUNDRY_PROJECT_ENDPOINT = "http://localhost:8088/api/projects/local"
$env:AZURE_AI_AGENT_NAME = "hosted-files"
dotnet run
```

## End-to-end demo

With the [`Hosted-Files`](../../Hosted-Files/) agent running:

```text
══════════════════════════════════════════════════════════
Session Files Client
Connected to: http://localhost:8088/
Try: "Give me the total revenue in the contoso file."
Type a message or 'quit' to exit
══════════════════════════════════════════════════════════

You> Give me the total revenue in the contoso file.
Agent> The contoso file reports total revenue of "$1,482.6M".

You> quit
Goodbye!
```

The agent looked at its bundled files via `ListFiles`, picked `contoso_q1_2026_report.txt`, called `ReadFile`, and quoted the figure verbatim. The client only sent a chat prompt.
