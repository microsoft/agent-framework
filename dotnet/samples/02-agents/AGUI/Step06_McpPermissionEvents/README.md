# Step06: AG-UI Permission Events for MCP Tool Calls

This sample demonstrates how **MCP tool calls** triggered by the GitHub Copilot SDK are surfaced as AG-UI protocol events, enabling:

1. **Tool Call Visibility** — Clients see `TOOL_CALL_START/ARGS/END/RESULT` events for every MCP tool execution
2. **Human-in-the-Loop Approval** — Clients can approve or deny MCP tool calls via the AG-UI protocol before execution proceeds

## Architecture

```
┌──────────────┐   AG-UI SSE    ┌──────────────────┐   Copilot SDK   ┌───────────────┐
│  Any AG-UI   │◄──────────────►│  .NET Backend    │◄──────────────►│ GitHub Copilot │
│  Client      │  TOOL_CALL_*   │  MapAGUI()       │  permission.    │ + MCP Server   │
│              │  CUSTOM events │  /approve POST   │  requested      │                │
│  Approve/    │                │  GitHubCopilot   │                │  Tool exec     │
│  Deny UI     │                │  Agent           │                │  happens here  │
└──────────────┘                └──────────────────┘                └───────────────┘
```

## Prerequisites

- .NET 10 SDK or later
- GitHub Copilot CLI installed and in PATH
- An MCP server to connect to

## AG-UI Events Emitted

### Phase 1: Tool Call Visibility (automatic)

When `OnPermissionRequest` is set on `SessionConfig`, every permission request emits:

| AG-UI Event | When |
|---|---|
| `TOOL_CALL_START` | Permission request received — includes tool name and ID |
| `TOOL_CALL_ARGS` | Arguments (permission kind, metadata) serialized as JSON |
| `TOOL_CALL_END` | Args fully transmitted |
| `TOOL_CALL_RESULT` | Permission decision result (e.g., "approved", "denied-interactively-by-user") |

### Phase 2: Human-in-the-Loop (via PendingApprovalStore)

When the `PendingApprovalStore` is configured (automatic with `MapAGUI`), additional events appear:

| AG-UI Event | When |
|---|---|
| `CUSTOM` name=`tool_approval_requested` | Client should show approve/deny UI. Payload: `{ requestId, toolCallId, toolCallName, kind }` |
| `CUSTOM` name=`tool_approval_completed` | Approval resolved. Payload: `{ requestId, toolCallId, result }` |

The client responds by POSTing to `/{pattern}/approve`:
```json
{ "requestId": "<from tool_approval_requested>", "approved": true }
```

## Server Setup

### Minimal (Phase 1 — Visibility Only)

```csharp
using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.GitHub.Copilot;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddAGUI();

var app = builder.Build();

// Enable trace logging so [AGUI-Permission] and [AGUI-SSE] logs appear in console
System.Diagnostics.Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener());

await using var copilotClient = new CopilotClient();
await copilotClient.StartAsync();

var sessionConfig = new SessionConfig
{
    McpServers = new Dictionary<string, object>
    {
        ["my-mcp-server"] = new { url = "https://my-mcp-server.example.com/mcp" }
    },
    // Any non-null handler enables Phase 1 tool call visibility
    OnPermissionRequest = async (request, invocation) =>
    {
        // Auto-approve everything — but TOOL_CALL events still appear on AG-UI stream
        return new PermissionRequestResult { Kind = "approved" };
    }
};

var agent = new GitHubCopilotAgent(copilotClient, sessionConfig);

app.MapAGUI("/", agent);
app.Run();
```

With this setup, **every MCP tool call** emits `TOOL_CALL_START/ARGS/END/RESULT` events on the SSE stream. Clients see which tools are being called and with what arguments — even though everything is auto-approved server-side.

### Full HITL (Phase 2 — Client Approval)

