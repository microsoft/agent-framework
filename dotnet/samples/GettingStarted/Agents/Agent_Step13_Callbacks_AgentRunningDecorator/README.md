# Agent Step 13: Agent Running Decorator Pattern

This sample demonstrates how to implement agent middleware using the decorator pattern with Azure AI Foundry agents. It shows two approaches: direct decorator classes and context-based middleware for implementing guardrails and content filtering.

## What This Sample Shows

1. **Azure AI Foundry Integration**: Using Azure AI Foundry agents as the backend
2. **Decorator Pattern**: Creating custom agent decorators that inherit from `DelegatingAIAgent`
3. **Context-Based Middleware**: Using `AgentInvokeCallbackContext` for flexible middleware processing
4. **Content Filtering**: Implementing PII detection and content guardrails
5. **Streaming Support**: How decorators work with both regular and streaming agent responses
6. **Fluent Builder Pattern**: Using `.Use()` method to chain multiple middleware components

## Key Concepts

### Decorator Pattern Architecture

This sample demonstrates two decorator approaches for agent middleware:

- **`DelegatingAIAgent`**: Base class for creating agent decorators that wrap inner agents
- **`GuardrailCallbackAgent`**: Custom decorator implementing content filtering logic
- **`AgentInvokeCallbackContext`**: Context object for context-based middleware processing
- **Builder Integration**: Seamless integration with the agent builder pattern

### Decorator Implementation Approaches

1. **Direct Decorator Class**: Create a class inheriting from `DelegatingAIAgent` and override methods
2. **Context-Based Middleware**: Use `.Use()` with context and next delegate for inline processing
3. **Chaining**: Combine multiple decorators and context-based middleware in a single pipeline

### Content Filtering Features

The sample implements practical guardrails:
- **PII Detection**: Automatically redacts phone numbers, emails, and names
- **Content Guardrails**: Filters harmful or illegal content requests
- **Streaming Support**: Applies filtering to both regular and streaming responses

## Usage Examples

### Decorator Pattern Setup

```csharp
// Create Azure AI Foundry client
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Create agent with decorator and context-based middleware
var agent = persistentAgentsClient.CreateAIAgent(model).AsBuilder()
    .Use((innerAgent) => new GuardrailCallbackAgent(innerAgent)) // Direct decorator
    .Use(async (context, next) => // Context-based middleware
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
    })
    .Build();
```

### Custom Decorator Implementation

```csharp
internal sealed class GuardrailCallbackAgent : DelegatingAIAgent
{
    private readonly string[] _forbiddenKeywords = { "harmful", "illegal", "violence" };

    public GuardrailCallbackAgent(AIAgent innerAgent) : base(innerAgent) { }

    public override async Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var filteredMessages = this.FilterMessages(messages);
        Console.WriteLine($"Guardrail Middleware - Filtered messages: {new ChatResponse(filteredMessages).Text}");

        var response = await this.InnerAgent.RunAsync(filteredMessages, thread, options, cancellationToken);
        response.Messages = response.Messages.Select(m => new ChatMessage(m.Role, this.FilterContent(m.Text))).ToList();

        return response;
    }

    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var filteredMessages = this.FilterMessages(messages);
        await foreach (var update in this.InnerAgent.RunStreamingAsync(filteredMessages, thread, options, cancellationToken))
        {
            if (update.Text != null)
            {
                yield return new AgentRunResponseUpdate(update.Role, this.FilterContent(update.Text));
            }
            else
            {
                yield return update;
            }
        }
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
cd dotnet/samples/GettingStarted/Agents/Agent_Step13_Callbacks_AgentRunningDecorator
dotnet run
```

## Expected Output

The sample will demonstrate:
- Content guardrails filtering harmful requests like "Tell me something harmful"
- PII detection and redaction for phone numbers, emails, and names
- Both regular and streaming response filtering
- Decorator pattern implementation with `DelegatingAIAgent`
- Context-based middleware using `AgentInvokeCallbackContext`

Example output:
```
=== Wording Guardrail ===
Guardrail Middleware - Filtered messages: [REDACTED: Forbidden content]
PII Middleware - Filtered messages: [REDACTED: Forbidden content]

=== PII detection ===
PII Middleware - Filtered messages: My name is [REDACTED: PII], call me at [REDACTED: PII] or email me at [REDACTED: PII]
```

## Next Steps

- Explore creating custom decorators for authentication, caching, or rate limiting
- Implement decorators that modify requests or responses based on business logic
- Use decorators for telemetry and monitoring in production applications
- Combine multiple decorators and context-based middleware for complex processing pipelines
- Study the difference between decorator pattern and processor pattern approaches
