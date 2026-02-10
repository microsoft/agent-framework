---
status: proposed
contact: sergeymenshykh
date: 2026-01-22
deciders: rbarreto, westey-m, stephentoub
informed: {}
---

# Structured Output

Structured output is a valuable aspect of any agent system, since it forces an agent to produce output in a required format that may include required fields.
This allows easily turning unstructured data into structured data using a general-purpose language model.

## Context and Problem Statement

Structured output is currently supported only by `ChatClientAgent` and can be configured in two ways:

**Approach 1: ResponseFormat + Deserialize**

Specify the SO type schema via the `ChatClientAgent{Run}Options.ChatOptions.ResponseFormat` property at agent creation or invocation time, then use `JsonSerializer.Deserialize<T>` to extract the structured data from the response text.

	```csharp
	// SO type can be provided at agent creation time
	ChatClientAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions()
	{
		Name = "...",
		ChatOptions = new() { ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>() }
	});

	AgentResponse response = await agent.RunAsync("...");

	PersonInfo personInfo = response.Deserialize<PersonInfo>(JsonSerializerOptions.Web);

	Console.WriteLine($"Name: {personInfo.Name}");
	Console.WriteLine($"Age: {personInfo.Age}");
	Console.WriteLine($"Occupation: {personInfo.Occupation}");

	// Alternatively, SO type can be provided at agent invocation time
	response = await agent.RunAsync("...", new ChatClientAgentRunOptions()
	{
		ChatOptions = new() { ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>() }
	});

	personInfo = response.Deserialize<PersonInfo>(JsonSerializerOptions.Web);

	Console.WriteLine($"Name: {personInfo.Name}");
	Console.WriteLine($"Age: {personInfo.Age}");
	Console.WriteLine($"Occupation: {personInfo.Occupation}");
	```

**Approach 2: Generic RunAsync<T>**

Supply the SO type as a generic parameter to `RunAsync<T>` and access the parsed result directly via the `Result` property.

	```csharp
	ChatClientAgent agent = ...;
	
	AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("...");

	Console.WriteLine($"Name: {response.Result.Name}");
	Console.WriteLine($"Age: {response.Result.Age}");
	Console.WriteLine($"Occupation: {response.Result.Occupation}");
	```
	Note: `RunAsync<T>` is an instance method of `ChatClientAgent` and not part of the `AIAgent` base class since not all agents support structured output.

Approach 1 is perceived as cumbersome by the community, as it requires additional effort when using primitive or collection types - the SO schema may need to be wrapped in an artificial JSON object. Otherwise, the caller will encounter an error like _Invalid schema for response_format 'Movie': schema must be a JSON Schema of 'type: "object"', got 'type: "array"'_. 
This occurs because OpenAI and compatible APIs require a JSON object as the root schema.

Approach 1 is also necessary in scenarios where (a) agents can only be configured with SO at creation time (such as with `AIProjectClient`), (b) the SO type is not known at compile time, or (c) the JSON schema is represented as text (for declarative agents) or as a `JsonElement`.

Approach 2 is more convenient and works seamlessly with primitives and collections. However, it requires the SO type to be known at compile time, making it less flexible.

Additionally, since the `RunAsync<T>` methods are instance methods of `ChatClientAgent` and are not part of the `AIAgent` base class, applying decorators like `OpenTelemetryAgent` on top of `ChatClientAgent` prevents users from accessing `RunAsync<T>`, meaning structured output is not available with decorated agents.

Given the different scenarios above in which structured output can be used, there is no one-size-fits-all solution. Each approach has its own advantages and limitations,
and the two can complement each other to provide a comprehensive structured output experience across various use cases.

## Approaches Overview

1. SO usage via `ResponseFormat` property
2. SO usage via `RunAsync<T>` generic method

## 1. SO usage via `ResponseFormat` property

This approach should be used in the following scenarios:
 - 1.1 SO result as text is sufficient as is, and deserialization is not required
 - 1.2 SO for inter-agent collaboration
 - 1.3 SO can only be configured at agent creation time (such as with `AIProjectClient`)
 - 1.4 SO type is not known at compile time and represented by System.Type
 - 1.5 SO is represented by JSON schema and there's no corresponding .NET type either at compile time or at runtime
 - 1.6 SO in streaming scenarios, where the SO response is produced in parts

