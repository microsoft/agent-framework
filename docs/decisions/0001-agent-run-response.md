---
# These are optional elements. Feel free to remove any of them.
status: accepted
contact: westey-m
date: 2025-07-10 {YYYY-MM-DD when the decision was last updated}
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted: 
informed: 
---

# Agent Run Responses Design

## Context and Problem Statement

Agents may produce lots of output during a run including

1. **[Primary]** General response messages to the caller (this may be in the form of text, including structured output, images, sound, etc.)
2. **[Primary]** Structured confirmation requests to the caller
3. **[Secondary]** Tool invocation activities executed (both local and remote).  For information only.
4. Reasoning/Thinking output.
    1. **[Primary]** In some cases an LLM may return reasoning output intermixed with as part of the answer to the caller, since the caller's prompt asked for this detail in some way. This should be considered a specialization of 1.
    1. **[Secondary]** Reasonining models optionally produce reasoning output separate from the answer to the caller's question, and this should be considered secondary content.
5. **[Secondary]** Handoffs / transitions from agent to agent where an agent contains sub agents.
6. **[Secondary]** An indication that the agent is responding (i.e. typing) as if it's a real human.
7. Complete messages in addition to updates, when streaming
8. Id for long running process that is launched
9. and more

We need to ensure that with this diverse list of output, we are able to

- Support all with abstractions where needed
- Provide a simple getting started experience that doesn't overwhelm developers

### Agent response data types

When comparing various agent SDKs and protocols, agent output is often divided into two categories:

1. **Result**: A response from the agent that communicates the result of the agent's work to the caller in natural language (or images/sound/etc.). Let's call this **Primary** output.
    1. Includes cases where the agent finished because it requires more input from the user.
2. **Progress**: Updates while the agent is running, which are informational only, typically showing what the agent is doing, and does not allow any actions to be taken by the caller that modify the behavior of the agent before completing the run. Let's call this **Secondary** output.

A potential third category is:

3. **Long Running**: A response that does not contain a Primary response or Secondary updates, but rather a reference to a long running task.

### Different use cases for Primary and Secondary output

To solve complex problems, many agents must be used together. These agents typically have their own capabilities and responsibilities and communicate via input messages and final responses/handoff calls, while the internal workings of each agent is not of interest to the other agents participating in solving the problem.

When an agent is in conversation with one or more humans, the information that may be displayed to the user(s) can vary. E.g. When an agent is part of a conversation with multiple humans it may be asked to perform tasks by the humans, and they may not want a stream of distracting updates posted to the conversation, but rather just a final response.  On the other hand, if an agent is being used by a single human to perform a task, the human may be waiting for the agent to complete the task.  Therefore, they may be interested in getting updates of what the agent is doing.

