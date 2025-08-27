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
- **Namespace Updates**: From `Microsoft.SemanticKernel` to `Microsoft.Extensions.AI`
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

// Keep these for SK compatibility during migration
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
Register tools directly instead of using plugin wrappers:

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
Simplify service registration:

```csharp
// Old
services.AddKernel().AddProvider(...);
services.AddTransient<SpecificAgent>(...);

// New
services.AddTransient<AIAgent>(() => client.CreateAIAgent(...));
```

## Running Individual Projects

Each migration demo is now a **separate console application project** that can be run independently:

### Run Specific Projects
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
Each project demonstrates **side-by-side comparisons** of:
1. **AF Agent** (Agent Framework approach) - The new way
2. **SK Agent** (Semantic Kernel approach) - The legacy way

### OpenAI Assistants - Step02_DependencyInjection

**Purpose**: Dependency injection with OpenAI Assistants agents

#### Before (Semantic Kernel)
```csharp
var serviceCollection = new ServiceCollection();
serviceCollection.AddSingleton((sp) => new AssistantClient(apiKey));
serviceCollection.AddKernel().AddOpenAIChatClient(modelId, apiKey);
serviceCollection.AddTransient<OpenAIAssistantAgent>((sp) =>
{
    var assistantsClient = sp.GetRequiredService<AssistantClient>();
    Assistant assistant = assistantsClient.CreateAssistantAsync(modelId, name: "Joker", instructions: "You are good at telling jokes.")
        .GetAwaiter().GetResult();
    return new OpenAIAssistantAgent(assistant, assistantsClient);
});

await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
var agent = serviceProvider.GetRequiredService<OpenAIAssistantAgent>();
```

#### After (Agent Framework)
```csharp
var serviceCollection = new ServiceCollection();
serviceCollection.AddSingleton((sp) => new AssistantClient(apiKey));
serviceCollection.AddTransient<AIAgent>((sp) =>
{
    var assistantClient = sp.GetRequiredService<AssistantClient>();
    var agent = assistantClient.CreateAIAgentAsync(modelId, name: "Joker", instructions: "You are good at telling jokes.")
        .GetAwaiter().GetResult();
    return agent;
});

await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
var agent = serviceProvider.GetRequiredService<AIAgent>();
```

#### Key Migration Points
- **Service Type**: Register `AIAgent` instead of `OpenAIAssistantAgent`
- **Creation Method**: Use `CreateAIAgentAsync()` directly instead of creating `Assistant` first
- **No Kernel Dependency**: No need to register Kernel services for AF agents

### OpenAI Assistants - Step03_ToolCall

**Purpose**: Function calling with OpenAI Assistants agents

#### Before (Semantic Kernel)
```csharp
var builder = Kernel.CreateBuilder();
var assistantsClient = new AssistantClient(apiKey);

Assistant assistant = await assistantsClient.CreateAssistantAsync(
    modelId, name: "Host", instructions: "Answer questions about the menu");

OpenAIAssistantAgent agent = new(assistant, assistantsClient)
{
    Kernel = builder.Build(),
    Arguments = new KernelArguments(new OpenAIPromptExecutionSettings()
    {
        MaxTokens = 1000,
        FunctionChoiceBehavior = FunctionChoiceBehavior.Auto()
    }),
};

// Requires plugin wrapper
agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromType<MenuPlugin>());
```

#### After (Agent Framework)
```csharp
var assistantClient = new AssistantClient(apiKey);

var agent = await assistantClient.CreateAIAgentAsync(
    modelId,
    name: "Host",
    instructions: "Answer questions about the menu",
    tools: [
        AIFunctionFactory.Create(MenuTools.GetMenu),
        AIFunctionFactory.Create(MenuTools.GetSpecials),
        AIFunctionFactory.Create(MenuTools.GetItemPrice)
    ]);
```

#### Key Migration Points
- **Tool Registration**: Tools specified at creation time vs post-creation plugin addition
- **No Kernel Required**: AF agents don't need Kernel for tool calling
- **Direct Function Registration**: Use `AIFunctionFactory.Create()` vs plugin wrappers
- **Automatic Function Choice**: Built-in function calling behavior

## Advanced Migration Scenarios

### Error Handling Differences

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

### Streaming Differences

#### Semantic Kernel
```csharp
await foreach (var update in agent.InvokeStreamingAsync(userInput, thread))
{
    Console.Write(update.Message); // Update is not ToString() friendly, Message property needed
}
```

#### Agent Framework
```csharp
await foreach (var update in agent.RunStreamingAsync(userInput, thread))
{
    Console.Write(update); // Update is ToString() friendly
}
```

### Cleanup Patterns

#### Semantic Kernel (OpenAI Assistants)
```csharp
// Manual cleanup required
await thread.DeleteAsync();
await assistantsClient.DeleteAssistantAsync(agent.Id);
```

#### Agent Framework (OpenAI Assistants)
```csharp
// Consistent cleanup across providers
await assistantClient.DeleteThreadAsync(thread.ConversationId);
await assistantClient.DeleteAssistantAsync(agent.Id);
```

## Common Gotchas and Solutions

### 1. Tool Function Signatures
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

### 2. Thread Lifecycle Management
**Problem**: Different thread cleanup patterns between frameworks

**Solution**: Use consistent cleanup patterns per provider:
```csharp
// OpenAI Assistant
await assistantClient.DeleteThreadAsync(thread.ConversationId);

// Azure AI Foundry
await azureClient.Threads.DeleteThreadAsync(thread.ConversationId);
```

### 3. Options Configuration
**Problem**: Complex options setup in SK
```csharp
var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
var options = new AgentInvokeOptions() { KernelArguments = new(settings) };
```

**Solution**: Simplified options in AF
```csharp
var options = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });
```
