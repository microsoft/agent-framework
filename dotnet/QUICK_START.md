# Quick Start Guide - .NET Agent Framework

## 5-Minute Quick Start

### 1. Create a Basic Agent

```csharp
using Microsoft.Agents.AI;
using Azure.AI.OpenAI;
using Azure.Identity;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!;
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME")!;

var agent = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
    .GetOpenAIResponseClient(deploymentName)
    .CreateAIAgent(name: "HaikuBot", instructions: "You are an upbeat assistant.");

var response = await agent.RunAsync("Write a haiku about coding.");
Console.WriteLine(response);
```

### 2. Add Function Tools

```csharp
AIFunction GetWeather([Description("The city name")] string city)
{
    return $"The weather in {city} is sunny, 72°F";
}

var agent = chatClient
    .CreateAIAgent(name: "WeatherBot")
    .WithTools([GetWeather])
    .Build();

await agent.RunAsync("What's the weather in Seattle?");
```

### 3. Multi-Turn Conversation

```csharp
var thread = new InMemoryAgentThread();

while (true)
{
    Console.Write("You: ");
    var input = Console.ReadLine();
    
    var response = await agent.RunAsync(input, thread);
    Console.WriteLine($"Agent: {response}");
}
```

---

## Common Scenarios

### Scenario 1: Using OpenAI

```csharp
using OpenAI;
using OpenAI.Chat;
using Microsoft.Agents.AI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")!;
var chatClient = new OpenAIClient(apiKey).GetChatClient("gpt-4o");

var agent = chatClient.CreateAIAgent(
    name: "MyAgent",
    instructions: "You are a helpful assistant."
);
```

**See:** `samples/GettingStarted/AgentProviders/Agent_With_OpenAIChatCompletion/`

### Scenario 2: Using Azure OpenAI

```csharp
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;

var endpoint = new Uri(Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!);
var credential = new AzureCliCredential();
var deploymentName = "gpt-4o";

var chatClient = new AzureOpenAIClient(endpoint, credential).GetChatClient(deploymentName);
var agent = chatClient.CreateAIAgent(name: "MyAgent");
```

**See:** `samples/GettingStarted/AgentProviders/Agent_With_AzureOpenAIChatCompletion/`

### Scenario 3: Structured Output

```csharp
public record Weather(string City, int Temperature, string Condition);

var response = await agent.RunAsync<Weather>(
    "What's the weather in Seattle?",
    options: new AgentRunOptions 
    { 
        ResponseFormat = ChatResponseFormat.CreateJsonSchemaFormat(
            jsonSchemaFormatName: "weather",
            jsonSchema: BinaryData.FromString("""
            {
                "type": "object",
                "properties": {
                    "city": { "type": "string" },
                    "temperature": { "type": "number" },
                    "condition": { "type": "string" }
                }
            }
            """)
        )
    }
);

Weather weather = response.GetResult<Weather>();
```

**See:** `samples/GettingStarted/Agents/Agent_Step05_StructuredOutput/`

### Scenario 4: Persistent Conversations

```csharp
// First run - create thread
var thread = new InMemoryAgentThread();
await agent.RunAsync("My name is Alice", thread);

// Save thread ID
var threadId = thread.Id;

// Later - restore thread
var restoredThread = new InMemoryAgentThread { Id = threadId };
await agent.RunAsync("What's my name?", restoredThread);
// Response: "Your name is Alice"
```

**See:** `samples/GettingStarted/Agents/Agent_Step06_PersistedConversations/`

### Scenario 5: Human Approval for Tools

```csharp
var agent = chatClient
    .CreateAIAgent(name: "Assistant")
    .WithTools([SendEmail])
    .WithApprovalRequired()
    .Build();

await agent.RunAsync("Send an email to bob@example.com", 
    options: new AgentRunOptions
    {
        ApprovalCallback = async (toolCall) =>
        {
            Console.WriteLine($"Approve {toolCall.FunctionName}? (y/n)");
            return Console.ReadLine()?.ToLower() == "y";
        }
    }
);
```

**See:** `samples/GettingStarted/Agents/Agent_Step04_UsingFunctionToolsWithApprovals/`

### Scenario 6: Dependency Injection

```csharp
var builder = Host.CreateApplicationBuilder(args);

// Register services
builder.Services.AddSingleton<IChatClient>(sp => 
    new OpenAIClient(apiKey).GetChatClient("gpt-4o")
);

// Register agent
builder.Services.AddAgent<MyAgent>();

var app = builder.Build();

// Use agent
var agent = app.Services.GetRequiredService<MyAgent>();
await agent.RunAsync("Hello!");
```

