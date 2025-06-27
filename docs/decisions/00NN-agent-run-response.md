---
# These are optional elements. Feel free to remove any of them.
status: proposed {proposed | rejected | accepted | deprecated | … | superseded by [ADR-0001](0001-madr-architecture-decisions.md)}
contact: westey-m {person proposing the ADR}
date: 2025-06-24 {YYYY-MM-DD when the decision was last updated}
deciders: {list everyone involved in the decision}
consulted: {list everyone whose opinions are sought (typically subject-matter experts); and with whom there is a two-way communication}
informed: {list everyone who is kept up-to-date on progress; and with whom there is a one-way communication}
---

# Agent Run Responses Design

## Context and Problem Statement

Agents may produce lots of output during a run including

1. General response messages to the user
2. Structured confirmation requests to the user
3. Tool invocation activities executed (both local and remote).  For information only.
4. Reasoning/Thinking output. For information only.
5. Handoffs / transitions from agent to agent where an agent contains sub agents.
6. An indication that the agent is responding (i.e. typing) as if it's a real human.
7. Complete messages in addition to updates, when streaming
8. Id for long running process that is launched
9. and more

We need to ensure that with this diverse list of output, we are able to

- Support all with abstractions where needed
- Provide a simple getting started experience that doesn't overwhelm users

### Agent response data types

When comparing various agent SDKs and protocols, agent output is often divided into two categories:

1. **Final Response**: The final response from the agent, which communicates the result of the agent's work to the caller in natural language, including cases where the agent finished because it requires more input from the user. Let's call this **Primary** output.
2. **Processing Updates**: Updates while the agent is running, which are informational only, and does not allow any actions to be taken by the caller that modify the behavior of the agent before completing the run. Let's call this **Secondary** output.

A potential third category is:

3. **Long Running**: A response that does not contain a final response or updates, but rather a reference to a long running task.

### Different use cases for Primary and Secondary output

To solve complex problems, many agents must be used together. These agents typically have their own capabilities and responsibilities and communicate via input messages and final responses/handoff calls, while the internal workings of each agent is not of interest to the other agents participating in solving the problem.

When an agent is in conversation with one or more humans, the information that may be displayed to the user(s) can vary. E.g. When an agent is part of a conversation with multiple humans it may be asked to perform tasks by the humans, and they may not want a stream of distracting updates posted to the conversation, but rather just a final response.  On the other hand, if an agent is being used by a single human to perform a task, the human may be waiting for the agent to complete the task.  Therefore, they may be interested in getting updates of what the agent is doing.

Where agents are nested, consumers would also likely would want to constrain the amount of data from an agent that bubbles up into higher level conversations to avoid exceeding the context window, therefore limiting it to final response only.

### Comparison with other SDKs / Protocols

Approaches observed from the compared SDKs:

1. Response object with separate properties for Primary and Secondary
2. Response stream that contains Primary and Secondary entries and callers need to filter.
3. Response containing just Primary.

