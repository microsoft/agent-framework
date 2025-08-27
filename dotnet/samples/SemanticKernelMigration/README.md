# Semantic Kernel to Agent Framework Migration Guide

This repository contains **11 separate console application projects** demonstrating how to transition from **Semantic Kernel (SK)** to the new **Agent Framework (AF)**. Each project shows side-by-side comparisons of equivalent functionality in both frameworks and can be run independently.

## Prerequisites

Before you begin, ensure you have the following:

- [.NET 8.0 SDK or later](https://dotnet.microsoft.com/download)
- For Azure AI Foundry samples: Azure OpenAI service endpoint and deployment configured
- For OpenAI samples: OpenAI API key
- For OpenAI Assistants samples: OpenAI API key with Assistant API access

## Environment Variables

Set the appropriate environment variables based on the sample type you want to run:

**For Azure AI Foundry projects:**
```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
```

**For OpenAI and OpenAI Assistants projects:**
```powershell
$env:OPENAI_API_KEY = "sk-..."
```

**Optional debug mode:**
```powershell
$env:AF_SHOW_ALL_DEMO_SETTING_VALUES = "Y"
```

If environment variables are not set, the demos will prompt you to enter values interactively.

## Samples

The migration samples are organized into three categories, each demonstrating different AI service integrations:

|Category|Description|Projects|
|---|---|---|
|[Azure AI Foundry](./Azure%20AI%20Foundry/)|Azure OpenAI service integration samples|4 projects|
|[OpenAI](./OpenAI/)|Direct OpenAI API integration samples|3 projects|
|[OpenAI Assistants](./OpenAI%20Assistants/)|OpenAI Assistant API integration samples|4 projects|

### Sample Types

Each category includes the following migration demonstrations:

- **Step01_Basics**: Basic agent creation and invocation
- **Step02_DependencyInjection**: Using dependency injection patterns
- **Step03_ToolCall**: Function/tool calling capabilities
- **Step04_CodeInterpreter**: Code interpreter functionality (Azure AI Foundry and OpenAI Assistants only)

## Running the samples from the console

To run any migration sample, navigate to the desired sample directory:

```powershell
# Azure AI Foundry Examples
cd "Azure AI Foundry\Step01_Basics"
dotnet run

cd "Azure AI Foundry\Step03_ToolCall"
dotnet run

# OpenAI Examples
cd "OpenAI\Step01_Basics"
dotnet run

cd "OpenAI\Step02_DependencyInjection"
dotnet run

# OpenAI Assistants Examples
cd "OpenAI Assistants\Step01_Basics"
dotnet run

cd "OpenAI Assistants\Step04_CodeInterpreter"
dotnet run
```

Each project demonstrates **side-by-side comparisons** of:
1. **AF Agent** (Agent Framework approach) - The new way
2. **SK Agent** (Semantic Kernel approach) - The legacy way

## Running the samples from Visual Studio

Open the solution in Visual Studio and set the desired sample project as the startup project. Then, run the project using the built-in debugger or by pressing `F5`.

You will be prompted for any required environment variables if they are not already set.

## Key Migration Concepts

The migration samples demonstrate the following key differences between Semantic Kernel and Agent Framework:

### Core Changes
- **Namespace Updates**: From `Microsoft.SemanticKernel.Agents` to `Microsoft.Extensions.AI.Agents`
- **Agent Creation**: Single fluent API calls vs multi-step builder patterns
- **Thread Management**: Built-in thread management vs manual thread creation
- **Tool Registration**: Direct function registration vs plugin wrapper systems
- **Dependency Injection**: Simplified service registration patterns
- **Invocation Patterns**: Streamlined options and result handling

### Benefits of Migration
- **Simplified API**: Reduced complexity and boilerplate code
- **Better Performance**: Optimized object creation and memory usage
- **Unified Interface**: Consistent patterns across different AI providers
- **Enhanced Developer Experience**: More intuitive and discoverable APIs

## Common Migration Patterns

### 1. Namespace Updates
Always update your using statements to include the new Agent Framework namespaces:

```csharp
// Add these
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

// Remove these after SK code was fully migrated
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
```

### 2. Agent Creation Simplification
Replace multi-step agent creation with fluent API calls:

```csharp
// Old pattern
var builder = Kernel.CreateBuilder().AddProvider(...);
var agent = new SpecificAgent() { Kernel = builder.Build(), ... };

// New pattern  
var agent = client.CreateAIAgent(...);
```

### 3. Thread Management
Use built-in thread management instead of manual creation:

```csharp
// Old
var thread = new SpecificAgentThread(...);

// New
var thread = agent.GetNewThread();
```

### 4. Tool Registration
Register tools directly instead of using `Kernel` with plugin wrappers:

```csharp
// Old
agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromType<PluginClass>());

// New
var agent = client.CreateAIAgent(tools: [
    AIFunctionFactory.Create(ToolClass.Method1),
    AIFunctionFactory.Create(ToolClass.Method2)
]);
```

### 5. Dependency Injection

Simpler service registration:

```csharp
// Old
services.AddKernel().AddProvider(...);
services.AddTransient<SpecificAgent>(...);

// New
services.AddTransient<AIAgent>(() => client.CreateAIAgent(...));
```

## Running Individual Sample Projects

Each migration demo is now full end-to-end **separate console application project** that can be run independently with clear view on what are all required dependencies and environment variables.

This approach also paves the way for future sample convergence in the .net 10 `dotnet run file.cs` feature, see: https://devblogs.microsoft.com/dotnet/announcing-dotnet-run-app/

### Running Specific Sample Projects
```powershell
# Azure AI Foundry Examples
cd "Azure AI Foundry\Step01_Basics"
dotnet run

cd "Azure AI Foundry\Step03_ToolCall"
dotnet run

# OpenAI Examples
cd "OpenAI\Step01_Basics"
dotnet run

cd "OpenAI\Step02_DependencyInjection"
dotnet run

# OpenAI Assistants Examples
cd "OpenAI Assistants\Step01_Basics"
dotnet run

cd "OpenAI Assistants\Step04_CodeInterpreter"
dotnet run
```

### What Each Demo Shows
Each project demonstrates **side-by-side comparisons** of the same functionality using:
2. **SK Agent** (Semantic Kernel approach)
1. **AF Agent** (Agent Framework approach)

#### Key Migration Points
- **Service Type**: Register `AIAgent` instead of `OpenAIAssistantAgent`
- **Creation Method**: Use `CreateAIAgentAsync()` directly instead of creating `Assistant` first
- **Tool Registration**: Tools specified at creation time vs post-creation plugin addition
- **No Kernel Required**: AF agents don't need Kernel for tool calling
- **Direct Function Registration**: Use `AIFunctionFactory.Create()` vs plugin wrappers
- **Automatic Function Choice**: Built-in function calling behavior

## Key differences

### Agent Non-Streaming Invocation

Key differences in the method names from `Invoke` to `Run` and the return types.

#### Semantic Kernel

The Non-Streaming uses a streaming pattern `IAsyncEnumerable<AgentResponseItem<ChatMessageContent>>` for returning multiple agent messages.

```csharp
await foreach (var result in agent.InvokeAsync(userInput, thread, agentOptions))
{
    Console.WriteLine(result.Message);
}
```

#### Agent Framework

The Non-Streaming returns a single `AgentRunResponse` with the final agent message. 
This aligns with a simplified non-streaming experience for the API.

```csharp
var agentResponse = await agent.RunAsync(userInput, thread);
```

### Agent Streaming Invocation

Key differences in the method names from `Invoke` to `Run` and the return types.

#### Semantic Kernel

```csharp
await foreach (StreamingChatMessageContent update in agent.InvokeStreamingAsync(userInput, thread))
{
    Console.Write(update);
}
```

#### Agent Framework

Similar streaming API pattern with the key difference being that it `AgentRunResponseUpdate` including more agent related information per update.

```csharp
await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(userInput, thread))
{
    Console.Write(update); // Update is ToString() friendly
}
```

### Hosted Agent Thread Cleanup

In Agent framework threads don't have a deletion method anymore, 
the caller must know the provider of a given hosted agent thread and delete it 
using the provider client.

#### Semantic Kernel

Threads have a deletion method

i.e: OpenAI Assistants Provider
```csharp
await thread.DeleteAsync();
await assistantsClient.DeleteAssistantAsync(agent.Id);
```

#### Agent Framework 

Threads don't have a deletion method, knowing the thread source and using the source provider client is required

i.e: OpenAI Assistants Provider
```csharp
await assistantClient.DeleteThreadAsync(thread.ConversationId);
await assistantClient.DeleteAssistantAsync(agent.Id);
```

### Tool Function Signatures
**Problem**: SK plugin methods need `[KernelFunction]` attributes
```csharp
public class MenuPlugin
{
    [KernelFunction] // Required for SK
    public static MenuItem[] GetMenu() => ...;
}
```

**Solution**: AF can use methods directly without attributes
```csharp
public class MenuTools
{
    [Description("Get menu items")] // Only Description needed
    public static MenuItem[] GetMenu() => ...;
}
```

### Options Configuration
**Problem**: Complex options setup in SK
```csharp
var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
var options = new AgentInvokeOptions() { KernelArguments = new(settings) };
```

**Solution**: Simplified options in AF
```csharp
var options = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });
```

### Error Handling

#### Semantic Kernel
```csharp
try
{
    await foreach (var result in agent.InvokeAsync(userInput, thread))
    {
        // Handle individual results
        if (result.Message != null)
            Console.WriteLine(result.Message);
    }
}
catch (KernelException ex)
{
    // SK-specific exception handling
}
```

#### Agent Framework
```csharp
try
{
    var result = await agent.RunAsync(userInput, thread);
    Console.WriteLine(result);
}
catch (AIException ex)
{
    // AF-specific exception handling
}
```