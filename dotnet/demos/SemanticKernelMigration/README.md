# Semantic Kernel to Agent Framework Migration Guide

This repository contains **11 separate console application projects** demonstrating how to transition from **Semantic Kernel (SK)** to the new **Agent Framework (AF)**. Each project shows side-by-side comparisons of equivalent functionality in both frameworks and can be run independently.

## Table of Contents

- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Key Migration Concepts](#key-migration-concepts)
- [OpenAI Samples](#openai-samples)
- [Azure AI Foundry Samples](#azure-ai-foundry-samples)
- [OpenAI Assistant Samples](#openai-assistant-samples)
- [Common Migration Patterns](#common-migration-patterns)
- [Running Individual Projects](#running-individual-projects)

## Quick Start

### 1. Set Environment Variables

**For Azure AI Foundry projects:**
```powershell
$env:AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
```

**For OpenAI projects:**
```powershell
$env:OPENAI_API_KEY = "sk-..."
```

### 2. Run Any Project
```powershell
cd "Azure AI Foundry\Step01_Basics"
dotnet run

cd "OpenAI\Step03_ToolCall"
dotnet run

cd "OpenAI Assistant\Step04_CodeInterpreter"
dotnet run
```

## Project Structure

```
MigrationGuidance/
├── Azure AI Foundry/          (4 projects)
│   ├── Step01_Basics/
│   ├── Step02_DependencyInjection/
│   ├── Step03_ToolCall/
│   └── Step04_CodeInterpreter/
├── OpenAI/                    (3 projects)
│   ├── Step01_Basics/
│   ├── Step02_DependencyInjection/
│   └── Step03_ToolCall/
└── OpenAI Assistant/          (4 projects)
    ├── Step01_Basics/
    ├── Step02_DependencyInjection/
    ├── Step03_ToolCall/
    └── Step04_CodeInterpreter/
```

Each project demonstrates:
- **Step01_Basics**: Basic agent creation and invocation
- **Step02_DependencyInjection**: Using dependency injection patterns
- **Step03_ToolCall**: Function/tool calling capabilities
- **Step04_CodeInterpreter**: Code interpreter functionality

## Configuration

### Environment Variables
- **Azure AI Foundry**: `AZURE_OPENAI_ENDPOINT`
- **OpenAI/OpenAI Assistant**: `OPENAI_API_KEY`

### Interactive Mode
If environment variables are not set, the demos will prompt you to enter values interactively.

### Debug Mode (Optional)
```powershell
$env:AF_SHOW_ALL_DEMO_SETTING_VALUES = "Y"
```

## Key Migration Concepts

### Namespace Changes
```csharp
// Semantic Kernel
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;

// Agent Framework
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
```

### Agent Creation Pattern
```csharp
// SK: Multi-step setup
var builder = Kernel.CreateBuilder().AddOpenAIChatClient(modelId, apiKey);
var agent = new ChatCompletionAgent() { 
    Kernel = builder.Build(), 
    Name = "Agent",
    Instructions = "Instructions"
};

// AF: Single fluent call
var agent = new OpenAIClient(apiKey).GetChatClient(modelId)
    .CreateAIAgent(name: "Agent", instructions: "Instructions");
```

### Thread Management
```csharp
// SK: Manual thread creation
var thread = new ChatHistoryAgentThread();

// AF: Built-in thread management
var thread = agent.GetNewThread();
```

### Invocation Patterns
```csharp
// SK: Complex options setup
var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
var options = new AgentInvokeOptions() { KernelArguments = new(settings) };
await foreach (var result in agent.InvokeAsync(input, thread, options)) { }

// AF: Simplified options
var options = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });
var result = await agent.RunAsync(input, thread, options);
```

## OpenAI Samples

### OpenAI - Step01_Basics

**Purpose**: Basic agent creation and conversation handling

#### Before (Semantic Kernel)
```csharp
var builder = Kernel.CreateBuilder().AddOpenAIChatClient(modelId, apiKey);

var agent = new ChatCompletionAgent() { 
    Kernel = builder.Build(), 
    Name = "Joker",
    Instructions = "You are good at telling jokes.",
};

var thread = new ChatHistoryAgentThread();
var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
var agentOptions = new AgentInvokeOptions() { KernelArguments = new(settings) };

await foreach (var result in agent.InvokeAsync(userInput, thread, agentOptions))
{
    Console.WriteLine(result.Message);
}
```

#### After (Agent Framework)
```csharp
var agent = new OpenAIClient(apiKey).GetChatClient(modelId)
    .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes.");

var thread = agent.GetNewThread();
var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

var result = await agent.RunAsync(userInput, thread, agentOptions);
Console.WriteLine(result);
```

#### Key Migration Points
- **Agent Creation**: Single fluent call vs multi-step builder pattern
- **Thread Management**: `GetNewThread()` vs manual `ChatHistoryAgentThread`
- **Invocation**: `RunAsync()` returns single result vs `InvokeAsync()` returns enumerable
- **Options**: `ChatClientAgentRunOptions` vs `AgentInvokeOptions` with `KernelArguments`

### OpenAI - Step02_DependencyInjection

**Purpose**: Using dependency injection with agents

#### Before (Semantic Kernel)
```csharp
var serviceCollection = new ServiceCollection();
serviceCollection.AddKernel().AddOpenAIChatClient(modelId, apiKey);
serviceCollection.AddTransient((sp) => new ChatCompletionAgent()
{
    Kernel = sp.GetRequiredService<Kernel>(),
    Name = "Joker",
    Instructions = "You are good at telling jokes."
});

await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
var agent = serviceProvider.GetRequiredService<ChatCompletionAgent>();
```

#### After (Agent Framework)
```csharp
var serviceCollection = new ServiceCollection();
serviceCollection.AddTransient((sp) => new OpenAIClient(apiKey)
    .GetChatClient(modelId)
    .CreateAIAgent(name: "Joker", instructions: "You are good at telling jokes."));

await using ServiceProvider serviceProvider = serviceCollection.BuildServiceProvider();
var agent = serviceProvider.GetRequiredService<AIAgent>();
```

#### Key Migration Points
- **Service Registration**: Direct agent creation vs kernel-based approach
- **Dependencies**: No need for separate `Kernel` service registration
- **Type**: `AIAgent` interface vs concrete `ChatCompletionAgent` class

### OpenAI - Step03_ToolCall

**Purpose**: Function calling and tool integration

#### Before (Semantic Kernel)
```csharp
ChatCompletionAgent agent = new()
{
    Instructions = "Answer questions about the menu",
    Name = "Host",
    Kernel = builder.Build(),
    Arguments = new KernelArguments(new PromptExecutionSettings() { 
        FunctionChoiceBehavior = FunctionChoiceBehavior.Auto() 
    }),
};

// Requires plugin wrapper with [KernelFunction] attributes
agent.Kernel.Plugins.Add(KernelPluginFactory.CreateFromType<MenuPlugin>());
```

#### After (Agent Framework)
```csharp
var agent = new OpenAIClient(apiKey).GetChatClient(modelId).CreateAIAgent(
    name: "Host", 
    instructions: "Answer questions about the menu",
    tools: [
        AIFunctionFactory.Create(MenuTools.GetMenu),
        AIFunctionFactory.Create(MenuTools.GetSpecials),
        AIFunctionFactory.Create(MenuTools.GetItemPrice)
    ]);
```

#### Key Migration Points
- **Tool Registration**: Direct function registration vs plugin system
- **Function Attributes**: No need for `[KernelFunction]` wrapper classes
- **Function Choice**: Built-in auto function calling vs explicit `FunctionChoiceBehavior`
- **Setup**: Tools defined at agent creation vs post-creation plugin addition

## Azure AI Foundry Samples

### Azure AI Foundry - Step01_Basics

**Purpose**: Basic Azure AI Foundry agent usage

#### Before (Semantic Kernel)
```csharp
var azureAgentClient = AzureAIAgent.CreateAgentsClient(azureEndpoint, new AzureCliCredential());

PersistentAgent definition = await azureAgentClient.Administration.CreateAgentAsync(
    modelId, name: "GenerateStory", instructions: "You are good at telling jokes.");

AzureAIAgent agent = new(definition, azureAgentClient);
var thread = new AzureAIAgentThread(azureAgentClient);

AzureAIAgentInvokeOptions options = new() { MaxPromptTokens = 1000 };
var result = await agent.InvokeAsync(userInput, thread, options).FirstAsync();
```

#### After (Agent Framework)
```csharp
var azureAgentClient = new PersistentAgentsClient(azureEndpoint, new AzureCliCredential());

var agent = await azureAgentClient.CreateAIAgentAsync(
    modelId, name: "GenerateStory", instructions: "You are good at telling jokes.");

var thread = agent.GetNewThread();
var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

var result = await agent.RunAsync(userInput, thread, agentOptions);
```

#### Key Migration Points
- **Client Creation**: `PersistentAgentsClient` vs `AzureAIAgent.CreateAgentsClient()`
- **Agent Creation**: Direct `CreateAIAgentAsync()` vs separate definition and wrapper
- **Thread Management**: Built-in `GetNewThread()` vs manual `AzureAIAgentThread`
- **Options**: Unified `ChatClientAgentRunOptions` vs `AzureAIAgentInvokeOptions`

## OpenAI Assistant Samples

### OpenAI Assistant - Step01_Basics

**Purpose**: OpenAI Assistant API integration

#### Before (Semantic Kernel)
```csharp
var assistantsClient = new AssistantClient(apiKey);

Assistant assistant = await assistantsClient.CreateAssistantAsync(
    modelId, name: "Joker", instructions: "You are good at telling jokes.");

OpenAIAssistantAgent agent = new(assistant, assistantsClient);
var thread = new OpenAIAssistantAgentThread(assistantsClient);

var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
var agentOptions = new OpenAIAssistantAgentInvokeOptions() { 
    KernelArguments = new(settings) 
};

await foreach (var result in agent.InvokeAsync(userInput, thread, agentOptions)) { }
```

#### After (Agent Framework)
```csharp
var assistantClient = new AssistantClient(apiKey);

var agent = await assistantClient.CreateAIAgentAsync(
    modelId, name: "Joker", instructions: "You are good at telling jokes.");

var thread = agent.GetNewThread();
var agentOptions = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });

var result = await agent.RunAsync(userInput, thread, agentOptions);
```

#### Key Migration Points
- **Agent Creation**: Direct `CreateAIAgentAsync()` vs separate assistant creation and wrapping
- **Thread Management**: Built-in thread management vs manual thread creation
- **Options**: Simplified options vs complex `KernelArguments` setup
- **Invocation**: Single result vs enumerable results

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

# OpenAI Assistant Examples
cd "OpenAI Assistant\Step01_Basics"
dotnet run

cd "OpenAI Assistant\Step04_CodeInterpreter"
dotnet run
```

### What Each Demo Shows
Each project demonstrates **side-by-side comparisons** of:
1. **AF Agent** (Agent Framework approach) - The new way
2. **SK Agent** (Semantic Kernel approach) - The legacy way

### OpenAI Assistant - Step02_DependencyInjection

**Purpose**: Dependency injection with OpenAI Assistant agents

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

### OpenAI Assistant - Step03_ToolCall

**Purpose**: Function calling with OpenAI Assistant agents

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

#### Semantic Kernel (OpenAI Assistant)
```csharp
// Manual cleanup required
await thread.DeleteAsync();
await assistantsClient.DeleteAssistantAsync(agent.Id);
```

#### Agent Framework (OpenAI Assistant)
```csharp
// Consistent cleanup across providers
await assistantClient.DeleteThreadAsync(thread.ConversationId);
await assistantClient.DeleteAssistantAsync(agent.Id);
```

## Common Gotchas and Solutions

### 1. Async Service Registration
**Problem**: Trying to use async methods in DI registration
```csharp
// This won't work
services.AddTransient(async (sp) => await client.CreateAIAgentAsync(...));
```

**Solution**: Use `GetAwaiter().GetResult()` for synchronous DI registration
```csharp
services.AddTransient((sp) => client.CreateAIAgentAsync(...).GetAwaiter().GetResult());
```

### 2. Tool Function Signatures
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

### 3. Thread Lifecycle Management
**Problem**: Different thread cleanup patterns between frameworks

**Solution**: Use consistent cleanup patterns per provider:
```csharp
// OpenAI Assistant
await assistantClient.DeleteThreadAsync(thread.ConversationId);

// Azure AI Foundry
await azureClient.Threads.DeleteThreadAsync(thread.ConversationId);
```

### 4. Options Configuration
**Problem**: Complex options setup in SK
```csharp
var settings = new OpenAIPromptExecutionSettings() { MaxTokens = 1000 };
var options = new AgentInvokeOptions() { KernelArguments = new(settings) };
```

**Solution**: Simplified options in AF
```csharp
var options = new ChatClientAgentRunOptions(new() { MaxOutputTokens = 1000 });
```

## Performance Considerations

### Agent Creation
- **SK**: Multiple object allocations (Kernel, Agent, Settings)
- **AF**: Single fluent call with optimized object creation

### Memory Usage
- **SK**: Higher memory footprint due to Kernel overhead
- **AF**: Reduced memory usage with streamlined architecture

### Execution Speed
- **SK**: Additional abstraction layers can impact performance
- **AF**: Direct API integration provides better performance