**See:** `samples/GettingStarted/Agents/Agent_Step09_DependencyInjection/`

### Scenario 7: OpenTelemetry Observability

```csharp
var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddOpenTelemetry()
    .WithTracing(tracing => tracing
        .AddSource("Microsoft.Agents.AI")
        .AddConsoleExporter()
    );

builder.Services.AddAgent<MyAgent>();

var app = builder.Build();
var agent = app.Services.GetRequiredService<MyAgent>();

// All agent operations are now traced
await agent.RunAsync("Hello!");
```

**See:** `samples/GettingStarted/Agents/Agent_Step08_Observability/`

---

## Workflows

### Basic Workflow

```csharp
using Microsoft.Agents.AI.Workflows;

var workflow = new WorkflowBuilder("MyWorkflow")
    .AddExecutor("step1", async (string input) => 
    {
        Console.WriteLine($"Step 1: {input}");
        return $"Processed: {input}";
    })
    .AddExecutor("step2", async (string input) =>
    {
        Console.WriteLine($"Step 2: {input}");
        return $"Final: {input}";
    })
    .AddEdge("step1", "step2")
    .Build();

await foreach (var update in workflow.RunAsync("Hello"))
{
    Console.WriteLine($"Update: {update}");
}
```

**See:** `samples/GettingStarted/Workflows/_Foundational/01_ExecutorsAndEdges/`

### Agent in Workflow

```csharp
var agent = chatClient.CreateAIAgent(name: "Analyzer");

var workflow = new WorkflowBuilder("AnalysisWorkflow")
    .AddAgentExecutor("analyze", agent, instructions: "Analyze the input")
    .AddExecutor("process", async (AgentRunResponse response) =>
    {
        return $"Processed: {response.GetTextContent()}";
    })
    .AddEdge("analyze", "process")
    .Build();

await workflow.RunAsync("Analyze this text");
```

**See:** `samples/GettingStarted/Workflows/_Foundational/03_AgentsInWorkflows/`

### Conditional Routing

```csharp
var workflow = new WorkflowBuilder("ConditionalFlow")
    .AddExecutor("router", async (string input) => input)
    .AddExecutor("pathA", async (string input) => $"Path A: {input}")
    .AddExecutor("pathB", async (string input) => $"Path B: {input}")
    .AddEdge("router", "pathA", condition: (input) => input.Contains("important"))
    .AddEdge("router", "pathB", condition: (input) => !input.Contains("important"))
    .Build();

await workflow.RunAsync("important message");  // Goes to pathA
await workflow.RunAsync("regular message");     // Goes to pathB
```

**See:** `samples/GettingStarted/Workflows/ConditionalEdges/01_EdgeCondition/`

### Parallel Execution

```csharp
var workflow = new WorkflowBuilder("ParallelFlow")
    .AddExecutor("fanout", async (string input) => input)
    .AddExecutor("worker1", async (string input) => $"Worker1: {input}")
    .AddExecutor("worker2", async (string input) => $"Worker2: {input}")
    .AddExecutor("worker3", async (string input) => $"Worker3: {input}")
    .AddExecutor("aggregate", async (IEnumerable<string> results) => 
        string.Join(", ", results))
    .AddFanOutEdge("fanout", ["worker1", "worker2", "worker3"])
    .AddFanInEdge(["worker1", "worker2", "worker3"], "aggregate")
    .Build();

await workflow.RunAsync("Process this");
```

**See:** `samples/GettingStarted/Workflows/Concurrent/Concurrent/`

### Declarative YAML Workflow

**workflow.yaml:**
```yaml
name: SimpleWorkflow
description: A simple workflow example

agents:
  - id: analyzer
    type: AzureOpenAI
    model: gpt-4o
    instructions: Analyze the input

executors:
  - id: start
    type: function
    function: |
      return input;
  
  - id: analyze
    type: agent
    agent: analyzer
  
  - id: finish
    type: function
    function: |
      return "Done: " + input;

edges:
  - from: start
    to: analyze
  - from: analyze
    to: finish
```

**C# code:**
```csharp
using Microsoft.Agents.AI.Workflows.Declarative;

var workflow = await DeclarativeWorkflowBuilder
    .LoadFromFileAsync("workflow.yaml");

await workflow.RunAsync("Analyze this input");
```

**See:** `samples/GettingStarted/Workflows/Declarative/ExecuteWorkflow/`

---

## Advanced Features

### Checkpoint and Resume