```csharp
using GitHub.Copilot.SDK;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.GitHub.Copilot;

var builder = WebApplication.CreateBuilder(args);

// AddAGUI() registers PendingApprovalStore and AGUIOptions.
// The approval timeout is configurable (default: 60 seconds).
builder.Services.AddAGUI(options =>
{
    options.ApprovalTimeout = TimeSpan.FromSeconds(120); // 2 minutes instead of default 60s
});

var app = builder.Build();

// Enable trace logging so [AGUI-Permission], [AGUI-HITL], and [AGUI-SSE] logs appear in console
System.Diagnostics.Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener());

await using var copilotClient = new CopilotClient();
await copilotClient.StartAsync();

var sessionConfig = new SessionConfig
{
    McpServers = new Dictionary<string, object>
    {
        ["my-mcp-server"] = new { url = "https://my-mcp-server.example.com/mcp" }
    },
    // A non-null handler is required to activate the permission wrapper.
    // In HITL mode, this handler is NOT called directly — the framework
    // intercepts and blocks on PendingApprovalStore instead.
    OnPermissionRequest = async (request, invocation) =>
    {
        return new PermissionRequestResult { Kind = "approved" };
    }
};

var agent = new GitHubCopilotAgent(copilotClient, sessionConfig);

// MapAGUI automatically:
// 1. Registers PendingApprovalStore.RegisterAsync as a Func<string, Task<bool>>
//    on AgentRunOptions.AdditionalProperties["ag_ui_pending_approval_store"]
// 2. Registers POST {pattern}/approve endpoint
app.MapAGUI("/", agent);
app.Run();
```

## How the HITL Blocking Flow Works

When `AddAGUI()` is called and `MapAGUI()` sets up the endpoints, the full human-in-the-loop
cycle works as follows:

```
Step 1: Copilot SDK fires OnPermissionRequest(request, invocation)
        ↓
Step 2: GitHubCopilotAgent's wrapped handler:
        a. Generates a unique callId (GUID)
        b. Writes FunctionCallContent to the channel → TOOL_CALL_START/ARGS/END on SSE
        c. Checks if approvalRegistration delegate is available (set by MapAGUI)
        ↓
Step 3: approvalRegistration(callId) calls PendingApprovalStore.RegisterAsync(callId, timeout)
        a. Creates a TaskCompletionSource<bool>
        b. Stores it in ConcurrentDictionary keyed by callId
        c. Starts a CancellationTokenSource timer (configurable via AGUIOptions.ApprovalTimeout)
        d. Returns tcs.Task ← THE HANDLER BLOCKS HERE (await)
        ↓
Step 4: Meanwhile, the SSE stream emits:
        - TOOL_CALL_START, TOOL_CALL_ARGS, TOOL_CALL_END (tool visibility)
        - CUSTOM { name: "tool_approval_requested", value: { requestId: callId, ... } }
        The SSE connection stays OPEN. No more events flow until approval is received.
        ↓
Step 5: Client sees the CUSTOM event and shows approve/deny UI to the user.
        User clicks "Approve" or "Deny".
        ↓
Step 6: Client POSTs to /approve:
        { "requestId": "<callId>", "approved": true }
        ↓
Step 7: /approve handler calls PendingApprovalStore.TryComplete(callId, approved):
        a. Removes the entry from ConcurrentDictionary
        b. Calls tcs.TrySetResult(approved) → resolves the blocked Task
        c. Disposes the timeout CancellationTokenSource
        d. Returns 200 OK to the client
        ↓
Step 8: Back in GitHubCopilotAgent, the await resumes:
        a. Converts bool → PermissionRequestResult:
           true  → { Kind = "approved" }
           false → { Kind = "denied-interactively-by-user" }
        b. Writes FunctionResultContent to channel → TOOL_CALL_RESULT on SSE
        c. Returns the PermissionRequestResult to the Copilot SDK
        ↓
Step 9: Copilot SDK either:
        - Executes the MCP tool (if approved) → feeds result to LLM → streams response
        - Skips the tool (if denied) → LLM generates alternative response
        ↓
Step 10: SSE stream continues with TEXT_MESSAGE_* events from the LLM response.
```

### Timeout Scenario

If the client never POSTs to `/approve` within 60 seconds:

```
Step 3d: CancellationTokenSource fires after 60s
         ↓
Step 3e: Token callback runs:
         a. Removes entry from ConcurrentDictionary
         b. Calls tcs.TrySetResult(false) → resolves the blocked Task with "denied"
         c. Flow continues at Step 8 with approved = false
```