**Note: Primitives and arrays are not supported by this approach.**

When a caller provides a schema via `ResponseFormat`, they are explicitly telling the framework what schema to use. The framework passes that schema through as-is and
is not responsible for transforming it. Because the framework does not own the schema, it cannot wrap primitives or arrays into a JSON object to satisfy API requirements,
nor can it unwrap the response afterward - the caller controls the schema and is responsible for ensuring it is compatible with the underlying API.

This is in contrast to the `RunAsync<T>` approach (section 2), where the caller provides a type `T` and says "make it work." In that case, the caller does not
dictate the schema - the framework infers the schema from `T`, owns the end-to-end pipeline (schema generation, API invocation, and deserialization), and can
therefore wrap and unwrap primitives and arrays transparently.

Additionally, in streaming scenarios (1.6), the framework cannot reliably unwrap a response it did not wrap, since it has no way of knowing whether the caller wrapped the schema.Wrapping and unwrapping can only be done safely when the framework owns the entire lifecycle - from schema creation through deserialization — which is only the case with `RunAsync<T>`.

If a caller needs to work with primitives or arrays via the `ResponseFormat` approach, they can easily create a wrapper type around them:

```csharp
public class MovieListWrapper
{
    public List<string> Movies { get; set; }
}
```

### 1.1 SO result as text is sufficient as is, and deserialization is not required

In this scenario, the caller only needs the raw JSON text returned by the model and does not need to deserialize it into a .NET type.
The SO schema is specified via `ResponseFormat` at agent creation or invocation time, and the response text is consumed directly from the `AgentResponse`.

```csharp
AIAgent agent = chatClient.AsAIAgent();

AgentRunOptions runOptions = new()
{
        ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>()
};

AgentResponse response = await agent.RunAsync("...", options: runOptions);

Console.WriteLine(response.Text);
```

### 1.2 SO for inter-agent collaboration

This scenario assumes a multi-agent setup where agents collaborate by passing messages to each other.
One agent produces structured output as text that is then passed directly as input to the next agent, without intermediate deserialization.

```csharp
// First agent extracts structured data from unstructured input
AIAgent extractionAgent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    Name = "ExtractionAgent",
    ChatOptions = new() 
    { 
        Instructions = "Extract person information from the provided text.",
        ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>() 
    }
});

AgentResponse extractionResponse = await extractionAgent.RunAsync("John Smith is a 35-year-old software engineer.");

// Pass the message with structured output text directly to the next agent
ChatMessage soMessage = extractionResponse.Messages.Last();

AIAgent summaryAgent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    Name = "SummaryAgent",
    ChatOptions = new() { Instructions = "Given the following structured person data, write a short professional bio." }
});

AgentResponse summaryResponse = await summaryAgent.RunAsync(soMessage);

Console.WriteLine(summaryResponse);
```

### 1.3 SO configured at agent creation time

In this scenario, the SO schema can only be configured at agent creation time (such as with `AIProjectClient`) and cannot be changed on a per-run basis.
The caller specifies the `ResponseFormat` when creating the agent, and all subsequent invocations use the same schema.

```csharp
AIProjectClient client = ...;

AIAgent agent = await client.CreateAIAgentAsync(model: "<model>", new ChatClientAgentOptions()
{
    Name = "...",
    ChatOptions = new() { ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>() }
});

AgentResponse response = await agent.RunAsync("Please provide information about John Smith.");

PersonInfo personInfo = JsonSerializer.Deserialize<PersonInfo>(response.Text, JsonSerializerOptions.Web)!;

Console.WriteLine($"Name: {personInfo.Name}");
Console.WriteLine($"Age: {personInfo.Age}");
Console.WriteLine($"Occupation: {personInfo.Occupation}");
```

### 1.4 SO type not known at compile time and represented by System.Type

In this scenario, the SO type is not known at compile time and is provided as a `System.Type` at runtime. This is useful for dynamic scenarios where the schema is determined programmatically, 
such as when building tooling or frameworks that work with user-defined types.

```csharp
Type soType = GetStructuredOutputTypeFromConfiguration(); // e.g., typeof(PersonInfo)

ChatResponseFormat responseFormat = ChatResponseFormat.ForJsonSchema(soType);

AgentResponse response = await agent.RunAsync("...", new ChatClientAgentRunOptions()
{
    ChatOptions = new() { ResponseFormat = responseFormat }
});

PersonInfo personInfo = (PersonInfo)JsonSerializer.Deserialize(response.Text, soType, JsonSerializerOptions.Web)!;
```

