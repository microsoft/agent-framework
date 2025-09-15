# Agent Step 13: Agent Running Processor Pattern

This sample demonstrates how to implement agent middleware using the processor pattern with Azure AI Foundry agents. It shows how to use `CallbackMiddlewareProcessor` and `CallbackEnabledAgent` to create reusable middleware components for content filtering and guardrails.

## What This Sample Shows

1. **Azure AI Foundry Integration**: Using Azure AI Foundry agents as the backend
2. **Processor Pattern**: Using `CallbackMiddlewareProcessor` to manage middleware collections
3. **Callback Middleware**: Creating reusable middleware classes inheriting from `CallbackMiddleware<TContext>`
4. **Fluent Configuration**: Using `.UseCallbacks()` builder pattern to configure middleware
5. **Content Filtering**: Implementing PII detection and content guardrails as middleware
6. **Streaming Support**: How processor-based middleware works with both regular and streaming responses

## Key Concepts

### Processor Pattern Architecture

This sample demonstrates the processor-based approach for agent middleware:

- **`CallbackMiddlewareProcessor`**: Manages collections of middleware and orchestrates execution
- **`CallbackEnabledAgent`**: Decorator that integrates with the processor for middleware execution
- **`CallbackMiddleware<TContext>`**: Type-safe base class for implementing middleware
- **`AgentInvokeCallbackContext`**: Rich context object providing access to messages, options, and responses

### Middleware Execution Pipeline

The processor manages middleware execution in a chain:
1. Processor identifies applicable middleware for the context type
2. Each middleware receives the context and a `next` delegate
3. Middleware can perform pre-processing before calling `next`
4. Middleware can perform post-processing after `next` returns
5. Context provides access to both input and output data

### Type-Safe Middleware Design

The processor pattern provides strong typing:
- **Context-specific**: Middleware only processes contexts it can handle
- **Thread-safe**: Processor uses `ConcurrentBag` for safe concurrent access
- **Extensible**: Easy to add new middleware types without changing existing code

## Usage Examples

### Processor Pattern Setup

```csharp
// Create Azure AI Foundry client
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create agent with processor-based middleware
var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .UseCallbacks(config =>
    {
        config.AddCallback(new PiiDetectionMiddleware());
        config.AddCallback(new GuardrailCallbackMiddleware());
    }).Build();
```

### PII Detection Middleware Implementation

```csharp
internal sealed class PiiDetectionMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Pre-processing: Filter input messages for PII
        context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        Console.WriteLine($"PII Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

        await next(context).ConfigureAwait(false);

        // Post-processing: Filter output messages
        if (!context.IsStreaming)
        {
            context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        }
        else
        {
            context.SetRawResponse(StreamingPiiDetectionAsync(context.RunStreamingResponse!));
        }
    }

    private static string FilterPii(string content)
    {
        var piiPatterns = new[]
        {
            new Regex(@"\b\d{3}-\d{3}-\d{4}\b", RegexOptions.Compiled), // Phone number
            new Regex(@"\b[\w\.-]+@[\w\.-]+\.\w+\b", RegexOptions.Compiled), // Email
            new Regex(@"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", RegexOptions.Compiled) // Full name
        };

        foreach (var pattern in piiPatterns)
        {
            content = pattern.Replace(content, "[REDACTED: PII]");
        }
        return content;
    }
}
```

### Guardrail Middleware Implementation

```csharp
internal sealed class GuardrailCallbackMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    private readonly string[] _forbiddenKeywords = { "harmful", "illegal", "violence" };

    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Pre-processing: Filter input messages for forbidden content
        context.Messages = this.FilterMessages(context.Messages);
        Console.WriteLine($"Guardrail Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

        await next(context).ConfigureAwait(false);

        // Post-processing: Filter output messages
        if (!context.IsStreaming)
        {
            context.Messages = this.FilterMessages(context.Messages);
        }
        else
        {
            context.SetRawResponse(StreamingGuardRailAsync(context.RunStreamingResponse!));
        }
    }

    private List<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, this.FilterContent(m.Text))).ToList();
    }

    private string FilterContent(string content)
    {
        foreach (var keyword in this._forbiddenKeywords)
        {
            if (content.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            {
                return "[REDACTED: Forbidden content]";
            }
        }
        return content;
    }
}
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
cd dotnet/samples/GettingStarted/Agents/Agent_Step13_Callbacks_AgentRunningProcessor
dotnet run
```

## Expected Output

The sample will demonstrate:
- Processor-based middleware execution with `CallbackMiddlewareProcessor`
- Content guardrails filtering harmful requests like "Tell me something harmful"
- PII detection and redaction for phone numbers, emails, and names
- Both regular and streaming response filtering through middleware
- Type-safe middleware implementation with `CallbackMiddleware<TContext>`

Example output:
```
=== Wording Guardrail ===
Guardrail Middleware - Filtered messages: [REDACTED: Forbidden content]
PII Middleware - Filtered messages: [REDACTED: Forbidden content]

=== PII detection ===
PII Middleware - Filtered messages: My name is [REDACTED: PII], call me at [REDACTED: PII] or email me at [REDACTED: PII]
```

## Next Steps

- Explore creating custom middleware classes for authentication, caching, or rate limiting
- Implement middleware that modifies requests or responses based on business rules
- Use the processor pattern for telemetry and monitoring in production applications
- Study the differences between processor pattern and decorator pattern approaches
- Create reusable middleware libraries that can be shared across multiple agents