### Key Implementation Details

**`PendingApprovalStore` is a singleton**:  
Registered in DI via `AddAGUI()`. The same instance is shared between the `/approve`
POST handler (which calls `TryComplete`) and the agent's permission wrapper (which calls
`RegisterAsync`). This is what connects the two separate HTTP requests.

**The SSE connection stays open during the wait**:  
The `RunCoreStreamingAsync` method uses `Channel<AgentResponseUpdate>`. The
`OnPermissionRequest` callback runs on the Copilot SDK's thread and blocks via `await`.
Meanwhile, the SSE response is still being written by the AG-UI pipeline reading from the
channel. Events emitted before the block (TOOL_CALL_START, CUSTOM) are flushed to the
client. No new events arrive until the TCS resolves.

**The `approvalRegistration` delegate bridges packages without coupling**:  
`GitHubCopilotAgent` (in `Microsoft.Agents.AI.GitHub.Copilot` package) has no reference
to `PendingApprovalStore` (in `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore` package).
Instead, `MapAGUI` passes `PendingApprovalStore.RegisterAsync` as a
`Func<string, Task<bool>>` through `AgentRunOptions.AdditionalProperties`. The agent
extracts it by key and calls it without knowing the concrete type.

## Client Integration

### SSE Event Stream

Any AG-UI client receives events in this order for an MCP tool call:

```
RUN_STARTED
TEXT_MESSAGE_START          ← Agent starts responding
TEXT_MESSAGE_CONTENT (×N)   ← Streaming text
TEXT_MESSAGE_END
TOOL_CALL_START             ← MCP tool call detected
  { toolCallId: "abc123", toolCallName: "mcp", parentMessageId: "..." }
TOOL_CALL_ARGS
  { toolCallId: "abc123", delta: '{"kind":"mcp"}' }
TOOL_CALL_END
  { toolCallId: "abc123" }
CUSTOM                      ← (Phase 2 only) Approval needed
  { name: "tool_approval_requested", value: { requestId: "abc123", toolCallId: "abc123", toolCallName: "mcp", kind: "mcp" } }

  ... client POSTs to /approve ...

TOOL_CALL_RESULT            ← Permission decision
  { toolCallId: "abc123", content: "approved" }
CUSTOM                      ← (Phase 2 only) Approval resolved
  { name: "tool_approval_completed", value: { requestId: "abc123", toolCallId: "abc123", result: "approved" } }
TEXT_MESSAGE_START          ← Agent continues with tool result
TEXT_MESSAGE_CONTENT (×N)
TEXT_MESSAGE_END
RUN_FINISHED
```

### Approval Endpoint

```http
POST /approve
Content-Type: application/json

{
  "requestId": "abc123",
  "approved": true
}
```

**Responses:**
- `200 OK` — Approval registered, tool execution proceeds (or is skipped if denied)
- `404 Not Found` — Unknown requestId (expired or already completed)
- `400 Bad Request` — Missing requestId

### Example: Raw JavaScript Client

```javascript
// Connect to the AG-UI SSE stream
const response = await fetch('/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    threadId: 'thread-1',
    runId: 'run-1',
    messages: [{ role: 'user', content: 'Get test plan details' }]
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  // SSE events are separated by double newlines
  for (const line of text.split('\n')) {
    if (!line.startsWith('data: ')) continue;
    const data = JSON.parse(line.slice(6));

    switch (data.type) {
      case 'TOOL_CALL_START':
        console.log(`🔧 Tool call started: ${data.toolCallName} (${data.toolCallId})`);
        break;

      case 'TOOL_CALL_ARGS':
        console.log(`   Args: ${data.delta}`);
        break;

      case 'CUSTOM':
        if (data.name === 'tool_approval_requested') {
          const { requestId, toolCallName, kind } = data.value;
          console.log(`⏳ Approval needed for ${kind} tool "${toolCallName}"`);

          // Show approve/deny UI — this is where your app renders a modal, 
          // toast notification, or inline approval button
          const userApproved = confirm(
            `The agent wants to call ${kind} tool "${toolCallName}".\n\nAllow?`
          );

          // POST the user's decision to the /approve endpoint
          // This unblocks the server-side PendingApprovalStore.RegisterAsync() call
          const approveResponse = await fetch('/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ requestId, approved: userApproved })
          });

          if (approveResponse.ok) {
            console.log(`✅ Decision sent: ${userApproved ? 'approved' : 'denied'}`);
          } else if (approveResponse.status === 404) {
            console.log('⏰ Approval timed out (60s) — already auto-denied');
          }
        }

        if (data.name === 'tool_approval_completed') {
          console.log(`🏁 Approval resolved: ${data.value.result}`);
        }
        break;

      case 'TOOL_CALL_RESULT':
        console.log(`📋 Tool result: ${data.content}`);
        break;

      case 'TEXT_MESSAGE_CONTENT':
        process.stdout.write(data.delta); // Stream LLM response
        break;
    }
  }
}
```

