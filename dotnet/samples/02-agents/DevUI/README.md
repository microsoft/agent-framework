# DevUI Samples

This folder contains samples demonstrating how to use the DevUI in ASP.NET Core applications.

## What is DevUI?

The DevUI provides an interactive web interface for testing and debugging AI agents during development.

## Samples

### [DevUI_Step01_BasicUsage](./DevUI_Step01_BasicUsage)

Shows how to add DevUI to an ASP.NET Core application with multiple agents and workflows.

**Run the sample:**
```bash
cd DevUI_Step01_BasicUsage
dotnet run
```
Then navigate to: https://localhost:50516/devui

## Requirements

- .NET 8.0 or later
- ASP.NET Core
- Azure OpenAI credentials

## Quick Start

To add DevUI to your application:

```csharp
var builder = WebApplication.CreateBuilder(args);

// Set up the chat client
builder.Services.AddChatClient(chatClient);

// Register your agents
builder.AddAIAgent("my-agent", "You are a helpful assistant.");

// Register services for OpenAI responses and conversations (also required for DevUI)
builder.Services.AddOpenAIResponses();
builder.Services.AddOpenAIConversations();

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

Then navigate to `/devui` in your browser.
