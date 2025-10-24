## User Story

**Scenario:** Basic client-to-server text streaming

- **Given** an AG-UI client with an active thread and a single user text message
- **When** the client posts the message to the AG-UI server entrypoint
- **Then** the server emits a well-formed lifecycle event sequence and streams an assistant text response back to the client
- **And** the client aggregates the streamed text into a completed assistant message and adds it to the conversation history

## Minimal Implementation Surface

- **Integration Test:** End-to-end WebApplicationFactory test proving text streaming succeeds for a single user message.
	```csharp
	public sealed class BasicStreamingTests : IClassFixture<WebApplicationFactory<Program>>
	{
		private readonly HttpClient _client;

		public BasicStreamingTests(WebApplicationFactory<Program> factory);

		[Fact]
		public async Task ClientReceivesStreamedAssistantMessageAsync()
		{
			// Arrange
			using AGUIAgent agent = new AGUIAgent(this._client, "assistant", "Sample assistant", [], JsonDocument.Parse("null").RootElement);
			AgentThread thread = agent.GetNewThread();
			ChatMessage userMessage = new ChatMessage(ChatRole.User, "hello");

			// Act
			await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync([userMessage], thread, new AgentRunOptions(), CancellationToken.None))
			{
				// buffer updates
			}

			// Assert
			Assert.Collection(thread.Messages,
				message => Assert.Equal(ChatRole.User, message.Role),
				message => Assert.Equal(ChatRole.Assistant, message.Role));
		}
	}
	```
- **Client API surface:**
	- `AGUIAgent` extends `AIAgent`, accepts MEAI primitives (agent id, description, existing messages, state) and projects them onto AG-UI payloads.
	- Overrides of `RunAsync`/`RunStreamingAsync` return MEAI `AgentRunResponse`/`AgentRunResponseUpdate`, embedding AG-UI lifecycle updates inside `ChatResponseUpdate` content.
	- Internal translation layer maps incoming AG-UI events (`RunStarted`, `TextMessage*`, `RunFinished`, errors) into MEAI constructs (messages, `RunStartedContent`, etc.).
- **Server hosting glue:**
	- Single `MapAGUIAgent` extension registering the AG-UI endpoint and delegating to a user-supplied factory that returns an `AIAgent` built from MEAI abstractions.
	- Internal adapter translating AG-UI `RunAgentInput` (thread, run, messages, tools, context, forwarded props, state) into MEAI types before invoking the agent, and wrapping MEAI streaming responses back into AG-UI lifecycle/text events.
- **Shared contract:**
	- Minimal subset of AG-UI DTOs required for lifecycle and text events (no tools, state deltas yet) plus mapping utilities for MEAI conversions.
- **Test doubles:**
	- Fake `ChatClientAgent` implementation returning deterministic text chunks to validate streaming.

## Mapping Notes

- Lifecycle events (`RunStarted`, `RunFinished`, `RunError`, `StepStarted`, `StepFinished`) surface to consumers through `ChatResponseUpdate` content (e.g., `RunStartedContent`).
- Thread state and other AG-UI-specific payloads map into `AgentRunOptions.ChatOptions` via tools, context, and forwarded properties; state management can be represented as a dedicated client-side tool invocation.
- Thread identifiers translate into `AgentThread CreateNewThread()` usage; AG-UI run identifiers remain internal to streaming updates.
- Server responses stream via ASP.NET Core's `TypedResults.ServerSentEvents`, which expects `SseItem<T>` payloads mapped from AG-UI events.
- Basic input validation relies on `[Required]`/`[MinLength]` data annotations applied to the `RunAgentInput` transport type.

## C# Skeleton Surface

