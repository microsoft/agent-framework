# Microsoft.Agents.AI.DevUI

This package provides a web interface for testing and debugging AI agents during development.

> [!WARNING]
> DevUI is intended for development only. Its endpoints surface agent system instructions, tool definitions, model identifiers, and workflow structure. Do not expose DevUI to untrusted callers. By default, DevUI rejects any request whose remote endpoint is not a loopback address; see [Security](#security) below for the available options.

## Installation

```bash
dotnet add package Microsoft.Agents.AI.DevUI
dotnet add package Microsoft.Agents.AI.Hosting
dotnet add package Microsoft.Agents.AI.Hosting.OpenAI
```

## Usage

Add DevUI services and map the endpoint in your ASP.NET Core application:

```csharp
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;

var builder = WebApplication.CreateBuilder(args);

// Register your agents
builder.AddAIAgent("assistant", "You are a helpful assistant.");

// Register DevUI services
if (builder.Environment.IsDevelopment())
{
    builder.AddDevUI();
}

// Register services for OpenAI responses and conversations (also required for DevUI)
builder.AddOpenAIResponses();
builder.AddOpenAIConversations();

var app = builder.Build();

// Map endpoints for OpenAI responses and conversations (also required for DevUI)
app.MapOpenAIResponses();
app.MapOpenAIConversations();

if (builder.Environment.IsDevelopment())
{
    // Map DevUI endpoint to /devui
    app.MapDevUI();
}

app.Run();
```

## Function approval responses

DevUI sends decisions for `ApprovalRequiredAIFunction` as a non-standard Responses API extension inside a user message's `content` array:

```json
{
  "input": [{
    "type": "message",
    "role": "user",
    "content": [{
      "type": "function_approval_response",
      "request_id": "request-1",
      "approved": true,
      "function_call": {
        "id": "call-1",
        "name": "get_weather",
        "arguments": { "location": "Seattle" }
      }
    }]
  }]
}
```

The hosting layer converts this content to `ToolApprovalResponseContent`, preserving the request ID, decision, and function call. Rejections use `"approved": false`; function arguments can be an object or `null` for a call without arguments. The IDs and function call must come from the pending approval request, including any workflow prefix on the request ID.

### Restoring the approval session

Enable session persistence explicitly when registering the agent. Both Responses endpoint variants (`MapOpenAIResponses()` and `MapOpenAIResponses(agent)`) use the `AgentSessionStore` registered under the resolved agent's name, falling back to a non-keyed `AgentSessionStore` when one is registered:

```csharp
// Single-user local development only: no caller identity is configured.
builder.AddAIAgent("assistant", "You are a helpful assistant.")
    .WithInMemorySessionStore(withIsolation: false);

// For an existing workflow:
builder.AddAIAgent("workflow", (_, _) => workflow.AsAIAgent(name: "workflow"))
    .WithInMemorySessionStore(withIsolation: false);
```

Use `WithSessionStore(...)` for a custom store. In multi-user hosts, configure an `AgentIsolationKeyProvider` and leave isolation enabled; the default isolation wrapper rejects requests without an isolation key. Session isolation does not replace authentication and authorization on the Responses and Conversations endpoints.

DevUI sends the same `conversation` ID on subsequent turns. The hosting layer restores the full agent session, including pending approvals and workflow checkpoints, and saves it before publishing `response.completed`. It uses the session's history instead of replaying the conversation transcript, so previously handled approvals are not submitted again. Workflow approval events expose the workflow-facing request ID rather than a duplicate internal agent request.

Clients can alternatively continue with `previous_response_id`, which restores that response's independent session snapshot. Each successful turn saves a new snapshot unless `store` is `false`; a conversation's session is also advanced under its stable ID. Deleting a stored response deletes its snapshot without deleting the conversation's session.

Without a configured session store, the existing transcript-based behavior is unchanged and pending approval sessions are not restored. The in-memory session store is for local development and loses state on restart. Hosts own session-store retention, stable agent IDs across agent recreation, and coordination of concurrent turns against the same conversation. Conversation transcript storage is separate: adding or deleting transcript items does not edit a persisted agent session.

## Security

DevUI exposes `/v1/entities` and `/v1/entities/{id}/info`, which return agent metadata including the system prompt (`ChatClientAgent.Instructions`). To prevent accidental disclosure, the DevUI route group is wrapped in a small endpoint filter that:

- Rejects requests from any non-loopback `RemoteIpAddress` with HTTP 403 by default.
- Optionally requires a shared bearer token on every request.

Configure via `DevUIOptions`:

```csharp
builder.AddDevUI(options =>
{
    // Allow non-loopback callers. Set this only when the host fronts DevUI with
    // its own authentication or network policy.
    options.AllowRemoteAccess = true;

    // Optional: require Authorization: Bearer <token> on every request.
    // Falls back to the DEVUI_AUTH_TOKEN environment variable when null.
    options.AuthToken = builder.Configuration["DevUI:AuthToken"];

    // Optional: attach a real authorization policy or rate limiting.
    options.ConfigureEndpoints = group => group.RequireAuthorization("DevUIPolicy");
});
```

The bundled bearer-token check uses constant-time comparison and is intended as a convenience for development scenarios. Production hosts should prefer a real ASP.NET Core authentication scheme via `ConfigureEndpoints`.