### 1.5 SO represented by JSON schema with no corresponding .NET type

In this scenario, the SO schema is represented as raw JSON schema text or a `JsonElement`, and there is no corresponding .NET type available at compile time or runtime.
This is typical for declarative agents or scenarios where schemas are loaded from external configuration.

```csharp
// JSON schema provided as a string, e.g., loaded from a configuration file
string jsonSchema = """
{
    "type": "object",
    "properties": {
        "name": { "type": "string" },
        "age": { "type": "integer" },
        "occupation": { "type": "string" }
    },
    "required": ["name", "age", "occupation"]
}
""";

ChatResponseFormat responseFormat = ChatResponseFormat.ForJsonSchema(
    jsonSchemaName: "PersonInfo",
    jsonSchema: BinaryData.FromString(jsonSchema));

AgentResponse response = await agent.RunAsync("...", new ChatClientAgentRunOptions()
{
    ChatOptions = new() { ResponseFormat = responseFormat }
});

// Consume the SO result as text since there's no .NET type to deserialize into
Console.WriteLine(response.Text);
```

### 1.6 SO in streaming scenarios

In this scenario, the SO response is produced incrementally in parts via streaming. The caller specifies the `ResponseFormat` and consumes the response chunks as they arrive.
Deserialization is performed after all chunks have been received.

```csharp
AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    Name = "HelpfulAssistant",
    ChatOptions = new()
    {
        Instructions = "You are a helpful assistant.",
        ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>()
    }
});

IAsyncEnumerable<AgentResponseUpdate> updates = agent.RunStreamingAsync("Please provide information about John Smith, who is a 35-year-old software engineer.");

AgentResponse response = await updates.ToAgentResponseAsync();

// Deserialize the complete SO result after streaming is finished
PersonInfo personInfo = JsonSerializer.Deserialize<PersonInfo>(response.Text)!;
```

## 2. SO usage via `RunAsync<T>` generic method

This approach provides a convenient way to work with structured output on a per-run basis when the target type is known at compile time and a typed instance of the result
is required.

### Decision Drivers

1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

### Considered Options

1. `RunAsync<T>` as an instance method of `AIAgent` class delegating to virtual `RunCoreAsync<T>`
2. `RunAsync<T>` as an extension method using feature collection
3. `RunAsync<T>` as a method of the new `ITypedAIAgent` interface
4. `RunAsync<T>` as an instance method of `AIAgent` class working via the new `AgentRunOptions.ResponseFormat` property

### 1. `RunAsync<T>` as an instance method of `AIAgent` class delegating to virtual `RunCoreAsync<T>`

This option adds the `RunAsync<T>` method directly to the `AIAgent` base class.

```csharp
public abstract class AIAgent
{
	public Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
		=> this.RunCoreAsync<T>(messages, session, serializerOptions, options, cancellationToken);

    protected virtual Task<AgentResponse<T>> RunCoreAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        throw new NotSupportedException($"The agent of type '{this.GetType().FullName}' does not support typed responses.");
    }
}
```

Agents with native SO support override the `RunCoreAsync<T>` method to provide their implementation. If not overridden, the method throws a `NotSupportedException`.

Users will call the generic `RunAsync<T>` method directly on the agent:

```csharp
AIAgent agent = chatClient.AsAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");
```

Decision drivers satisfied:
1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

Pros:
- The `AIAgent.RunAsync<T>` method is easily discoverable.
- Both the SO decorator and `ChatClientAgent` have compile-time access to the type `T`, allowing them to use the native `IChatClient.GetResponseAsync<T>` API, which handles primitives and collections seamlessly.

Cons:
- Agents without native SO support will still expose `RunAsync<T>`, which may be misleading.
- `ChatClientAgent` exposing `RunAsync<T>` may be misleading when the underlying chat client does not support SO.
- All `AIAgent` decorators must override `RunCoreAsync<T>` to properly handle `RunAsync<T>` calls.

### 2. `RunAsync<T>` as an extension method using feature collection

This option uses the Agent Framework feature collection (implemented via `AgentRunOptions.AdditionalProperties`) to pass a `StructuredOutputFeature` to agents, signaling that SO is requested.