```csharp
public sealed class AGUIAgent : AIAgent
{
	public AGUIAgent(HttpClient httpClient, string id, string description, IEnumerable<ChatMessage> messages, JsonElement state);
	public override AgentThread GetNewThread();
	public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null);
	public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default);
	public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default);
}

public static class AGUIEndpointRouteBuilderExtensions
{
	public static IEndpointConventionBuilder MapAGUIAgent(this IEndpointRouteBuilder endpoints, string pattern, Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, JsonElement, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> agentFactory);
}

public sealed class RunStartedContent : AIContent
{
	public RunStartedContent(string threadId, string runId);
}

public sealed class RunFinishedContent : AIContent
{
	public RunFinishedContent(string threadId, string runId, string? result);
}

public sealed class RunErrorContent : AIContent
{
	public RunErrorContent(string message, string? code);
}

public sealed class StepStartedContent : AIContent
{
	public StepStartedContent(string stepName);
}

public sealed class StepFinishedContent : AIContent
{
	public StepFinishedContent(string stepName);
}

public sealed class BasicStreamingTests : IClassFixture<WebApplicationFactory<Program>>
{
	public BasicStreamingTests(WebApplicationFactory<Program> factory);
	[Fact]
	public Task ClientReceivesStreamedAssistantMessageAsync();
}

internal sealed class AGUIEventStreamProcessor
{
	public AGUIEventStreamProcessor();
	public AgentRunResponse MapRunStarted(RunStartedEvent evt);
	public AgentRunResponseUpdate MapTextEvents(IReadOnlyList<BaseEvent> events);
	public AgentRunResponse MapRunFinished(RunFinishedEvent evt);
	public AgentRunResponse MapRunError(RunErrorEvent evt);
}

internal abstract class BaseEvent
{
}

internal sealed class RunStartedEvent : BaseEvent
{
	public string ThreadId { get; set; }
	public string RunId { get; set; }
}

internal sealed class RunErrorEvent : BaseEvent
{
	public string Message { get; set; }
	public string? Code { get; set; }
}

internal sealed class TextMessageStartEvent : BaseEvent
{
	public string MessageId { get; set; }
	public string Role { get; set; }
}

internal sealed class TextMessageContentEvent : BaseEvent
{
	public string MessageId { get; set; }
	public string Delta { get; set; }
}

internal sealed class TextMessageEndEvent : BaseEvent
{
	public string MessageId { get; set; }
}

internal sealed class RunFinishedEvent : BaseEvent
{
	public string ThreadId { get; set; }
	public string RunId { get; set; }
	public string? Result { get; set; }
}

internal sealed class StepStartedEvent : BaseEvent
{
	public string StepName { get; set; }
}

internal sealed class StepFinishedEvent : BaseEvent
{
	public string StepName { get; set; }
}

internal sealed class RunAgentInput
{
	[Required]
	public string ThreadId { get; set; }

	[Required]
	public string RunId { get; set; }

	public JsonElement State { get; set; }

	[Required]
	[MinLength(1)]
	public IReadOnlyList<ChatMessage> Messages { get; set; }

	[Required]
	public IReadOnlyList<AITool> Tools { get; set; }

	[Required]
	public IReadOnlyDictionary<string, string> Context { get; set; }

	public JsonElement ForwardedProperties { get; set; }
}

internal sealed class AGUIRequestProcessor
{
	public AGUIRequestProcessor(AIAgent agent);
	public IAsyncEnumerable<BaseEvent> ExecuteAsync(IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, JsonElement state, IEnumerable<KeyValuePair<string, string>> contextValues, JsonElement forwardedProps, CancellationToken cancellationToken);
}

internal sealed class FakeChatClientAgent : ChatClientAgent
{
	public FakeChatClientAgent();
	public override Task<StreamingResponse> GetStreamingResponseAsync(ChatRequest request, CancellationToken cancellationToken);
}
```

## Implementation Sketches

### MapAGUIAgent

```csharp
public static IEndpointConventionBuilder MapAGUIAgent(this IEndpointRouteBuilder endpoints, string pattern, Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, JsonElement, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> agentFactory)
{
	// 1. Register a POST endpoint on the supplied pattern
	var builder = endpoints.MapPost(pattern, async (HttpContext context, RunAgentInput input, CancellationToken cancellationToken) =>
	{
		// 2. Obtain required services and options from HttpContext.RequestServices
		// 3. Model binding + data annotations ensure required fields are present (threadId, messages, etc.)
		var (messages, tools, state, contextValues, forwardedProps) = MapRunAgentInput(input);
		// 4. Invoke agentFactory with messages, tools, context, forwarded props, state to get AIAgent
		AIAgent agent = ResolveAgent(agentFactory, context, messages, tools, state, contextValues, forwardedProps);
		// 5. Create AGUIRequestProcessor and execute it to obtain IAsyncEnumerable<BaseEvent>
		IAsyncEnumerable<BaseEvent> events = CreateEventStream(agent, messages, tools, state, contextValues, forwardedProps, cancellationToken);
		// 6. Convert protocol events into SSE payloads expected by TypedResults.ServerSentEvents
		IAsyncEnumerable<SseItem<string>> sseStream = MapEventsToSseItems(events, cancellationToken);
		// 7. Return the built-in server-sent events result (TypedResults.ServerSentEvents)
		return TypedResults.ServerSentEvents(sseStream, cancellationToken);
	});

	return builder;
}
```

```csharp
// Helper signatures referenced above
private static (IEnumerable<ChatMessage> Messages, IEnumerable<AITool> Tools, JsonElement State, IEnumerable<KeyValuePair<string, string>> ContextValues, JsonElement ForwardedProperties) MapRunAgentInput(RunAgentInput input);
private static AIAgent ResolveAgent(Func<IEnumerable<ChatMessage>, IEnumerable<AITool>, JsonElement, IEnumerable<KeyValuePair<string, string>>, JsonElement, AIAgent> agentFactory, HttpContext context, IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, JsonElement state, IEnumerable<KeyValuePair<string, string>> contextValues, JsonElement forwardedProps);
private static IAsyncEnumerable<BaseEvent> CreateEventStream(AIAgent agent, IEnumerable<ChatMessage> messages, IEnumerable<AITool> tools, JsonElement state, IEnumerable<KeyValuePair<string, string>> contextValues, JsonElement forwardedProps, CancellationToken cancellationToken);
private static IAsyncEnumerable<SseItem<string>> MapEventsToSseItems(IAsyncEnumerable<BaseEvent> events, CancellationToken cancellationToken);
```
