# Agent Step 13: Function Invocation Decorator Pattern

This sample demonstrates how to implement function invocation middleware using the decorator pattern with Azure AI Foundry agents. It shows how to intercept and process function calls before they are executed, providing logging and parameter inspection capabilities.

## What This Sample Shows

1. **Azure AI Foundry Integration**: Using Azure AI Foundry agents as the backend
2. **Function Invocation Middleware**: Intercepting function calls before execution
3. **Decorator Pattern**: Using `.Use()` method to chain function invocation middleware
4. **Parameter Inspection**: Accessing and logging function arguments
5. **Streaming Context**: Understanding streaming vs non-streaming function invocation contexts
6. **Tool Integration**: Working with AI functions and tools in the middleware pipeline

## Key Concepts

### Function Invocation Middleware Architecture

This sample demonstrates function-level middleware using the decorator pattern:

- **Function Invocation Context**: Access to function arguments, streaming state, and execution context
- **Decorator Pattern**: Using `.Use()` method to chain multiple function middleware
- **Parameter Access**: Inspecting and logging function arguments before execution
- **Streaming Awareness**: Understanding whether the function is called in streaming or non-streaming context

### Function Middleware Execution

Function middleware receives context and next delegate:
1. Middleware can inspect function arguments and context
2. Middleware can log or modify parameters before calling `next`
3. Call `next(arguments, cancellationToken)` to continue to the actual function
4. Middleware can process results after function execution

### Tool Integration Features

The sample demonstrates practical function middleware:
- **Parameter Logging**: Automatically log function arguments for debugging
- **Streaming Detection**: Identify whether function calls are in streaming context
- **Argument Inspection**: Access specific parameters like location for weather functions

## Usage Examples

### Function Invocation Middleware Setup

```csharp
// Create Azure AI Foundry client
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Define a function tool
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Create agent with function invocation middleware
var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .Use((functionInvocationContext, next, ct) =>
    {
        Console.WriteLine($"IsStreaming: {functionInvocationContext!.IsStreaming}");
        return next(functionInvocationContext.Arguments, ct);
    })
    .Use((functionInvocationContext, next, ct) =>
    {
        Console.WriteLine($"City Name: {(functionInvocationContext!.Arguments.TryGetValue("location", out var location) ? location : "not provided")}");
        return next(functionInvocationContext.Arguments, ct);
    })
    .Build();
```

### Running the Agent with Tools

```csharp
var thread = agent.GetNewThread();

// Configure the agent to use the weather function
var options = new ChatClientAgentRunOptions(new() { Tools = [AIFunctionFactory.Create(GetWeather)] });

// Ask a question that will trigger the function
var response = await agent.RunAsync("What's the weather in Seattle?", thread, options);
Console.WriteLine(response);
```

### Expected Function Middleware Output

When the agent calls the weather function, the middleware will output:
```
IsStreaming: False
City Name: Seattle
```

This shows that:
1. The function is being called in non-streaming mode
2. The location parameter "Seattle" was extracted from the function arguments
3. Both middleware components executed in sequence before the actual function call

## Prerequisites

Before running this sample, you need to set up Azure AI Foundry:

1. Set the following environment variables:
   - `AZURE_FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
   - `AZURE_FOUNDRY_PROJECT_MODEL_ID`: The model deployment name (optional, defaults to "gpt-4o-mini")

2. Ensure you're authenticated with Azure CLI:
   ```bash
   az login
   ```

## Running the Sample

```bash
cd dotnet/samples/GettingStarted/Agents/Agent_Step13_Callbacks_FunctionInvocationDecorator
dotnet run
```

## Expected Output

The sample will demonstrate:
- Function invocation middleware intercepting tool calls
- Parameter inspection and logging for function arguments
- Streaming context detection for function calls
- Decorator pattern implementation for function-level middleware

Example output:
```
=== Example: Agent with custom function middleware ===
IsStreaming: False
City Name: Seattle
The weather in Seattle is cloudy with a high of 15°C.
```

## Next Steps

- Explore creating custom function middleware for authentication, validation, or rate limiting
- Implement middleware that modifies function arguments or results
- Use function middleware for telemetry and monitoring of tool usage
- Combine function-level and agent-level middleware for comprehensive processing pipelines
- Study the difference between function invocation middleware and agent running middleware
