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