```csharp
var checkpointStore = new FileSystemJsonCheckpointStore("./checkpoints");

var workflow = new WorkflowBuilder("CheckpointableFlow")
    .AddExecutor("step1", async (string input) => /* ... */)
    .AddExecutor("step2", async (string input) => /* ... */)
    .AddEdge("step1", "step2")
    .WithCheckpointing(checkpointStore)
    .Build();

// Run with checkpointing
var run = workflow.RunAsync("input");
await foreach (var update in run)
{
    if (update.CheckpointId != null)
    {
        Console.WriteLine($"Checkpointed: {update.CheckpointId}");
    }
}

// Resume from checkpoint
var checkpointId = "previous-checkpoint-id";
var resumedRun = workflow.ResumeAsync(checkpointId);
await foreach (var update in resumedRun)
{
    Console.WriteLine(update);
}
```

**See:** `samples/GettingStarted/Workflows/Checkpoint/CheckpointAndResume/`

### A2A (Agent-to-Agent) Communication

**Server:**
```csharp
using Microsoft.Agents.AI.A2A;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddAgent<MyAgent>();
builder.Services.AddA2AHosting();

var app = builder.Build();
app.MapA2AEndpoints();
app.Run();
```

**Client:**
```csharp
var client = new A2AAgent(new Uri("http://localhost:5000/a2a"));
var response = await client.RunAsync("Hello from client!");
```

**See:** `samples/A2AClientServer/`

### Model Context Protocol (MCP)

```csharp
using ModelContextProtocol;

var mcpServer = new McpServer();
mcpServer.AddTool("weather", async (string city) => 
    $"Weather in {city}: Sunny"
);

var agent = chatClient
    .CreateAIAgent(name: "Assistant")
    .WithMcpServer(mcpServer)
    .Build();

await agent.RunAsync("What's the weather in Seattle?");
```

**See:** `samples/GettingStarted/ModelContextProtocol/Agent_MCP_Server/`

### Memory Integration

```csharp
using Microsoft.SemanticKernel.Connectors.InMemory;

var memoryStore = new InMemoryVectorStore();

var agent = chatClient
    .CreateAIAgent(name: "Assistant")
    .WithMemory(memoryStore)
    .Build();

await agent.RunAsync("Remember: my favorite color is blue");
// Later...
await agent.RunAsync("What's my favorite color?");
// Response: "Your favorite color is blue"
```

**See:** `samples/GettingStarted/Agents/Agent_Step13_Memory/`

---

## Environment Setup

### Required Environment Variables

**For Azure OpenAI:**
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
# Authentication via Azure CLI or:
AZURE_OPENAI_API_KEY=your-api-key
```

**For OpenAI:**
```bash
OPENAI_API_KEY=sk-...
```

**For Azure AI Foundry:**
```bash
AZURE_AI_PROJECT_ENDPOINT=https://your-project.api.azureml.ms
AZURE_AI_AGENT_ID=your-agent-id
```

### Using User Secrets (Recommended)

```bash
dotnet user-secrets init
dotnet user-secrets set "AZURE_OPENAI_ENDPOINT" "https://..."
dotnet user-secrets set "AZURE_OPENAI_API_KEY" "..."
```

Access in code:
```csharp
var configuration = new ConfigurationBuilder()
    .AddUserSecrets<Program>()
    .Build();

var endpoint = configuration["AZURE_OPENAI_ENDPOINT"];
```

---

## Project Structure for New Projects

### Console Application

```
MyAgentApp/
├── MyAgentApp.csproj
├── Program.cs
├── Agents/
│   ├── MyAgent.cs
│   └── HelperAgent.cs
├── Tools/
│   └── MyTools.cs
└── appsettings.json
```

**MyAgentApp.csproj:**
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net9.0</TargetFramework>
    <UserSecretsId>your-guid-here</UserSecretsId>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.Agents.AI" Version="*-preview" />
    <PackageReference Include="Microsoft.Agents.AI.OpenAI" Version="*-preview" />
    <PackageReference Include="Azure.Identity" Version="1.17.0" />
    <PackageReference Include="Microsoft.Extensions.Configuration.UserSecrets" Version="9.0.0" />
  </ItemGroup>
</Project>
```

### Web Application with A2A

```
MyAgentWeb/
├── MyAgentWeb.csproj
├── Program.cs
├── Agents/
│   └── MyAgent.cs
└── appsettings.json
```

**MyAgentWeb.csproj:**
```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.Agents.AI" Version="*-preview" />
    <PackageReference Include="Microsoft.Agents.AI.Hosting.A2A.AspNetCore" Version="*-preview" />
  </ItemGroup>
</Project>
```

