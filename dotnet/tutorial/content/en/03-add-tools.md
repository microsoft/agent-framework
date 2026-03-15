# Adding Tools

**Sample:** `dotnet/samples/01-get-started/02_add_tools/`

Tools let the agent call .NET functions on your behalf. The LLM decides when and how to call them based on the conversation.

## The Complete Program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates how to use a ChatClientAgent with function tools.
// It shows both non-streaming and streaming agent interactions using menu-related tools.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create the chat client and agent, and provide the function tool to the agent.
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are a helpful assistant", tools: [AIFunctionFactory.Create(GetWeather)]);

// Non-streaming agent interaction with function tools.
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?"));

// Streaming agent interaction with function tools.
await foreach (var update in agent.RunStreamingAsync("What is the weather like in Amsterdam?"))
{
    Console.WriteLine(update);
}
```

## How Tools Work

When you pass tools to an agent, the following happens on each invocation:

1. MAF sends the conversation + tool schemas to the LLM
2. The LLM decides to call `GetWeather` with `location = "Amsterdam"`
3. `FunctionInvokingChatClient` (built into MAF) calls your local function
4. The result is appended to the conversation
5. The LLM generates a final response using the tool output

This is the standard [OpenAI function calling](https://platform.openai.com/docs/guides/function-calling) flow, abstracted away.

## Defining a Tool

```csharp
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";
```

The `[Description]` attributes on the **method** and **parameters** become the JSON schema the LLM uses to decide when and how to call the function. Write clear descriptions — the LLM reads them.

## Registering Tools

```csharp
.AsAIAgent(
    instructions: "You are a helpful assistant",
    tools: [AIFunctionFactory.Create(GetWeather)]
)
```

`AIFunctionFactory.Create` reflects over your method signature and description attributes to produce an `AIFunction` with the correct schema. Pass multiple tools as an array.

## Real-World Tool Patterns

Tools don't have to be static mock functions. Common patterns:

```csharp
// Instance method on a service
AIFunction searchTool = AIFunctionFactory.Create(searchService.SearchAsync);

// Lambda (for simple cases)
AIFunction dateTool = AIFunctionFactory.Create(
    () => DateTime.UtcNow.ToString("R"),
    name: "GetCurrentTime",
    description: "Returns the current UTC time.");

// Async tool
[Description("Look up order status in the database.")]
static async Task<string> GetOrderStatus([Description("The order ID.")] string orderId)
{
    var order = await db.Orders.FindAsync(orderId);
    return order?.Status ?? "Not found";
}
```

## Running the Sample

```bash
cd dotnet/samples/01-get-started/02_add_tools
dotnet run
```

## Key Takeaways

- Tools are .NET methods decorated with `[Description]` attributes
- `AIFunctionFactory.Create` generates the JSON schema automatically
- Pass tools via the `tools:` parameter of `.AsAIAgent()`
- MAF handles the function-calling loop — you just implement the function