### Example: React Component with Approval Dialog

```tsx
import { useState, useEffect, useCallback } from 'react';

interface PendingApproval {
  requestId: string;
  toolCallName: string;
  kind: string;
}

function AgentChat() {
  const [messages, setMessages] = useState<string[]>([]);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);

  const sendMessage = useCallback(async (userMessage: string) => {
    const response = await fetch('/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        threadId: 'thread-1',
        runId: Date.now().toString(),
        messages: [{ role: 'user', content: userMessage }]
      })
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      for (const line of decoder.decode(value).split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const event = JSON.parse(line.slice(6));

        if (event.type === 'CUSTOM' && event.name === 'tool_approval_requested') {
          // Show the approval dialog — SSE stream pauses until user responds
          setPendingApproval({
            requestId: event.value.requestId,
            toolCallName: event.value.toolCallName,
            kind: event.value.kind,
          });
        }

        if (event.type === 'TEXT_MESSAGE_CONTENT') {
          setMessages(prev => [...prev, event.delta]);
        }
      }
    }
  }, []);

  const handleApproval = async (approved: boolean) => {
    if (!pendingApproval) return;

    // POST to /approve — this unblocks the server and resumes the SSE stream
    await fetch('/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requestId: pendingApproval.requestId,
        approved
      })
    });

    setPendingApproval(null);
  };

  return (
    <div>
      {/* Chat messages */}
      {messages.map((msg, i) => <p key={i}>{msg}</p>)}

      {/* Approval dialog — appears when CUSTOM tool_approval_requested arrives */}
      {pendingApproval && (
        <div className="approval-dialog">
          <p>
            The agent wants to call <strong>{pendingApproval.kind}</strong> tool
            "<strong>{pendingApproval.toolCallName}</strong>"
          </p>
          <button onClick={() => handleApproval(true)}>✅ Approve</button>
          <button onClick={() => handleApproval(false)}>❌ Deny</button>
          <small>Auto-denies in 60 seconds if no response</small>
        </div>
      )}
    </div>
  );
}
```

### Example: CopilotKit Integration

CopilotKit users can handle approval events via `useAgent()` subscriber:

```tsx
import { useAgent } from "@copilotkit/react-core";

function MyComponent() {
  const { subscribe } = useAgent();
  
  useEffect(() => {
    const unsubscribe = subscribe({
      onToolCallStartEvent: (event) => {
        console.log(`Tool: ${event.toolCallName}`);
      },
      onCustomEvent: (event) => {
        if (event.name === 'tool_approval_requested') {
          // Render approval UI and POST to /approve
        }
      },
    });
    return unsubscribe;
  }, []);
}
```

## Backward Compatibility

| Scenario | Behavior |
|---|---|
| `OnPermissionRequest = null` | No wrapper injected. SDK default behavior. No TOOL_CALL events. |
| `OnPermissionRequest = auto-approve handler` | Phase 1: TOOL_CALL events emitted. Auto-approves immediately. |
| `OnPermissionRequest = console prompt` | Phase 1: TOOL_CALL events emitted. Console prompt fires server-side. |
| `PendingApprovalStore` not in DI | Phase 1 only. No HITL blocking. No CUSTOM events. |
| `PendingApprovalStore` registered (via `AddAGUI()`) | Phase 2: HITL blocking enabled. CUSTOM events emitted. Configurable timeout. |
| `ServerFunctionApprovalAgent` for .NET tools | Completely unaffected — separate code path. |

