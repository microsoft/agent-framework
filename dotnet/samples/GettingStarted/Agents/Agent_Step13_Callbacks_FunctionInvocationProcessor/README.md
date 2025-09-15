# Agent Step 13: Function Invocation Processor Pattern

This sample demonstrates how to implement function invocation middleware using the processor pattern with Azure AI Foundry agents. It shows how to create reusable middleware classes for intercepting and processing function calls using the `CallbackMiddlewareProcessor` architecture.

## What This Sample Shows

1. **Azure AI Foundry Integration**: Using Azure AI Foundry agents as the backend
2. **Function Invocation Processor**: Using processor pattern for function-level middleware
3. **Callback Middleware Classes**: Creating reusable middleware inheriting from `CallbackMiddleware<TContext>`
4. **Fluent Configuration**: Using `.UseCallbacks()` builder pattern for function middleware
5. **Function Context Processing**: Working with function invocation contexts and arguments
6. **Tool Integration**: Intercepting AI function calls in a structured, reusable way

## Key Concepts

### Function Invocation Processor Architecture

This sample demonstrates the processor-based approach for function invocation middleware:

- **`CallbackMiddlewareProcessor`**: Manages collections of function invocation middleware
- **`CallbackEnabledAgent`**: Integrates with the processor for function middleware execution
- **`CallbackMiddleware<TContext>`**: Type-safe base class for function invocation middleware
- **Function Invocation Context**: Rich context providing access to function arguments and execution state

### Function Middleware Execution Pipeline

The processor manages function middleware execution:
1. Processor identifies applicable middleware for function invocation contexts
2. Each middleware receives the function context and a `next` delegate
3. Middleware can inspect or modify function arguments before calling `next`
4. Middleware can process function results after execution
5. Context provides access to function metadata and execution state

### Reusable Function Middleware Design

The processor pattern enables reusable function middleware:
- **Context-specific**: Middleware only processes function invocation contexts
- **Type-safe**: Strong typing for function invocation context and arguments
- **Composable**: Easy to combine multiple function middleware in a pipeline
- **Testable**: Middleware can be unit tested independently

## Usage Examples

### Function Invocation Processor Setup

```csharp
// Create Azure AI Foundry client
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create agent with function invocation middleware using processor pattern
var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .UseCallbacks(config =>
    {
        config.AddCallback(new UsedApiFunctionInvocationCallback());
        config.AddCallback(new CityInformationFunctionInvocationCallback());
    }).Build();
```

### Function Usage Tracking Middleware

```csharp
internal sealed class UsedApiFunctionInvocationCallback : CallbackMiddleware<AgentFunctionInvocationCallbackContext>
{
    public override async Task OnProcessAsync(AgentFunctionInvocationCallbackContext context, Func<AgentFunctionInvocationCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"[FUNCTION USAGE] Function '{context.Function.Metadata.Name}' is being invoked");
        Console.WriteLine($"[FUNCTION USAGE] IsStreaming: {context.IsStreaming}");

        var startTime = DateTime.UtcNow;

        await next(context).ConfigureAwait(false);

        var duration = DateTime.UtcNow - startTime;
        Console.WriteLine($"[FUNCTION USAGE] Function '{context.Function.Metadata.Name}' completed in {duration.TotalMilliseconds:F1}ms");
    }
}
```

### Parameter Inspection Middleware

```csharp
internal sealed class CityInformationFunctionInvocationCallback : CallbackMiddleware<AgentFunctionInvocationCallbackContext>
{
    public override async Task OnProcessAsync(AgentFunctionInvocationCallbackContext context, Func<AgentFunctionInvocationCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Inspect function arguments before execution
        if (context.Arguments.TryGetValue("location", out var location))
        {
            Console.WriteLine($"[CITY INFO] Requesting weather for city: {location}");

            // Could add validation, logging, or modification here
            if (string.IsNullOrWhiteSpace(location?.ToString()))
            {
                Console.WriteLine($"[CITY INFO] Warning: Empty location provided");
            }
        }

        await next(context).ConfigureAwait(false);

        // Could process function results here
        Console.WriteLine($"[CITY INFO] Function execution completed");
    }
}
```

### Running with Tools

```csharp
// Define a weather function
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

var thread = agent.GetNewThread();
var options = new ChatClientAgentRunOptions(new() { Tools = [AIFunctionFactory.Create(GetWeather)] });

// This will trigger the function middleware
var response = await agent.RunAsync("What's the weather in Seattle?", thread, options);
```

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
cd dotnet/samples/GettingStarted/Agents/Agent_Step13_Callbacks_FunctionInvocationProcessor
dotnet run
```

## Expected Output

The sample will demonstrate:
- Function invocation middleware using the processor pattern
- Function usage tracking and timing measurements
- Parameter inspection and validation for function calls
- Reusable middleware classes for function-level processing

Example output:
```
[FUNCTION USAGE] Function 'GetWeather' is being invoked
[FUNCTION USAGE] IsStreaming: False
[CITY INFO] Requesting weather for city: Seattle
[CITY INFO] Function execution completed
[FUNCTION USAGE] Function 'GetWeather' completed in 2.3ms
```

## Next Steps

- Explore creating custom function middleware for authentication, validation, or rate limiting
- Implement middleware that modifies function arguments or results
- Use function middleware for telemetry and monitoring of tool usage in production
- Create reusable function middleware libraries that can be shared across multiple agents
- Study the differences between function invocation processor and decorator patterns
- Combine function-level and agent-level middleware for comprehensive processing pipelines