Agents with native SO support check for this feature. If present, they read the target type, build the schema, invoke the underlying API, and store the response back in the feature.
```csharp
public class StructuredOutputFeature
{
    public StructuredOutputFeature(Type outputType)
    {
        this.OutputType = outputType;
    }

    [JsonIgnore]
    public Type OutputType { get; set; }

    public JsonSerializerOptions? SerializerOptions { get; set; }

    public AgentResponse? Response { get; set; }
}
```

The `RunAsync<T>` extension method for `AIAgent` adds this feature to the collection.
```csharp
public static async Task<AgentResponse<T>> RunAsync<T>(
    this AIAgent agent,
    IEnumerable<ChatMessage> messages,
    AgentSession? session = null,
    JsonSerializerOptions? serializerOptions = null,
    AgentRunOptions? options = null,
    CancellationToken cancellationToken = default)
{
    // Create the structured output feature.
    StructuredOutputFeature structuredOutputFeature = new(typeof(T))
    {
        SerializerOptions = serializerOptions,
    };

    // Register it in the feature collection.
    ((options ??= new AgentRunOptions()).AdditionalProperties ??= []).Add(typeof(StructuredOutputFeature).FullName!, structuredOutputFeature);

    var response = await agent.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);

    if (structuredOutputFeature.Response is not null)
    {
        return new StructuredOutputResponse<T>(structuredOutputFeature.Response, response, serializerOptions);
    }

    throw new InvalidOperationException("No structured output response was generated by the agent.");
}
```

Users will call the `RunAsync<T>` extension method directly on the agent:

```csharp
AIAgent agent = chatClient.AsAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");
```

Decision drivers satisfied:
1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

Pros:
- The `RunAsync<T>` extension method is easily discoverable.
- The `AIAgent` public API surface remains unchanged.
- No changes required to `AIAgent` decorators.

Cons:
- Agents without native SO support will still expose `RunAsync<T>`, which may be misleading.
- `ChatClientAgent` exposing `RunAsync<T>` may be misleading when the underlying chat client does not support SO.

### 3. `RunAsync<T>` as a method of the new `ITypedAIAgent` interface

This option defines a new `ITypedAIAgent` interface that agents with SO support implement. Agents without SO support do not implement it, allowing users to check for SO capability via interface detection.

The interface:
```csharp
public interface ITypedAIAgent
{
    Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default);

    ...
}
```

Agents with SO support implement this interface:
```csharp
public sealed partial class ChatClientAgent : AIAgent, ITypedAIAgent
{
    public async Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        ...
    }
}
```

However, `ChatClientAgent` presents a challenge: it can work with chat clients that either support or do not support SO. Implementing the interface does not guarantee 
the underlying chat client supports SO, which undermines the core idea of using interface detection to determine SO capability.

Additionally, to allow users to access interface methods on decorated agents, all decorators must implement `ITypedAIAgent`. This makes it difficult for users to 
determine whether the underlying agent actually supports SO, further weakening the purpose of this approach.

Furthermore, users would have to probe the agent type to check if it implements the `ITypedAIAgent` interface and cast it accordingly to access the `RunAsync<T>` methods.
This adds friction to the user experience. A `RunAsync<T>` extension method for `AIAgent` could be provided to alleviate that.

Given these drawbacks, this option is more complex to implement than the others without providing clear benefits.

Decision drivers satisfied:
1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

Pros:
- Both the SO decorator and `ChatClientAgent` have compile-time access to the type `T`, allowing them to use the native `IChatClient.GetResponseAsync<T>` API, which handles primitives and collections seamlessly.

Cons:
- `ChatClientAgent` implementing `ITypedAIAgent` may be misleading when the underlying chat client does not support SO.
- All `AIAgent` decorators must implement `ITypedAIAgent` to handle `RunAsync<T>` calls.
- Decorators implementing the interface may mislead users into thinking the underlying agent natively supports SO.
- Agents must implement all members of `ITypedAIAgent`, not just a core method.
- Users must check the agent type and cast to `ITypedAIAgent` to access `RunAsync<T>`.

### 4. `RunAsync<T>` as an instance method of `AIAgent` class working via the new `AgentRunOptions.ResponseFormat` property

This option adds a `ResponseFormat` property of type `ChatResponseFormat` to `AgentRunOptions`. Agents that support SO check for the presence of 
this property in the options passed to `RunAsync` to determine whether structured output is requested. If present, they use the schema from `ResponseFormat` 
to invoke the underlying API and obtain the SO response.

