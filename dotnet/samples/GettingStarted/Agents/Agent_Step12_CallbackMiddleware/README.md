# Agent Step 11: Callback Middleware

This sample demonstrates how to use the callback middleware system with Azure AI Foundry agents to implement cross-cutting concerns such as timing and custom processing.

## What This Sample Shows

1. **Azure AI Foundry Integration**: Using Azure AI Foundry agents as the backend
2. **Custom Middleware**: Creating and using custom middleware for timing measurements
3. **Fluent Configuration**: Using the `WithCallbacks` builder pattern to configure middleware
4. **Streaming Support**: How middleware works with both regular and streaming agent responses
5. **Response Access**: How middleware can access and process agent responses

## Key Concepts

### Callback Middleware Architecture

The callback middleware system provides a clean way to intercept and process agent operations:

- **`AgentInvokeCallbackContext`**: Provides context information for agent invocation operations
- **`CallbackMiddleware<TContext>`**: Base class for implementing middleware
- **Fluent Configuration**: Use `WithCallbacks` builder pattern to configure middleware

### Middleware Execution

Middleware receives the context and a `next` delegate:
1. Middleware can perform operations before calling `next`
2. Call `next(context)` to continue the pipeline
3. Middleware can perform operations after `next` returns
4. Access response data through the context properties

### Response Access

Middleware can access different types of responses:
- **Regular responses**: Access via `context.RunResponse`
- **Streaming responses**: Access via `context.RunStreamingResponse`
- **Error handling**: Use try/catch blocks around the `next` call

## Usage Examples

### Basic Middleware Setup

```csharp
// Create Azure AI Foundry client
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create agent with middleware using fluent configuration
var agent = persistentAgentsClient.CreateAIAgent(model)
    .WithCallbacks(builder =>
    {
        builder.AddCallback(new TimingCallbackMiddleware());
    });
```

### Custom Middleware Implementation

```csharp
internal sealed class TimingCallbackMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"[TIMING] Starting invocation for agent: {context.Agent.DisplayName}");
        var timingStart = DateTime.UtcNow;

        try
        {
            await next(context).ConfigureAwait(false);

            // Access response based on operation type
            if (!context.IsStreaming)
            {
                Console.WriteLine($"Response: {context.RunResponse?.Messages[0].Text}");
            }
            else
            {
                // Process streaming response
                await foreach (var update in context.RunStreamingResponse!)
                {
                    Console.WriteLine($"Streaming update: {update.Text}");
                }
            }

            var duration = DateTime.UtcNow - timingStart;
            Console.WriteLine($"[TIMING] Completed invocation in {duration.TotalMilliseconds:F1}ms");
        }
        catch (Exception exception)
        {
            Console.WriteLine($"[TIMING] Error: {exception.Message}");
            throw;
        }
    }
}
```

### Multiple Middleware

```csharp
var agent = persistentAgentsClient.CreateAIAgent(model)
    .WithCallbacks(builder =>
    {
        builder.AddCallback(new LoggingCallbackMiddleware());
        builder.AddCallback(new TimingCallbackMiddleware());
        builder.AddCallback(new CustomAuthMiddleware());
    });
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
cd dotnet/samples/GettingStarted/Agents/Agent_Step11_CallbackMiddleware
dotnet run
```

## Expected Output

The sample will demonstrate:
- Custom timing measurements for agent invocations
- Response processing for both regular and streaming operations
- Clean middleware implementation using the fluent configuration pattern

## Next Steps

- Explore creating custom middleware for authentication, caching, or rate limiting
- Implement middleware that modifies requests or responses
- Use middleware for telemetry and monitoring in production applications
- Combine multiple middleware for complex processing pipelines
