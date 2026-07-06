# AG-UI Dojo Server

An ASP.NET Core server that hosts a suite of AG-UI agents, one per protocol feature, behind
the [AG-UI Dojo](https://github.com/ag-ui-protocol/ag-ui) demo viewer. Each feature is exposed
as its own AG-UI endpoint via `MapAGUI`, so the Dojo front end can exercise every capability
against a real .NET agent.

> **Warning**
> The AG-UI protocol is still under development and changing. We will try to keep these
> samples updated as the protocol evolves.

## Endpoints

Each endpoint is a self-contained agent mapped with `MapAGUI("/<feature>", agent)`:

| Endpoint | Feature |
| --- | --- |
| `/agentic_chat` | Plain streaming chat |
| `/backend_tool_rendering` | Tool results rendered by the client |
| `/human_in_the_loop` | Client-approved tool calls |
| `/tool_based_generative_ui` | Tool-driven generative UI |
| `/agentic_generative_ui` | Plan/state-driven generative UI |
| `/shared_state` | Shared state snapshots and deltas |
| `/predictive_state_updates` | Streamed document edits |
| `/a2ui_fixed_schema` | **A2UI** — author-owned card layouts, agent supplies only the data |
| `/a2ui_dynamic_schema` | **A2UI** — a subagent designs the surface via the `generate_a2ui` tool |
| `/a2ui_recovery` | **A2UI** — the validate-and-retry recovery loop for invalid surfaces |
| `/a2ui_chat` | **A2UI** — zero-configuration: the client middleware injects the render tool |

The four `a2ui_*` endpoints demonstrate the
[`Microsoft.Agents.AI.AGUI.A2UI`](../../../../src/Microsoft.Agents.AI.AGUI.A2UI) toolkit. See
[A2UI/A2UICompositionGuides.cs](./A2UI/A2UICompositionGuides.cs) and
[ChatClientAgentFactory.cs](./ChatClientAgentFactory.cs) for how each agent is built.

## Configuring Environment Variables

The server runs in one of two modes, chosen by which variables are set.

**Azure OpenAI** (uses `DefaultAzureCredential` — authenticate via `az login`, Visual Studio,
or environment variables):

```powershell
$env:AZURE_OPENAI_ENDPOINT="<<your-model-endpoint>>"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o"
```

**OpenAI / OpenAI-compatible** (API key, with an optional base-URL override for a local or
proxy endpoint — useful for deterministic end-to-end tests against a mock server):

```powershell
$env:OPENAI_API_KEY="<<your-api-key>>"
$env:OPENAI_CHAT_MODEL_ID="gpt-4o"          # optional, defaults to gpt-4o
$env:OPENAI_BASE_URL="http://localhost:8000/v1"   # optional
```

If `AZURE_OPENAI_ENDPOINT` is set the server uses Azure mode; otherwise it falls back to
`OPENAI_API_KEY`.

## Running the Sample

```bash
cd AGUIDojoServer
dotnet run --urls "http://localhost:8016"
```

Point the AG-UI Dojo's `microsoft-agent-framework-dotnet` integration at the server's URL
(`http://localhost:8016` by default), then open any feature page to interact with the
matching endpoint. The endpoints are plain AG-UI servers, so they can also be driven directly
over HTTP POST with a `RunAgentInput` body (see the
[AG-UI Client and Server sample](../README.md) for the request shape).

> **Note**
> When deploying multi-user, register a session-isolation key provider (see the commented
> `UseClaimsBasedSessionIsolation` call in [Program.cs](./Program.cs)); otherwise sessions are
> shared across callers.