```csharp
public class AgentRunOptions
{
    public ChatResponseFormat? ResponseFormat { get; set; }
}
```

Additionally, a generic `RunAsync<T>` method is added to `AIAgent` that initializes the `ResponseFormat` based on the type `T` and delegates to the non-generic `RunAsync`.

```csharp
public abstract class AIAgent
{
	public async Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        serializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        var responseFormat = ChatResponseFormat.ForJsonSchema<T>(serializerOptions);

        options = options?.Clone() ?? new AgentRunOptions();
        options.ResponseFormat = responseFormat;

        AgentResponse response = await this.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);

        return new AgentResponse<T>(response, serializerOptions);
    }
}
```

Users call the generic `RunAsync<T>` method directly on the agent:

```csharp
AIAgent agent = chatClient.AsAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");
```

Decision drivers satisfied:
1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

Pros:
- The `AIAgent.RunAsync<T>` method is easily discoverable.
- No changes required to `AIAgent` decorators

Cons:
- Agents without native SO support will still expose `RunAsync<T>`, which may be misleading.
- `ChatClientAgent` exposing `RunAsync<T>` may be misleading when the underlying chat client does not support SO.

### Decision Table

|  | Option 1: Instance method + RunCoreAsync<T> | Option 2: Extension method + feature collection | Option 3: ITypedAIAgent Interface | Option 4: Instance method + AgentRunOptions.ResponseFormat |
|---|---|---|---|---|
| Discoverability | ✅ `RunAsync<T>` easily discoverable | ✅ `RunAsync<T>` easily discoverable | ❌ Requires type check and cast | ✅ `RunAsync<T>` easily discoverable |
| Decorator changes | ❌ All decorators must override `RunCoreAsync<T>` | ✅ No changes required | ❌ All decorators must implement `ITypedAIAgent` | ✅ No changes required to decorators |
| Primitives/collections handling | ✅ Native support via `IChatClient.GetResponseAsync<T>` | ❌ Must wrap/unwrap internally | ✅ Native support via `IChatClient.GetResponseAsync<T>` | ❌ Must wrap/unwrap internally |
| Misleading API exposure | ❌ Agents without SO still expose `RunAsync<T>` | ❌ Agents without SO still expose `RunAsync<T>` | ❌ Interface on `ChatClientAgent` may be misleading | ❌ Agents without SO still expose `RunAsync<T>` |
| Implementation burden | ❌ Decorators must override method | ❌ Must handle schema wrapping | ❌ Agents must implement all interface members | ✅ Delegates to existing `RunAsync` via `ResponseFormat` |

## Cross-Cutting Aspects

1. **The `useJsonSchemaResponseFormat` parameter**: The `ChatClientAgent.RunAsync<T>` method has this parameter to enable structured output on LLMs that do not natively support it.
  It works by adding a user message like "Respond with a JSON value conforming to the following schema:" along with the JSON schema. However, this approach has not been reliable historically. The recommendation is not to carry this parameter forward, regardless of which option is chosen.

2. **Primitives and array types handling**: There are a few options for how primitive and array types can be handled in the Agent Framework:

   1. **Never wrap**, regardless of whether the schema is provided via `ResponseFormat` or `RunAsync<T>`.
       - Pro: No changes needed; user has full control.
       - Pro: No issues with unwrapping in streaming scenarios.
       - Con: User must wrap manually.

   2. **Always wrap**, regardless of whether the schema is provided via `ResponseFormat` or `RunAsync<T>`.
       - Pro: Consistent wrapping behavior; no manual wrapping needed.
       - Con: Inconsistent unwrapping behavior; it may be unexpected to have SO result wrapped when schema is provided via `ResponseFormat`.
       - Con: Impossible to know if SO result is wrapped to unwrap it in streaming scenarios.

   3. **Wrap only for `RunAsync<T>`** and do not wrap the schema provided via `ResponseFormat`.
       - Pro: No unexpectedly wrapped result when schema is provided via `ResponseFormat`.
       - Pro: Solves the problem with unwrapping in streaming scenarios.

   4. **User decides** whether to wrap schema provided via `ResponseFormat` using a new `wrapPrimitivesAndArrays` property of `ChatResponseFormatJson`. For SO provided via `RunAsync<T>`, AF always wraps.
       - Pro: No manual wrapping needed; just flip a switch.
       - Pro: Solves the problem with unwrapping in streaming scenarios.
       - Con: Extends the public API surface.

