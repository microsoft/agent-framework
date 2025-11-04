# Microsoft.Agents.AI.DevUI

This package provides a web interface for testing and debugging AI agents during development.

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

// Add DevUI services
builder.AddDevUI();

var app = builder.Build();

// Map DevUI endpoint
app.MapDevUI(); // Available at /devui

// Map required endpoints
app.MapEntities();
app.MapOpenAIResponses();
app.MapOpenAIConversations();

app.Run();
```

### Custom Path

```csharp
app.MapDevUI("/agent-ui");
```

### With Authorization

```csharp
app.MapDevUI().RequireAuthorization("Developer");
```