| SDK | Non-Streaming | Streaming |
|-|-|-|
| AutoGen | **Approach 1** Separates messages into Agent-Agent (maps to Primary) and Internal (maps to Secondary) and these are returned as separate properties on the agent response object.  See [types of messages](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/messages.html#types-of-messages) and [Response](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.base.html#autogen_agentchat.base.Response) | **Approach 2** Returns a stream of internal events and the last item is a Response object. See [ChatAgent.on_messages_stream](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.base.html#autogen_agentchat.base.ChatAgent.on_messages_stream) |
| OpenAI Agent SDK | **Approach 1** Separates new_items (Primary+Secondary) from final output (Primary) as separate properties on the [RunResult](https://github.com/openai/openai-agents-python/blob/main/src/agents/result.py#L39) | **Approach 1** Similar to non-streaming, has a way of streaming updates via a method on the response object which includes all data, and then a separate final output property on the response object which is populated only when the run is complete. See [RunResultStreaming](https://github.com/openai/openai-agents-python/blob/main/src/agents/result.py#L136) |
| Google ADK | **Approach 2** [Emits events](https://google.github.io/adk-docs/runtime/#step-by-step-breakdown) with [FinalResponse](https://github.com/google/adk-java/blob/main/core/src/main/java/com/google/adk/events/Event.java#L232) true (Primary) / false (Secondary) and callers have to filter out those with false to get just the final response message | **Approach 2** Similar to non-streaming except [events](https://google.github.io/adk-docs/runtime/#streaming-vs-non-streaming-output-partialtrue) are emitted with [Partial](https://github.com/google/adk-java/blob/main/core/src/main/java/com/google/adk/events/Event.java#L133) true to indicate that they are streaming messages. A final non partial event is also emitted. |
| AWS (Strands) | **Approach 3** Returns an [AgentResult](https://strandsagents.com/latest/api-reference/agent/#strands.agent.agent_result.AgentResult) (Primary) with messages and a reason for the run's completion. | **Approach 2** [Streams events](https://strandsagents.com/latest/api-reference/agent/#strands.agent.agent.Agent.stream_async) (Primary+Secondary) including, response text, current_tool_use, even data from "callbacks" (strands plugins) |
| LangGraph | TBD | TBD |
| Agno | **Combination of various approaches** Returns a [RunResponse](https://docs.agno.com/reference/agents/run-response) object with text content, messages (essentially chat history including inputs and instructions), reasoning and thinking text properties. Secondary events could potentially be extracted from messages. | **Approach 2** Returns [RunResponseEvent](https://docs.agno.com/reference/agents/run-response#runresponseevent-types-and-attributes) objects including tool call, memory update, etc, information, where the [RunResponseCompletedEvent](https://docs.agno.com/reference/agents/run-response#runresponsecompletedevent) has similar properties to RunResponse|
| A2A | **Approach 3** Returns a [Task or Message](https://a2aproject.github.io/A2A/latest/specification/#71-messagesend) where the message is the final result (Primary) and task is a reference to a long running process. | **Approach 2** Returns a [stream](https://a2aproject.github.io/A2A/latest/specification/#72-messagestream) that contains task updates (Secondary) and a final message (Primary) |
| Protocol Activity | **Approach 2** Single stream of responses including secondary events and final response messages (Primary). | No separate behavior for streaming. |

## Decision Drivers

- Solutions provides an easy to use experience for users who are getting started and just want the answer to a question.
- Solution must be extensible to future requirements, e.g. long running agent processes.
- Experience is in line or better than the best in class experience from other SDKs

## Response Type Options

- **Option 1** Run: Messages List contains mix of Primary and Secondary content, RunStreaming: Stream of Primary + Secondary
  - **Option 1.1** Updates do not use `TextContent`
  - **Option 1.2** Presence of Secondary Content is determined by a runtime parameter
  - **Option 1.3** Use ChatClient response types
  - **Option 1.4** Return derived ChatClient response types
- **Option 2** Run: Container with Primary and Secondary Properties, RunStreaming: Stream of Primary + Secondary
  - **Option 2.1** Response types extend MEAI types
  - **Option 2.2** New Response types
- **Option 3** Run: Primary-only, RunStreaming: Stream of Primary + Secondary
- **Option 4** Remove Run API and retain RunStreaming API only, which returns a Stream of Primary + Secondary.

Since the suggested options vary only for the non-streaming case, the following detailed explanations for each
focuses on the non-streaming case.

### Option 1 Run: Messages List contains mix of Primary and Secondary content, RunStreaming: Stream of Primary + Secondary

Run returns a `Task<ChatResponse>` and RunStreaming returns a `IAsyncEnumerable<ChatResponseUpdate>`.
For Run, the returned `ChatResponse.Messages` contains an ordered list of messages that contain both the updates and the final response.
The last message should be considered the final response.

`ChatResponse.Text` automatically aggregates all text from any `TextContent` items in all `ChatMessage` items in the response.
If we can ensure that no updates ever contain `TextContent`, this will mean that `ChatResponse.Text` will always contain
the final response text. See option 1.1.
If we cannot ensure this, either the solution or usage becomes more complex, see 1.3 and 1.4.

#### Option 1.1 Updates do not use `TextContent`

`ChatResponse.Text` aggregates all `TextContent` values, and no secondary updates use `TextContent`
so `ChatResponse.Text` will always contain the final response.

```csharp
// Since text contains the final response, it's a good getting started experience.
var response = agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers can still get access to all updates too.
foreach (var update in response.Messages)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Easy and familiar user experience, reuse response types from IChatClient.
- **CONS**: Requires all implementations to avoid using `TextContent` for anything but the final response.

#### Option 1.2 Presence of Secondary Content is determined by a runtime parameter

We can allow callers to optionally include secondary content in the list of messages.
Open Question: Do we allow secondary content to use `TextContent` types?

```csharp
// By default the response only has the final response messages, so text
// contains the final response, and it's a good starting experience.
var response = agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// we can also optionally include updates via an option.
var response = agent.RunAsync("Do Something", options: new() { IncludeUpdates = true });
// Callers can now access all updates.
foreach (var update in response.Messages)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Easy getting started experience, reuse response types from IChatClient.
- **CONS**: May need either a derived ChatResponse or implementations to avoid using `TextContent` for anything but the final response similar to 1.1 or 1.4.

#### Option 1.3 Use ChatClient response types

```csharp
// Since text contains the aggregate output of everything that happened, the following
// would not get the caller a nice final response text.
var response = agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Instead they would need to do the following:
Console.WriteLine(response.Messages.Last().Text);

// Callers can get access to all updates.
foreach (var message in response.Messages)
{
    Console.WriteLine(message.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Reuse response types from IChatClient.
- **CONS**: More complex getting started experience.

#### Option 1.4 Return derived ChatClient response types

```csharp
public class AgentChatResponse : ChatResponse
{
    // ChatResponse.Text would need to be made virtual.
    public override string Text => _messages.LastOrDefault()?.Text ?? string.Empty;
}

// Since text contains the final response, it's a good getting started experience.
var response = agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers can still get access to all updates too.
foreach (var update in response.Messages)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Easy getting started experience.
- **CONS**: Requires custom response types.

### Option 2 Run: Container with Primary and Secondary Properties, RunStreaming: Stream of Primary + Secondary

Run and RunStreaming return new types.
For Run the new response type has separate properties for the final response and updates leading up to it.
The final response is available in the `AgentRunResponse.Messages` property while updates are in a new `AgentRunResponse.Updates` property.
`AgentRunResponse.Text` returns the final response text.

```csharp
// Since text contains the final response, it's a good getting started experience.
var response = agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers can still get access to all updates too.
foreach (var update in response.Updates)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

#### Option 2.1 Response types extend MEAI types

```csharp
class Agent
{
    public abstract Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    public abstract IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);
}

class AgentRunResponse : ChatResponse
{
    public List<AgentRunResponseUpdate> Updates { get; set; } // Stream of updates before the final response (Secondary)
}

public class AgentRunResponseUpdate : ChatResponseUpdate
{
}
```

- **PROS**: Final response messages and Updates are categorised and therefore easy to distinguish and this design popular SDKs like AutoGen and OpenAI SDK.
- **CONS**: Requires custom response types and design differs significantly between streaming and non-streaming.

#### Option 2.2 New Response types

We could create new response types for Agents.
For non-streaming it would include a new property for updates.
The new types could also exclude properties that make less sense for agents, like ConversationId, which is abstracted away by AgentThread, or ModelId, where an agent might use multiple models.

```csharp
class Agent
{
    public abstract Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    public abstract IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);
}

class AgentRunResponse // Compare with ChatResponse
{
    public string Text { get; } // Aggregation of Messages text.

    public IList<ChatMessage> Messages { get; set; } // Final response from the agent (Primary)

    // New
    public List<AgentRunResponseUpdate> Updates { get; set; } // List of updates generated before the final response (Secondary)

    public string? ResponseId { get; set; }
    public AgentRunResponseReason? FinishReason { get; set; }

    // Metadata
    public string? AuthorName { get; set; }
    public DateTimeOffset? CreatedAt { get; set; }
    public object? RawRepresentation { get; set; }
    public UsageDetails? Usage { get; set; }
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

// Not Included in AgentRunResponse compared to ChatResponse
public string? ConversationId { get; set; }
public string? ModelId { get; set; }

public class AgentRunResponseUpdate // Compare with ChatResponseUpdate
{
    public string Text { get; } // Aggregation of Contents text.

    public IList<AIContent> Contents { get; set; }

    public string? ResponseId { get; set; }
    public string? MessageId { get; set; }
    public AgentRunResponseReason? FinishReason { get; set; }

    // Metadata
    public ChatRole? Role { get; set; }
    public string? AuthorName { get; set; }
    public DateTimeOffset? CreatedAt { get; set; }
    public UsageDetails? Usage { get; set; }
    public object? RawRepresentation { get; set; }
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

// Not Included in AgentRunResponseUpdate compared to ChatResponseUpdate
public string? ConversationId { get; set; }
public string? ModelId { get; set; }

public class AgentRunResponseReason // Compare with ChatFinishReason
{
    public static AgentRunResponseReason Stop { get; } = new AgentRunResponseReason("stop");
    public static AgentRunResponseReason Length { get; } = new AgentRunResponseReason("length");
    public static AgentRunResponseReason ContentFilter { get; } = new AgentRunResponseReason("content_filter");
}

// Not included in AgentRunResponseReason compared to ChatFinishReason
public static ChatFinishReason ToolCalls { get; } = new ChatFinishReason("tool_calls");
```

- **PROS**: Final response messages and Updates are categorised and therefore easy to distinguish and this design popular SDKs like AutoGen and OpenAI SDK. Properties that don't make that sense on the agent API surface, like ConversationId, can be removed.
- **CONS**: Requires custom response types and design differs significantly between streaming and non-streaming.

### Option 3 Run: Primary-only, RunStreaming: Stream of Primary + Secondary

Run returns a `Task<ChatResponse>` and RunStreaming returns a `IAsyncEnumerable<ChatResponseUpdate>`.
For Run, the returned `ChatResponse.Messages` contains only the final response message.
`ChatResponse.Text` will contain the aggregate text of `ChatResponse.Messages` and therefore the final response message text.

```csharp
// Since text contains the final response, it's a good getting started experience.
var response = agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers cannot get access to all updates, since only the final message is in messages.
var finalMessage = response.Messages.FirstOrDefault();
```

- **PROS**: Simple getting started experience, Reusing IChatClient response types.
- **CONS**: Intermediate updates are only availble in streaming mode.

### Option 4: Remove Run API and retain RunStreaming API only, which returns a Stream of Primary + Secondary

With this option, we remove the `RunAsync` method and only retain the `RunStreamingAsync` method, but
we add helpers to process the streaming responses and extract information from it.

```csharp
// User can get the final response through an extenion method on the async enumerable stream.
var responses = agent.RunStreamingAsync("Do Something");
// E.g. an extendion method that builds the final result text.
Console.WriteLine(await responses.AggregateFinalResult());
// Or an extention method that builds a result message from the updates.
Console.WriteLine(await responses.BuildMessage().Text);

// Callers can also iterate through all updates if needed
await foreach (var update in responses)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Single API for streaming/non-streaming
- **CONS**: More complex to for inexperienced users.

## Long Running Processes Options

Some agent protocols, like A2A, support long running agentic processes. When invoking the agent
in the non-streaming case, the agent may respond with an id of a process that was launched.

The caller is then expected to poll the service to get status updates using the id.
The caller may also subscribe to updates from the process using the id.

We therefore need to be able to support providing this type of response to agent callers.

- **Option 1** Add a new `AIContent` type and `ChatFinishReason` for long running processes.
- **Option 2** Add another property on a custom response type.

### Option 1: Add another AIContent type and ChatFinishReason for long running processes

```csharp
public class AgentRunContent : AIContent
{
    public string AgentRunId { get; set; }
}

// Add a new long running chat finish reason.
public class ChatFinishReason
{
    public static ChatFinishReason LongRunning { get; } = new ChatFinishReason("long_running");
}
```

- **PROS**: Fits well into existing `ChatResponse` design.
- **CONS**: More complex for users to extract the required long running result (can be mitigated with extenion methods)

### Option 2: Add another property on responses for AgentRun

```csharp
class AgentRunResponse : ChatResponse
{
    public List<AgentRunResponseUpdate> Updates { get; set; } // Stream of updates before the final response (Secondary)

    public AgentRun RunReference { get; set; } // Reference to long running process
}


public class AgentRunResponseUpdate : ChatResponseUpdate
{
    public AgentRun RunReference { get; set; } // Reference to long running process
}

// Add a new long running chat finish reason.
public class ChatFinishReason
{
    public static ChatFinishReason LongRunning { get; } = new ChatFinishReason("long_running");
}

// Can be added in future: Class representing long running processing by the agent
// that can be used to check for updates and status of the processing.
public class AgentRun
{
    public string AgentRunId { get; set; }
}
```

- **PROS**: Easy access to long running result values
- **CONS**: Requires custom response types.

## Structured user input options (Work in progress)

Some agent services may ask end users a question while also providing a list of options that the user can pick from or a template for the input required.
We need to decide whether to maintain an abstraction for these, so that similar types of structured input from different agents can be used by callers without
needing to break out of the abstraction.

## Tool result options (Work in progress)

We need to consider abstractions for `AIContent` derived types for tool call results for common tool types beyond Function calls, e.g. CodeInterpreter, WebSearch, etc.

## Decision Outcome

Chosen option: "{title of option 1}", because
{justification. e.g., only option, which meets k.o. criterion decision driver | which resolves force {force} | … | comes out best (see below)}.