3. **Structured output for agents without native SO support**: Some AI agents in AF do not support structured output natively. This is either because it is not part of the protocol (e.g., A2A agent) or because the agents use LLMs without structured output capabilities.
   To address this gap, AF can provide the `StructuredOutputAgent` decorator. This decorator wraps any `AIAgent` and adds structured output support by obtaining the text response from the decorated agent and delegating it to a configured chat client for JSON transformation.
   
   ```csharp
   public class StructuredOutputAgent : DelegatingAIAgent
   {
        private readonly IChatClient _chatClient;

        public StructuredOutputAgent(AIAgent innerAgent, IChatClient chatClient)
            : base(innerAgent)
        {
            this._chatClient = Throw.IfNull(chatClient);
        }

        protected override async Task<AgentResponse<T>> RunCoreAsync<T>(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            JsonSerializerOptions? serializerOptions = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            // Run the inner agent first, to get back the text response we want to convert.
            var textResponse = await this.InnerAgent.RunAsync(messages, session, options, cancellationToken).ConfigureAwait(false);

            // Invoke the chat client to transform the text output into structured data.
            ChatResponse<T> soResponse = await this._chatClient.GetResponseAsync<T>(
                messages:
                [
                    new ChatMessage(ChatRole.System, "You are a json expert and when provided with any text, will convert it to the requested json format."),
                    new ChatMessage(ChatRole.User, textResponse.Text)
                ],
                serializerOptions: serializerOptions ?? AgentJsonUtilities.DefaultOptions,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            return new StructuredOutputAgentResponse(soResponse, textResponse);
        }
   }
   ```

   The decorator preserves the original response from the decorated agent and surfaces it via the `OriginalResponse` property on the returned `StructuredOutputAgentResponse`.
   This allows users to access both the original unstructured response and the new structured response when using this decorator.
   ```csharp
   public class StructuredOutputAgentResponse : AgentResponse
   {
       internal StructuredOutputAgentResponse(ChatResponse chatResponse, AgentResponse agentResponse) : base(chatResponse)
       {
           this.OriginalResponse = agentResponse;
       }
       
       public AgentResponse OriginalResponse { get; }
    }
   ```
   
   The decorator can be registered during the agent configuration step using the `UseStructuredOutput` extension method on `AIAgentBuilder`.

   ```csharp
   IChatClient meaiChatClient = chatClient.AsIChatClient();

   AIAgent baseAgent = meaiChatClient.AsAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

   // Register the StructuredOutputAgent decorator during agent building
   AIAgent agent = baseAgent
       .AsBuilder()
       .UseStructuredOutput(meaiChatClient)
       .Build();

   AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");

   Console.WriteLine($"Name: {response.Result.Name}");
   Console.WriteLine($"Age: {response.Result.Age}");
   Console.WriteLine($"Occupation: {response.Result.Occupation}");
   
   var originalResponse = ((StructuredOutputAgentResponse)response.RawRepresentation!).OriginalResponse;
   Console.WriteLine($"Original unstructured response: {originalResponse.Text}");

   ```

## Decision Outcome

It was decided to keep both approaches for structured output - via `ResponseFormat` and via `RunAsync<T>` since they serve different scenarios and use cases.

For the `RunAsync<T>` approach, option 4 was selected, which adds a generic `RunAsync<T>` method to `AIAgent` that works via the new `AgentRunOptions.ResponseFormat` property.
This was chosen for its simplicity and because no changes are required to existing `AIAgent` decorators.

For cross-cutting aspects, the `useJsonSchemaResponseFormat` parameter will not be carried forward due to reliability issues.

For handling primitives and array types, option 3 was selected: wrap only for `RunAsync<T>` and do not wrap the schema provided via `ResponseFormat`.
This avoids the issues described in the Approach 1 section note.

Finally, it was decided not to include the `StructuredOutputAgent` decorator in the framework, since the reliability of producing structured output via an additional
LLM call may not be sufficient for all scenarios. Instead, this pattern is provided as a sample to demonstrate how structured output can be achieved for agents without native support,
giving users a reference implementation they can adapt to their own requirements.