## Configurable Timeout

The approval timeout is configurable via `AGUIOptions.ApprovalTimeout`:

```csharp
// Default: 60 seconds
builder.Services.AddAGUI();

// Custom: 2 minutes
builder.Services.AddAGUI(options => options.ApprovalTimeout = TimeSpan.FromSeconds(120));

// Custom: 30 seconds for fast-paced UIs
builder.Services.AddAGUI(options => options.ApprovalTimeout = TimeSpan.FromSeconds(30));
```

If the client doesn't POST to `/approve` within the configured timeout:

1. The pending approval auto-denies (`approved = false`)
2. `TOOL_CALL_RESULT` emits with `"denied-interactively-by-user"`
3. `tool_approval_completed` CUSTOM event emits with the denial
4. The Copilot SDK skips the tool call and the LLM generates an alternative response

## Trace Logging

The implementation emits structured trace logs at every stage using `System.Diagnostics.Trace`.

> **Important:** These logs require a `TraceListener` to be attached. ASP.NET Core does **not**
> include one by default. Without it, all `[AGUI-*]` logs are silently discarded.
> Add this line before `app.Run()`:
> ```csharp
> System.Diagnostics.Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener());
> ```

| Log prefix | Component | What's logged |
|---|---|---|
| `[AGUI-Permission]` | `GitHubCopilotAgent` | HITL delegate detection, OnPermissionRequest fire, channel writes, blocking/forwarding, approval results |
| `[AGUI-HITL]` | `PendingApprovalStore` | Registration, timeout auto-deny, client completion |
| `[AGUI-HITL]` | `/approve` endpoint | Received requests, resolved/not-found results |
| `[AGUI-SSE]` | `AsAGUIEventStreamAsync` | TOOL_CALL_START emission, CUSTOM event emission |

To see these logs in your ASP.NET Core app, add a console trace listener:

```csharp
// In Program.cs, before app.Run()
System.Diagnostics.Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener());
```

Example output for a tool approval flow:
```
[AGUI-Permission] OnPermissionRequest fired: Kind=mcp, ToolName=mcp, CallId=abc123
[AGUI-Permission] FunctionCallContent written to channel: CallId=abc123, Success=True
[AGUI-Permission] HITL mode — blocking for client approval: CallId=abc123
[AGUI-HITL] Registering pending approval: RequestId=abc123, TimeoutSeconds=60
[AGUI-HITL] Approval registered, waiting for client response: RequestId=abc123
[AGUI-SSE] Emitting TOOL_CALL_START: CallId=abc123, Name=mcp
[AGUI-SSE] Emitted CUSTOM tool_approval_requested: RequestId=abc123
  ... waiting for client ...
[AGUI-HITL] /approve received: RequestId=abc123
[AGUI-HITL] Approval completed: RequestId=abc123
[AGUI-Permission] HITL approval resolved: CallId=abc123, Approved=True
[AGUI-Permission] FunctionResultContent written to channel: CallId=abc123, ResultKind=approved, Success=True
[AGUI-SSE] Emitting TOOL_CALL_RESULT: CallId=abc123
[AGUI-SSE] Emitted CUSTOM tool_approval_completed: RequestId=abc123, Result=approved
```

## Permission Request Kinds

The Copilot SDK's `PermissionRequest.Kind` discriminator tells you what type of action needs approval:

| Kind | Description |
|---|---|
| `mcp` | MCP tool call — includes serverName, toolName, args |
| `shell` | Shell command execution |
| `write` | File write operation |
| `read` | File read operation |
| `url` | URL access |
| `custom-tool` | Custom tool via SessionConfig.Tools |

> **Note:** Currently `request.Kind` is the only confirmed property from the .NET Copilot SDK. Properties like `ServerName`, `ToolName`, `ToolTitle`, `Args`, and `ReadOnly` are documented in the Copilot SDK streaming events spec but need to be verified against the .NET SDK assembly. TODOs in the code mark where these should be added once confirmed.
