# Agent Step 11: Callback Middleware

This sample demonstrates how to use the callback middleware system with Azure AI Foundry agents to implement cross-cutting concerns such as logging, timing, and custom processing.

## What This Sample Shows

1. **Azure AI Foundry Integration**: Using Azure AI Foundry agents as the backend
2. **Basic Agent Usage**: Creating and using an agent without middleware
3. **Logging Middleware**: Using the built-in `LoggingCallbackMiddleware` to log agent invocations
4. **Custom Middleware**: Creating and using custom middleware for timing measurements
5. **Multiple Middleware**: Combining multiple middleware components in a pipeline
6. **Streaming Support**: How middleware works with streaming agent responses

## Key Concepts

### Callback Middleware Architecture

The callback middleware system uses a dedicated processor component that manages middleware chains:

- **`CallbackContext`**: Base class providing common context information
- **`AgentInvokeCallbackContext`**: Specific context for agent invocation operations
- **`ICallbackMiddleware<TContext>`**: Interface for implementing middleware
- **`CallbackMiddlewareBase<TContext>`**: Base class with convenient hooks
- **`CallbackMiddlewareProcessor`**: Manages and executes middleware chains

### Middleware Execution Order

Middleware is executed in the order it's registered:
1. First middleware's `OnProcessAsync` (before next call)
2. Second middleware's `OnProcessAsync` (before next call)
3. Actual agent operation
4. Second middleware's `OnProcessAsync` (after next call)
5. First middleware's `OnProcessAsync` (after next call)

### Error Handling

If an error occurs during agent execution, each middleware can handle it in its try/catch block before re-throwing the exception.

## Usage Examples

### Basic Middleware Setup

```csharp
// Create Azure AI Foundry agent
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());
var azureAgent = await persistentAgentsClient.CreateAIAgentAsync(model, name, instructions);

// Create middleware
var loggingMiddleware = new LoggingCallbackMiddleware(logger);
var middlewareProcessor = CallbackMiddlewareExtensions.CreateProcessor(loggingMiddleware);

// Create ChatClientAgent with middleware
var agent = new ChatClientAgent(
    azureAgent.GetChatClient(),
    options,
    loggerFactory,
    middlewareProcessor);
```

### Custom Middleware Implementation

```csharp
public class TimingMiddleware : CallbackMiddlewareBase<AgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        context.Properties["StartTime"] = DateTime.UtcNow;
        
        try
        {
            await next(context).ConfigureAwait(false);
            var duration = DateTime.UtcNow - (DateTime)context.Properties["StartTime"];
            Console.WriteLine($"Operation took {duration.TotalMilliseconds}ms");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Error: {ex.Message}");
            throw;
        }
    }
}
```

### Multiple Middleware

```csharp
var processor = CallbackMiddlewareExtensions.CreateProcessor(
    new LoggingCallbackMiddleware(logger),
    new TimingCallbackMiddleware(),
    new CustomAuthMiddleware());

var agent = new ChatClientAgent(
    azureAgent.GetChatClient(),
    options,
    loggerFactory,
    processor);
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
- Basic agent operation without middleware
- Detailed logging of agent invocations with timing information
- Custom timing measurements
- Streaming responses with middleware processing

## Next Steps

- Explore creating custom middleware for authentication, caching, or rate limiting
- Integrate middleware with dependency injection systems
- Use middleware for telemetry and monitoring in production applications
