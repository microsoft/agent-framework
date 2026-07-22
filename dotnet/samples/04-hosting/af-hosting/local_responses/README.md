# Hosting Responses Agent (client / server)

A client/server pair showing how to expose an `AIAgent` over the OpenAI Responses protocol from an
ASP.NET Core route you write, and how to consume it from .NET two different ways.

```
local_responses/
├── Server/   # exposes POST /responses using the OpenAIResponses helpers
└── Client/   # consumes it two ways: CC (IChatClient) and MAF (AIAgent)
```

## Server

The server owns routing, authentication, and session storage. The framework provides only the protocol
conversion via `OpenAIResponses` (`ToAgentRunRequest`, `GetSessionStoreId`, `WriteResponse` /
`WriteResponseStreamAsync`), instead of the batteries-included `MapOpenAIResponses` endpoint. The agent has a
deterministic `lookup_weather` tool. Session continuity uses an in-memory `AgentSessionStore` directly. It
binds to `http://localhost:5000`.

See [Server/README.md](Server/README.md).

## Client

A single program that runs the same three-turn conversation twice, once per consumption path:

- **CC** — a plain `Microsoft.Extensions.AI.IChatClient` (the lower-level chat-client path).
- **MAF** — a Microsoft Agent Framework `AIAgent` + `AgentSession` (the higher-level agent path).

Both point at the same server. The third turn asks about the first turn, proving multi-turn session
continuity across the rotating response-id chain.

See [Client/README.md](Client/README.md).

## Run

Start the server in one shell:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<your-resource>.services.ai.azure.com/api/projects/<your-project>"
export FOUNDRY_MODEL="gpt-5.4-mini"   # optional, defaults to gpt-5.4-mini
dotnet run --project Server
```

Then run the client in another shell:

```bash
dotnet run --project Client
```

The client defaults to `http://localhost:5000`; override with `RESPONSES_SERVER_URL`.

## Security note

`OpenAIResponses.GetSessionStoreId(...)` returns an untrusted candidate key. The server's `Authorize(...)` is a
placeholder; a real application must authenticate the caller and authorize/bind the id to the authenticated
principal before using it as a session key. For multi-user hosts, scope the store with
`IsolationKeyScopedAgentSessionStore`.