Where agents are nested, consumers would also likely want to constrain the amount of data from an agent that bubbles up into higher level conversations to avoid exceeding the context window, therefore limiting it to the Primary response only.

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
| LangGraph | **Approach 2** A mixed list of all [messages](https://langchain-ai.github.io/langgraph/agents/run_agents/#output-format) | **Approach 2** A mixed list of all [messages](https://langchain-ai.github.io/langgraph/agents/run_agents/#output-format) |
| Agno | **Combination of various approaches** Returns a [RunResponse](https://docs.agno.com/reference/agents/run-response) object with text content, messages (essentially chat history including inputs and instructions), reasoning and thinking text properties. Secondary events could potentially be extracted from messages. | **Approach 2** Returns [RunResponseEvent](https://docs.agno.com/reference/agents/run-response#runresponseevent-types-and-attributes) objects including tool call, memory update, etc, information, where the [RunResponseCompletedEvent](https://docs.agno.com/reference/agents/run-response#runresponsecompletedevent) has similar properties to RunResponse|
| A2A | **Approach 3** Returns a [Task or Message](https://a2aproject.github.io/A2A/latest/specification/#71-messagesend) where the message is the final result (Primary) and task is a reference to a long running process. | **Approach 2** Returns a [stream](https://a2aproject.github.io/A2A/latest/specification/#72-messagestream) that contains task updates (Secondary) and a final message (Primary) |
| Protocol Activity | **Approach 2** Single stream of responses including secondary events and final response messages (Primary). | No separate behavior for streaming. |

## Decision Drivers

- Solutions provides an easy to use experience for users who are getting started and just want the answer to a question.
- Solution must be extensible to future requirements, e.g. long running agent processes.
- Experience is in line or better than the best in class experience from other SDKs

## Response Type Options

- **Option 1** Run: Messages List contains mix of Primary and Secondary content, RunStreaming: Stream of Primary + Secondary
  - **Option 1.1** Secondary content do not use `TextContent`
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
For Run, the returned `ChatResponse.Messages` contains an ordered list of messages that contain both the Primary and Secondary content.

`ChatResponse.Text` automatically aggregates all text from any `TextContent` items in all `ChatMessage` items in the response.
If we can ensure that no updates ever contain `TextContent`, this will mean that `ChatResponse.Text` will always contain
the Primary response text. See option 1.1.
If we cannot ensure this, either the solution or usage becomes more complex, see 1.3 and 1.4.

#### Option 1.1 `TextContent`, `DataContent` and `UriContent` means Primary content

`ChatResponse.Text` aggregates all `TextContent` values, and no secondary updates use `TextContent`
so `ChatResponse.Text` will always contain the Primary content.

```csharp
// Since the Text property contains the primary content, it's a simple getting started experience.
var response = await agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers can still get access to all updates too.
foreach (var update in response.Messages)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}

// For streaming, it's possible to output the primary content by also using the Text property on each update.
await foreach (var update in agent.RunStreamingAsync("Do Something"))
{
    Console.Writeline(update.Text)
}
```

- **PROS**: Easy and familiar user experience, reuse response types from IChatClient. Similar experience for both streaming and non streaming.
- **CONS**: The agent response types cannot evolve separately from MEAI if needed.

#### Option 1.1a `TextContent`, `DataContent` and `UriContent` means Primary content, with custom Agent response types

Same as 1.1 but with custom Agent Framework response types.
The response types should preferably resemble ChatResponse types closely, to ensure user's have a fimilar experience when moving between the two.
Therefore something like `AgentResponse.Text` which also aggregates all `TextContent` values similar to 1.1 makes sense.

- **PROS**: Easy getting started experience, and response types can be customized for the Agent Framework where needed.
- **CONS**: More work to define custom response types.

#### Option 1.2 Presence of Secondary Content is determined by a runtime parameter

We can allow callers to choose whether to include secondary content in the list of reponse messages.
Open Question: Do we allow secondary content to use `TextContent` types?

```csharp
// By default the response only has the primary content, so text
// contains the primary content, and it's a good starting experience.
var response = await agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// we can also optionally include updates via an option.
var response = await agent.RunAsync("Do Something", options: new() { IncludeUpdates = true });
// Callers can now access all updates.
foreach (var update in response.Messages)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Easy getting started experience, reuse response types from IChatClient.
- **CONS**: Since the basic experience is the same as 1.1, and when you look at individual messages, you most likely want all anyway, it seems arbitrarily limiting compared to 1.1.

### Option 2 Run: Container with Primary and Secondary Properties, RunStreaming: Stream of Primary + Secondary

Run returns a new response type that has separate properties for the Primary Content and the Secondary Updates leading up to it.
The Primary content is available in the `AgentRunResponse.Messages` property while Secondary updates are in a new `AgentRunResponse.Updates` property.
`AgentRunResponse.Text` returns the Primary content text.

Since streaming would still need to return an `IAsyncEnumerable` of updates, the design would differ from non-streaming.
With non-streaming Primary and Secondary content is split into separate lists, while with streaming it's combined in one stream.

```csharp
// Since text contains the primary content, it's a good getting started experience.
var response = await agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers can still get access to all updates too.
foreach (var update in response.Updates)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Primary content and Secondary Updates are categorised for non-streaming and therefore easy to distinguish and this design matches popular SDKs like AutoGen and OpenAI SDK.
- **CONS**: Requires custom response types and design would differ between streaming and non-streaming.

### Option 3 Run: Primary-only, RunStreaming: Stream of Primary + Secondary

Run returns a `Task<ChatResponse>` and RunStreaming returns a `IAsyncEnumerable<ChatResponseUpdate>`.
For Run, the returned `ChatResponse.Messages` contains only the Primary content messages.
`ChatResponse.Text` will contain the aggregate text of `ChatResponse.Messages` and therefore the primary content messages text.

```csharp
// Since text contains the primary content response, it's a good getting started experience.
var response = await agent.RunAsync("Do Something");
Console.WriteLine(response.Text);

// Callers cannot get access to all updates, since only the primary content is in messages.
var primaryContentOnly = response.Messages.FirstOrDefault();
```

- **PROS**: Simple getting started experience, Reusing IChatClient response types.
- **CONS**: Intermediate updates are only availble in streaming mode.

### Option 4: Remove Run API and retain RunStreaming API only, which returns a Stream of Primary + Secondary

With this option, we remove the `RunAsync` method and only retain the `RunStreamingAsync` method, but
we add helpers to process the streaming responses and extract information from it.

```csharp
// User can get the primary content through an extension method on the async enumerable stream.
var responses = agent.RunStreamingAsync("Do Something");
// E.g. an extension method that builds the primary content text.
Console.WriteLine(await responses.AggregateFinalResult());
// Or an extention method that builds complete messages from the updates.
Console.WriteLine(await responses.BuildMessage().Text);

// Callers can also iterate through all updates if needed
await foreach (var update in responses)
{
    Console.WriteLine(update.Contents.FirstOrDefault()?.GetType().Name);
}
```

- **PROS**: Single API for streaming/non-streaming
- **CONS**: More complex to for inexperienced users.

## Custom Response Type Design Options

### Option 1 Response types extend MEAI types

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
}

public class AgentRunResponseUpdate : ChatResponseUpdate
{
}
```

- **PROS**: Fimilar response types for anyone already using MEAI.
- **CONS**: Agent response types cannot evolve separately.

### Option 2 New Response types

We could create new response types for Agents.
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
    public string Text { get; } // Aggregation of TextContent from messages.

    public IList<ChatMessage> Messages { get; set; }

    public string? ResponseId { get; set; }

    // Metadata
    public string? AuthorName { get; set; }
    public DateTimeOffset? CreatedAt { get; set; }
    public object? RawRepresentation { get; set; }
    public UsageDetails? Usage { get; set; }
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

// Not Included in AgentRunResponse compared to ChatResponse
public ChatFinishReason? FinishReason { get; set; }
public string? ConversationId { get; set; }
public string? ModelId { get; set; }

public class AgentRunResponseUpdate // Compare with ChatResponseUpdate
{
    public string Text { get; } // Aggregation of TextContent from Contents.

    public IList<AIContent> Contents { get; set; }

    public string? ResponseId { get; set; }
    public string? MessageId { get; set; }

    // Metadata
    public ChatRole? Role { get; set; }
    public string? AuthorName { get; set; }
    public DateTimeOffset? CreatedAt { get; set; }
    public UsageDetails? Usage { get; set; }
    public object? RawRepresentation { get; set; }
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}

// Not Included in AgentRunResponseUpdate compared to ChatResponseUpdate
public ChatFinishReason? FinishReason { get; set; }
public string? ConversationId { get; set; }
public string? ModelId { get; set; }
```

- **PROS**: Agent response types can evolve separately. Types can still resemble MEAI response types to ensure a fimilar experience for developers.
- **CONS**: No automatic inheritence of new properties from MEAI. (this might also be a pro)

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
class AgentRunResponse
{
    ...
    public AgentRun RunReference { get; set; } // Reference to long running process
    ...
}


public class AgentRunResponseUpdate
{
    ...
    public AgentRun RunReference { get; set; } // Reference to long running process
    ...
}

// Add a new long running chat finish reason.
public class ChatFinishReason
{
    ...
    public static ChatFinishReason LongRunning { get; } = new ChatFinishReason("long_running");
    ...
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

## StructuredOutputs

Structured outputs is a valueable aspect of any Agent system, since it forces an Agent to produce output in a required format, and may include required fields. This allows turning unstructured data into structured data easily using a general purpose language model.

Not all agent types necessarily support this or necessarily support this in the same way.
Requesting a specific output schema at invocation time is widely supported by inference services though, and therefore inference based agents would support this well.
Custom agents on the other hand may not necessarily want to support this, and forcing all custom Agent implementations to have a final structured output step to produce this complicates implementations.
Custom agents may also have a built in output schema, that they always produce.

Options:

1. Support configuring the preferred structured output schema at agent construction time for those agents that support structured outputs.
2. Support configuring the preferred structured output schema at invocation time, and ignore/throw if not supported (similar to IChatClient)
3. Support both options with the invocation time schema overriding the construction time (or built in) schema if both are supported.

Note that where an agent doesn't support structured output, it may also be possible to use a decorator to produce structured output from the agent's unstructured response, thereby turning an agent that doesn't support this into one that does.

See [Structured Outputs Support](#structured-outputs-support) for a comparison on what other agent frameworks and protocols support.

To support a good user experience for structured outputs, I'm proposing that we follow the pattern used by MEAI.
We would add a generic version of `AgentRunResponse<T>`, that allows us to get the agent result already deserialized into our preferred type.
This would be coupled with generic overload extension methods for Run that automatically builds a schema from the supplied type and updates
the run options.

If we support requesting a schema at invocation time the following would be the preferred approach:

```csharp
class Movie
{
    public string Title { get; set; }
    public string DirectorFullName { get; set; }
    public int ReleaseYear { get; set; }
}

AgentRunResponse<Movie[]> response = agent.RunAsync<Movie[]>("What are the top 3 children's movies of the 80s.");
Movie[] movies = response.Result
```

If we only support requesting a schema at agent creation time or where an agent has a built in schema, the following would be the preferred approach:

```csharp
AgentRunResponse response = agent.RunAsync("What are the top 3 children's movies of the 80s.");
Movie[] movies = response.TryParseStructuredOutput<Movie[]>();
```

## Decision Outcome

### Response Type Options Decision

Option 1.1 with the caveate that we cannot control the output of all agents. However, as far as possible we should have appropriate AIContext derived types for
progress updates so that TextContent is not used for these.

### Custom Response Type Design Options Decision

Option 2 chosen so that we can vary Agent responses independently of Chat Client.

### StructuredOutputs Decision

We will not support structured output per run request, but individual agents are free to allow this on the concrete implementation or at construction time.
We will however add support for easily extracting a structured output type from the `AgentRunResponse`.

## Addendum 1: AIContext Derived Types for different response types / Gap Analysis (Work in progress)

We need to decide what AIContent types, each agent response type will be mapped to.

| Number | DataType | AIContent Type |
|-|-|-|
| 1. | General response messages to the user | TextContent + DataContent + UriContent |
| 2. | Structured confirmation requests to the user | ? |
| 3. | Function invocation activities executed (both local and remote). For information only. | FunctionCallContent + FunctionResultContent |
| 4. | Tool invocation activities executed (both local and remote). For information only. | FunctionCallContent/FunctionResultContent/Custom ? |
| 5. | Reasoning/Thinking output. For information only. | TextReasoningContent |
| 6. | Handoffs / transitions from agent to agent. | ? |
| 7. | An indication that the agent is responding (i.e. typing) as if it's a real human. | ? |
| 8. | Complete messages in addition to updates, when streaming | TextContent |
| 9. | Id for long running process that is launched | ? |
| 10. | Memory storage / lookups (are these just traces?) | ? |
| 11. | RAG indexing / lookups (are these just traces?) | ? |
| 12. | General status updates for human consumption / Tracing | ? |
| 13. | Unknown Type | AIContent |

## Addendum 2: Other SDK feature comparison

### Structured Outputs Support

1. Configure Schema on Agent at Agent construction
2. Pass schema at Agent invocation

| SDK | Structured Outputs support |
|-|-|
| AutoGen | **Approach 1** Supports [configuring an agent](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html#structured-output) at agent creation. |
| Google ADK | **Approach 1** Both [input and output shemas can be specified for LLM Agents](https://google.github.io/adk-docs/agents/llm-agents/#structuring-data-input_schema-output_schema-output_key) at construction time. This option is specific to this agent type and other agent types do not necessarily support |
| AWS (Strands) | **Approach 2** Supports a special invocation method called [structured_output](https://strandsagents.com/latest/api-reference/agent/#strands.agent.agent.Agent.structured_output) |
| LangGraph | **Approach 1** Supports [configuring an agent](https://langchain-ai.github.io/langgraph/agents/agents/?h=structured#6-configure-structured-output) at agent construction time, and a [structured response](https://langchain-ai.github.io/langgraph/agents/run_agents/#output-format) can be retrieved as a special property on the agent response |
| Agno | **Approach 1** Supports [configuring an agent](https://docs.agno.com/examples/getting-started/structured-output) at agent construction time |
| A2A | **Informal Approach 2** Doesn't formally support schema negotiation, but [hints can be provided via metadata](https://a2a-protocol.org/latest/specification/#97-structured-data-exchange-requesting-and-providing-json) at invocation time |
| Protocol Activity | Supports returning [Complex types](https://github.com/microsoft/Agents/blob/main/specs/activity/protocol-activity.md#complex-types) but no support for requesting a type |

### Response Reason Support

| SDK | Response Reason support |
|-|-|
| AutoGen | Supports a [stop reason](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.base.html#autogen_agentchat.base.TaskResult.stop_reason) which is a freeform text string |
| Google ADK | [No equivalent present](https://github.com/google/adk-python/blob/main/src/google/adk/events/event.py) |
| AWS (Strands) | Exposes a [stop_reason](https://strandsagents.com/latest/api-reference/types/#strands.types.event_loop.StopReason) property on the [AgentResult](https://strandsagents.com/latest/api-reference/agent/#strands.agent.agent_result.AgentResult) class with options that are tied closely to LLM operations. |
| LangGraph | No equivalent present, output contains only [messages](https://langchain-ai.github.io/langgraph/agents/run_agents/#output-format) |
| Agno | [No equivalent present](https://docs.agno.com/reference/agents/run-response) |
| A2A | No equivalent present, response only contains a [message](https://a2a-protocol.org/latest/specification/#64-message-object) or [task](https://a2a-protocol.org/latest/specification/#61-task-object). |
| Protocol Activity | [No equivalent present.](https://github.com/microsoft/Agents/blob/main/specs/activity/protocol-activity.md) |
