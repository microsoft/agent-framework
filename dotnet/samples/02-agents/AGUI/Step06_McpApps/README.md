# Step06_McpApps — MCP Apps with AG-UI

This sample demonstrates **MCP Apps**: a mechanism for attaching interactive HTML UI components to MCP tools. When an MCP tool is invoked, the AG-UI host passes the associated `ui://` resource URI alongside the tool result so that a capable client can render the HTML app in-place.

If you want the broader conceptual model for MCP Apps before diving into this sample, see the official [MCP Apps Overview](https://modelcontextprotocol.io/extensions/apps/overview).

## What This Sample Demonstrates

### McpServer (`McpServer/`)

An ASP.NET Core MCP server that exposes a `get-time` tool together with a bundled HTML UI:

- Registering MCP tools and resources with `AddMcpServer()`
- Attaching a UI resource to a tool via `[McpMeta("ui", JsonValue = ...)]`
- Exposing an HTML app as an MCP resource with MIME type `text/html;profile=mcp-app`
- Serving the bundled single-file HTML app from the `dist/` directory

### Server (`Server/`)

An AG-UI server that bridges the MCP server to AG-UI clients:

- Connecting to the MCP server with `McpClient` and listing its tools
- Wrapping an OpenAI chat client as an `AIAgent` with the MCP tools attached
- Exposing the agent over HTTP with `MapAGUI`
- Handling proxied MCP `resources/read` and `tools/call` requests through the `MapAGUI` `ProxiedResultResolver` overload

### Client (`Client/`)

A console client that connects to the AG-UI server. Demonstrates:

- Connecting with `AGUIChatClient`
- Streaming responses with `RunStreamingAsync`
- Displaying session and run metadata, text content, and errors

> **Note:** The console client cannot render the MCP App — HTML rendering requires a browser frontend. However, the AG-UI server correctly emits the `ACTIVITY_SNAPSHOT` event containing the `ui://` resource URI and the full tool result. A browser-based AG-UI client would receive exactly that information and use it to load and display the HTML app.

### Frontend MCP App (`McpServer/get-time.ts`)

A small TypeScript web app compiled with Vite that runs inside the MCP host:

- Using `@modelcontextprotocol/ext-apps` to establish communication with the MCP host
- Receiving the initial tool result via `app.ontoolresult`
- Proactively calling server tools from UI interactions with `app.callServerTool`
- Bundling as a self-contained single HTML file using `vite-plugin-singlefile`

## Architecture

```text
┌─────────────┐       AG-UI (SSE)     ┌────────────────┐     MCP (HTTP)     ┌─────────────────┐
│   Client    │ ────────────────────> │     Server     │ ─────────────────> │    McpServer    │
│  (console)  │     port 5253         │   port 5253    │     port 5177      │   port 5177     │
└─────────────┘                       └────────────────┘                    └─────────────────┘
```

## Prerequisites

- .NET 10.0 or later
- An OpenAI API key

```bash
export OPENAI_API_KEY="sk-..."
```

## Running the Sample

### 1. Start the McpServer

```bash
cd Step06_McpApps/McpServer
dotnet run
```

The MCP server starts at `http://localhost:5177` and exposes:

- `GET /` — health check
- `POST /mcp` — MCP endpoint (stateless HTTP transport)

### 2. Start the AG-UI Server

```bash
cd Step06_McpApps/Server
dotnet run
```

The server starts at `http://localhost:5253`. It connects to the McpServer, wraps GPT-4o as an AI agent with the MCP tools, and exposes an AG-UI endpoint at `/`.

### 3. Run the Client

```bash
cd Step06_McpApps/Client
AGUI_SERVER_URL=http://localhost:5253 dotnet run 
```

The client connects to `http://localhost:5253` by default. Type messages and press Enter. Type `:q` or `quit` to exit. Try asking: *"What time is it?"*

## Rebuilding the Frontend (Optional)

A pre-built `dist/get-time.html` is included. To rebuild from source after editing `get-time.ts` or `get-time.html`:

```bash
cd Step06_McpApps/McpServer
npm install
npm run build
```

This bundles `get-time.ts` and inlines all assets into `dist/get-time.html` as a single self-contained file.

## Key Concepts

The sample follows the core MCP Apps pattern described in the [MCP Apps Overview](https://modelcontextprotocol.io/extensions/apps/overview): a tool advertises a UI resource, the host loads that `ui://` resource, and the app communicates back through the host rather than calling the server directly from the browser.

### Tool ↔ UI Binding

The `[McpMeta("ui", ...)]` attribute on a tool method points to an MCP resource URI:

```csharp
[McpServerTool(Name = "get-time"), Description("Gets the current time.")]
[McpMeta("ui", JsonValue = """{"resourceUri":"ui://get-time.html"}""")]
public async Task<IEnumerable<ContentBlock>> GetTimeAsync() { ... }
```

### MCP App Resource

The HTML app is exposed as a resource with the special MIME type `text/html;profile=mcp-app`:

```csharp
[McpServerResource(UriTemplate = "ui://get-time.html", MimeType = "text/html;profile=mcp-app")]
public async Task<string> GetTimeUIResourceAsync() =>
    await File.ReadAllTextAsync("./dist/get-time.html");
```

### App SDK Communication

Inside the frontend, `@modelcontextprotocol/ext-apps` handles the messaging bridge between the HTML app and the MCP host:

```typescript
const app = new App({ name: "Get Time App", version: "1.0.0" });
app.connect();

// Receive initial tool result pushed by the host
app.ontoolresult = (result) => { ... };

// Proactively call tools from UI events
const result = await app.callServerTool({ name: "get-time", arguments: {} });
```

## AG-UI Protocol: MCP Apps in the Event Stream

When the Server forwards an MCP App tool invocation, the SSE stream contains this event sequence:

```text
RUN_STARTED
TOOL_CALL_START
TOOL_CALL_ARGS       (one or more, streaming JSON delta)
TOOL_CALL_END
TOOL_CALL_RESULT
ACTIVITY_SNAPSHOT    ← carries the MCP App resource URI and tool result
RUN_FINISHED
```

The `ACTIVITY_SNAPSHOT` event is the key addition over a plain tool call. Its `content` object tells the client which HTML app to load and passes the tool result into it:

```jsonc
{
  "type": "ACTIVITY_SNAPSHOT",
  "messageId": "<uuid>",
  "activityType": "mcp-apps",
  "replace": true,
  "content": {
    "resourceUri": "ui://get-time.html",   // MCP App resource to render
    "result": {                            // Full MCP tool result
      "content": [{ "type": "text", "text": "..." }]
    },
    "toolInput": {}                        // Arguments passed to the tool
  }
}
```

### `ACTIVITY_SNAPSHOT` Field Reference

| Field | Type | Notes |
| --- | --- | --- |
| `activityType` | `"mcp-apps"` | Identifies this as an MCP App activity |
| `replace` | boolean | `true` replaces any previous snapshot for this `messageId` |
| `content.resourceUri` | string | MCP App resource URI, e.g. `"ui://get-time.html"` |
| `content.result` | object | Full MCP tool result: `{ content: [{ type, text }] }` |
| `content.toolInput` | object | Arguments passed to the tool |

## AG-UI Protocol: Proxied MCP Resource Reads

After the client receives the `ACTIVITY_SNAPSHOT` containing the `resourceUri`, a capable host (e.g. CopilotKit) fetches the actual resource HTML by sending a second `agent/run` request. The resource URI alone is not enough — the client needs the HTML content to render the app.

### Proxied Request

The client embeds the MCP `resources/read` call inside `forwardedProps.__proxiedMCPRequest`:

```jsonc
{
  "threadId": "<thread-id>",
  "runId": "<run-id>",
  "messages": [...],              // conversation history
  "forwardedProps": {
    "__proxiedMCPRequest": {
      "serverHash": "<hash>",
      "serverId": "<server-id>",
      "method": "resources/read",
      "params": {
        "uri": "ui://get-time.html"
      }
    }
  }
}
```

This JSON is the plain AG-UI POST body used by the Step06 sample server. Some hosts, including CopilotKit, may wrap the same body inside an outer `{"method":"agent/run","params":...,"body":...}` envelope.

The presence of `forwardedProps.__proxiedMCPRequest` signals that this run is a proxy call, not a new LLM turn. The agent should **not** be invoked.

Hosts may include additional proxy metadata such as `serverHash` and `serverId`. Those fields are host-specific. The Step06 sample ignores them and only uses `method` plus `params.uri`, while some hosts may require them.

### Expected Response

The server should short-circuit the agent run and respond with exactly two SSE events:

```text
RUN_STARTED
RUN_FINISHED   ← carries result.contents with the resource HTML
```

```jsonc
// RUN_FINISHED
{
  "type": "RUN_FINISHED",
  "runId": "<run-id>",
  "threadId": "<thread-id>",
  "result": {
    "contents": [
      {
        "uri": "ui://get-time.html",
        "mimeType": "text/html;profile=mcp-app",
        "text": "<!DOCTYPE html>..."
      }
    ]
  }
}
```

### Server Implementation

The server (`Server/Program.cs`) handles both paths on the same AG-UI endpoint:

1. **Normal agent runs** — the sample calls `app.MapAGUI("/", agent, async (forwardedProperties, cancellationToken) => ...)`, which binds to the `ProxiedResultResolver` overload. When no proxied result is resolved, the AG-UI hosting layer converts the request into chat messages, runs the `AIAgent`, and streams the normal AG-UI SSE event sequence back to the client.

2. **Resolver invocation guard** — the `MapAGUI` overload only invokes the `ProxiedResultResolver` when `forwardedProps` is a non-empty JSON object. Missing, `null`, `undefined`, or empty-object forwarded properties fall through directly to the normal agent path.

3. **Proxied MCP resource reads** — when the resolver is invoked and `forwardedProps.__proxiedMCPRequest.method == "resources/read"`, the sample extracts `params.uri`, calls `mcpClient.ReadResourceAsync(uri)`, and maps that MCP response into the `RUN_FINISHED.result.contents` payload expected by AG-UI clients.

4. **Proxied MCP tool calls** — when `forwardedProps.__proxiedMCPRequest.method == "tools/call"`, the sample extracts `params.name` plus `params.arguments`, calls `mcpClient.CallToolAsync(...)`, and maps that MCP `CallToolResult` into the `RUN_FINISHED.result.content` payload expected by AG-UI clients and MCP App hosts.

5. **Minimal proxy SSE response** — the hosting layer still emits exactly two events:

- `RUN_STARTED`
- `RUN_FINISHED`, with `result.contents` for proxied `resources/read` and `result.content` for proxied `tools/call`

This keeps proxied resource fetches and in-app tool invocations out of the agent loop while preserving the same `/` endpoint shape expected by AG-UI clients and hosts such as CopilotKit, without inlining custom endpoint logic into the sample.

## AG-UI Protocol: Proxied MCP Tool Calls from the Loaded App

Once the host has fetched and rendered the MCP App HTML, the app can initiate further MCP calls through the same AG-UI endpoint. In this sample, the frontend uses `app.callServerTool({ name: "get-time", arguments: {} })` to issue a fresh `tools/call` request back to the MCP server.

Just like proxied `resources/read`, this is a proxy operation, not a new LLM turn. The AG-UI host forwards the MCP request shape inside `forwardedProps.__proxiedMCPRequest`, and the server should short-circuit the agent and call the MCP server directly.

### Proxied Tool Call Request

The request shape below is the plain AG-UI body sent after the app is already loaded:

```jsonc
{
  "threadId": "<thread-id>",
  "runId": "<run-id>",
  "tools": [],
  "context": [],
  "state": {},
  "messages": [
    { "id": "<user-id>", "role": "user", "content": "what time is it?" },
    {
      "id": "<assistant-id>",
      "role": "assistant",
      "toolCalls": [
        {
          "id": "<tool-call-id>",
          "type": "function",
          "function": { "name": "get-time", "arguments": "{}" }
        }
      ]
    },
    {
      "id": "<tool-result-id>",
      "toolCallId": "<tool-call-id>",
      "role": "tool",
      "content": "2026-04-11T09:54:05.2880570Z"
    }
  ],
  "forwardedProps": {
    "__proxiedMCPRequest": {
      "serverHash": "<hash>",
      "serverId": "<server-id>",
      "method": "tools/call",
      "params": {
        "name": "get-time",
        "arguments": {}
      }
    }
  }
}
```

Some hosts, including CopilotKit, may wrap this AG-UI body inside an outer `{"method":"agent/run","params":...,"body":...}` envelope. The Step06 sample server itself accepts the plain AG-UI body shown above.

The conversation history is host-managed context. The critical signal is still `forwardedProps.__proxiedMCPRequest`: the agent should not run, and the server should proxy the embedded MCP call directly.

### Expected Tool Call Response

The server again emits only the minimal proxy SSE envelope:

```text
RUN_STARTED
RUN_FINISHED   ← carries result.content with the proxied tool result
```

```jsonc
// RUN_FINISHED
{
  "type": "RUN_FINISHED",
  "runId": "<run-id>",
  "threadId": "<thread-id>",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "2026-04-11T09:54:12.0752760Z"
      }
    ]
  }
}
```

Unlike proxied `resources/read`, the `RUN_FINISHED.result` payload follows MCP `CallToolResult` shape, so text tool output appears under `result.content` rather than `result.contents`.

## Conformance Tests

[Tests/ConformanceTests.cs](Tests/ConformanceTests.cs) covers integration-level concerns that cannot be reached by unit tests. All AG-UI protocol output behaviour (event ordering, field values, wire format) is verified by the unit tests in `Microsoft.Agents.AI.AGUI.UnitTests`.

### Running against the sample AG-UI server

Both the McpServer (port 5177) and the AG-UI Server (port 5253) must be running before executing the tests.

```bash
cd Step06_McpApps/Tests
dotnet test
```

### Running against a CopilotKit endpoint

The tests auto-detect whether the target host expects a plain AG-UI body or a CopilotKit-style envelope (`{"method":"agent/run","params":{"agentId":"..."},"body":{...}}`). Override `AG_UI_HOST` to point at any compatible host:

```bash
cd Step06_McpApps/Tests
AG_UI_HOST=http://localhost:3000/api/copilotkit dotnet test
```

The detection works by sending a minimal probe request (empty `messages` array, no LLM call) before the first real test. A `200 text/event-stream` response means direct format; any non-success response falls back to the CopilotKit-style envelope, with `"default"` used as the agent ID. A common case is CopilotKit returning `400` with a missing-method error for the direct-format probe. Set `AG_UI_AGENT_ID` to override the agent ID explicitly.

When targeting CopilotKit, the `serverHash` and `serverId` values used in proxied resource-read and proxied tool-call requests are auto-discovered from the first real tool call, typically from CopilotKit-specific data associated with the emitted `ACTIVITY_SNAPSHOT` flow. These values are not part of the standard AG-UI `ACTIVITY_SNAPSHOT` fields documented above, so no manual configuration is needed when the host provides them.

### Cancellation

All tests are linked to the test runner's cancellation token. Pressing Ctrl+C (or using the IDE's stop button) aborts all in-flight HTTP requests immediately rather than waiting for the 60-second per-test timeout to expire.

### Test reference

| # | Test | What it verifies |
| --- | --- | --- |
| 1 | `HttpResponse_HasContentType_TextEventStream` | ASP.NET Core hosting layer emits `Content-Type: text/event-stream` |
| 2 | `AskingWhatTimeIsIt_CausesToolCallStart_ForGetTime` | Live LLM routes a natural-language time query to the `get-time` MCP tool |
| 3 | `ProxiedResourceRead_EmitsOnlyRunStartedAndRunFinished` | Proxied `resources/read` emits exactly `RUN_STARTED` + `RUN_FINISHED` — no agent events |
| 4 | `ProxiedResourceRead_RunFinished_HasResultContents` | `RUN_FINISHED` carries `result.contents` with at least one entry |
| 5 | `ProxiedResourceRead_RunFinished_ResourceUri_MatchesRequest` | `result.contents[0].uri` echoes the requested resource URI |
| 6 | `ProxiedResourceRead_RunFinished_MimeType_IsMcpApp` | `result.contents[0].mimeType` is `text/html;profile=mcp-app` |
| 7 | `ProxiedResourceRead_RunFinished_ResourceText_IsNonEmpty` | `result.contents[0].text` contains the actual HTML |
| 8 | `ProxiedResourceRead_RunFinished_EchoesRunId` | `RUN_FINISHED.runId` matches the `runId` from the request |
| 9 | `ProxiedToolCall_EmitsOnlyRunStartedAndRunFinished` | Proxied `tools/call` emits exactly `RUN_STARTED` + `RUN_FINISHED` — no agent events |
| 10 | `ProxiedToolCall_RunFinished_HasResultContent` | `RUN_FINISHED` carries `result.content` with at least one entry |
| 11 | `ProxiedToolCall_RunFinished_ResultContainsTextContent` | `result.content[0]` is a non-empty text content block |
| 12 | `ProxiedToolCall_RunFinished_EchoesRunId` | `RUN_FINISHED.runId` matches the `runId` from the proxied `tools/call` request |