---

## Testing

### Unit Test Setup

```csharp
using Xunit;
using FluentAssertions;
using Moq;

public class MyAgentTests
{
    [Fact]
    public async Task Agent_Should_Respond_To_Greeting()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var agent = mockChatClient.Object.CreateAIAgent(name: "Test");

        // Act
        var response = await agent.RunAsync("Hello");

        // Assert
        response.Should().NotBeNull();
    }
}
```

**Test Project:**
```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <IsPackable>false</IsPackable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="18.0.0" />
    <PackageReference Include="xunit" Version="2.9.3" />
    <PackageReference Include="xunit.runner.visualstudio" Version="3.1.3" />
    <PackageReference Include="FluentAssertions" Version="8.7.1" />
    <PackageReference Include="Moq" Version="4.18.4" />
  </ItemGroup>
</Project>
```

---

## Common Commands

### Build and Run

```bash
# Build solution
dotnet build

# Run specific sample
cd samples/GettingStarted/Agents/Agent_Step01_Running
dotnet run

# Run with specific configuration
dotnet run --configuration Release

# Run tests
dotnet test

# Run specific test project
dotnet test tests/Microsoft.Agents.AI.UnitTests

# Run with coverage
dotnet test --collect:"XPlat Code Coverage"
```

### Package Management

```bash
# Restore packages
dotnet restore

# Update package
dotnet add package Microsoft.Agents.AI

# List packages
dotnet list package

# Pack for NuGet
dotnet pack --configuration Release
```

### Development

```bash
# Watch and rebuild on changes
dotnet watch run

# Format code
dotnet format

# Clean
dotnet clean

# Restore, build, and run
dotnet run
```

---

## Troubleshooting

### Issue: Authentication Failed

**Solution:**
```bash
# Login to Azure CLI
az login

# Set subscription
az account set --subscription "Your Subscription"
```

### Issue: API Key Not Found

**Solution:**
Check environment variables or user secrets:
```bash
dotnet user-secrets list
```

### Issue: Package Not Found

**Solution:**
Add preview feed to `nuget.config`:
```xml
<packageSources>
  <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
</packageSources>
```

### Issue: Workflow Not Executing

**Solution:**
Enable detailed logging:
```csharp
builder.Services.AddLogging(logging =>
{
    logging.AddConsole();
    logging.SetMinimumLevel(LogLevel.Debug);
});
```

---

## Best Practices

### 1. Always Use Dependency Injection
```csharp
// ✅ Good
builder.Services.AddAgent<MyAgent>();

// ❌ Avoid
var agent = new MyAgent();
```

### 2. Use Streaming for Long Responses
```csharp
// ✅ Good
await foreach (var update in agent.RunStreamingAsync("Long task"))
{
    Console.Write(update);
}

// ❌ Avoid blocking
var response = await agent.RunAsync("Long task"); // Waits for full response
```

### 3. Implement Proper Error Handling
```csharp
// ✅ Good
try
{
    var response = await agent.RunAsync(input);
}
catch (AIException ex)
{
    logger.LogError(ex, "Agent failed");
    // Handle gracefully
}
```

### 4. Use Structured Outputs When Possible
```csharp
// ✅ Good - type-safe
var weather = await agent.RunAsync<WeatherData>(input);

// ❌ Avoid - string parsing
var response = await agent.RunAsync(input);
var weather = ParseWeather(response.ToString());
```

### 5. Enable Observability
```csharp
// ✅ Good
builder.Services.AddOpenTelemetry()
    .WithTracing(t => t.AddSource("Microsoft.Agents.AI"));
```

---

## Next Steps

1. **Explore Samples:** `samples/GettingStarted/Agents/` - Complete tutorial path
2. **Read Architecture:** `ARCHITECTURE.md` - Understand the design
3. **Browse API Docs:** `CODEBASE_INDEX.md` - Full project structure
4. **Check Examples:** `workflow-samples/` - YAML workflow examples
5. **Join Community:** GitHub Discussions

---

## Quick Links

- [Main README](./README.md)
- [Codebase Index](./CODEBASE_INDEX.md)
- [Architecture Guide](./ARCHITECTURE.md)
- [Official Documentation](https://learn.microsoft.com/agent-framework/)
- [GitHub Repository](https://github.com/microsoft/agent-framework)
- [Sample Guidelines](./samples/SAMPLE_GUIDELINES.md)

---

**Last Updated:** October 14, 2025  
**Version:** 1.0


