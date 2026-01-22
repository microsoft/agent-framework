---
status: proposed
contact: sergeymenshykh
date: 2026-01-22
deciders: markwallace, rbarreto, westey-m, stephentoub
informed: {}
---

# Structured Output

Structured output is a valuable aspect of any Agent system, since it forces an Agent to produce output in a required format, and may include required fields.
This allows turning unstructured data into structured data easily using a general purpose language model.

## Context and Problem Statement

Structured output is currently supported only by `ChatClientAgent` and can be configured in two ways:

**Approach 1: ResponseFormat + Deserialize**

Specify the SO type schema via the `ChatClientAgent{Run}Options.ChatOptions.ResponseFormat` property at agent creation or invocation time, then use the `{Try}Deserialize<T>` method to extract the structured data from the response.

	```csharp
	// SO type can be provided at agent creation time
	ChatClientAgent agent = chatClient.CreateAIAgent(new ChatClientAgentOptions()
	{
		Name = "...",
		ChatOptions = new() { ResponseFormat = ChatResponseFormat.ForJsonSchema<PersonInfo>() }
	});

	AgentRunResponse response = await agent.RunAsync("...");

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
	
	AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("...");

	Console.WriteLine($"Name: {response.Result.Name}");
	Console.WriteLine($"Age: {response.Result.Age}");
	Console.WriteLine($"Occupation: {response.Result.Occupation}");
	```
	Note: `RunAsync<T>` is an instance method of `ChatClientAgent` and not part of the `AIAgent` base class since not all agents support structured output.

**Current Limitations**

Approach 1 is perceived as cumbersome by the community. It also has a limitation when using primitive or collection types: the SO schema may need to be wrapped in an artificial JSON object. Otherwise, you'll encounter an error like _Invalid schema for response_format 'Movie': schema must be a JSON Schema of 'type: "object"', got 'type: "array"'_. This occurs because OpenAI and compatible APIs require a JSON object as the root schema.

Approach 1 is also necessary in scenarios where agents can only be configured at creation time (such as with `AIProjectClient`) or when the SO type is not known at compile time (such as for declarative agents).

Approach 2 is more convenient and solves the issue with primitives and collections. However, it requires the SO type to be known at compile time, making it less flexible.

Additionally, since `RunAsync<T>` is not part of the `AIAgent` base class, applying decorators like `OpenTelemetryAgent` on top of `ChatClientAgent` prevents users from accessing `RunAsync<T>`, which means structured output is not available with decorated agents.

**Conclusion**

Looking at scenarios where the SO type can be represented by a type known at compile time, or provided as a JSON schema, it's not
feasible to have a single solution that covers all scenarios well. Therefore, we need to consider multiple solutions that can coexist and complement each other.

The table below summarizes the different scenarios and how they can be addressed:

|  | SO type provided at agent creation | SO type provided per agent run |
|---|---|---|
| SO type is not available at compile time | `{AgentName}Options.ResponseFormat` <br/> `AgentResponse.Deserialize<T>()` | `{AgentName}RunOptions.ResponseFormat` <br/> `AgentResponse.Deserialize<T>()` |
| SO type available at compile time | `{AgentName}Options.ResponseFormat` <br/> `AgentResponse.Deserialize<T>()` | `RunAsync<T>()`  |

## Solutions Overview

1. SO configuration at agent creation and at agent invocation if SO type is not available at compile time
2. SO configuration at agent invocation if SO type is available at compile time

## 1. SO configuration at agent creation and at agent invocation if SO type is not available at compile time

This solution covers two scenarios:

**Scenario A: Configure SO at agent creation**

```csharp
AIAgent agent = this._client.CreateAIAgent(model: s_deploymentName, options: new ChatClientAgentOptions()
{
    ChatOptions = new ()
    {
        Instructions = "You are a car information expert.",
        ResponseFormat = declarativeAgentRecord.AsChatResponseFormat()
    }
});

AgentResponse response = await agent.RunAsync("What is most efficient and reliable car in 2026?");

JsonElement carInfo = response.Deserialize<JsonElement>();
```

**Scenario B: Configure SO at agent invocation (when the target type is not known at compile time)**

```csharp
AIAgent agent = this._client.CreateAIAgent(model: s_deploymentName, options: new ChatClientAgentOptions());

ChatClientAgentRunOptions options = new()
{
    ChatOptions = new ()
    {
        ResponseFormat = jsonSchema.AsChatResponseFormat()
    },
};

AgentResponse response = await agent.RunAsync("What is most efficient and reliable car in 2026?", options: options);

JsonElement carInfo = response.Deserialize<object>();
```

The `ChatClientAgent` already implements this solution using the following components:
- `ChatClientAgentOptions.ChatOptions.ResponseFormat` for SO configuration at agent creation time.
- `ChatClientAgentRunOptions.ChatOptions.ResponseFormat` for SO configuration at agent invocation time.
- `AgentResponse.Deserialize<T>` and `AgentResponse.TryDeserialize` methods for deserializing the agent response into the SO type.

There is a limitation when the SO type is a primitive or a collection: the underlying OpenAI-like LLM will throw an error. Users must manually wrap primitive or collection schemas in a JSON object schema that matches what the LLM expects.

A future improvement could have agents automatically wrap primitive or collection schemas in a JSON object schema internally and unwrap them before deserialization. This would align how primitives and collections are handled across both solutions: this one and the one described in the next section.

For agents that do not natively support SO (e.g., A2A agents), and when the SO type is not known at compile time, the `StructuredOutputAgent` decorator can enable SO support:
```csharp
public class StructuredOutputAgent : DelegatingAIAgent
{
    private readonly IChatClient _chatClient;
    private readonly ChatResponseFormatJson? _responseFormat;

    public StructuredOutputAgent(AIAgent innerAgent, IChatClient chatClient, ChatResponseFormatJson? responseFormat = null)
        : base(innerAgent)
    {
        this._chatClient = Throw.IfNull(chatClient);
        this._responseFormat = responseFormat;
    }

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Run the inner agent first, to get back the text response we want to convert.
        var response = await this.InnerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

        ChatResponseFormatJson responseFormat = options?.ResponseFormat
            ?? this._responseFormat
            ?? throw new InvalidOperationException("Response format must be specified either in the agent or in the run options.");

        // Invoke the chat client to transform the text output into structured data.
        ChatResponse chatResponse = await this._chatClient.GetResponseAsync(
            messages:
            [
                new ChatMessage(ChatRole.System, "You are a json expert and when provided with any text, will convert it to the requested json format."),
                new ChatMessage(ChatRole.User, response.Text)
            ],
            options: new() { ResponseFormat = responseFormat },
            cancellationToken: cancellationToken).ConfigureAwait(false);

        return new StructuredOutputAgentResponse(chatResponse, response);
    }
}
```

The decorator can accept `ResponseFormat` via constructor or, if `ResponseFormat` is required per agent run, the `AgentRunOptions` can be extended to include it. The format provided per run will override the one provided via constructor.

## 2. SO configuration at agent invocation if SO type is available at compile time

This solution provides a convenient way to work with structured output on a per-run basis when the target type is known at compile time.

### Decision Drivers

1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

### Considered Options

1. `RunAsync<T>` as an instance method of `AIAgent` class
2. `RunAsync<T>` as an extension method using feature collection
3. `RunAsync<T>` as a method of the new `ITypedAIAgent` interface

### 1. `RunAsync<T>` as an instance method of `AIAgent` class

This option adds the `RunAsync<T>` method directly to the `AIAgent` base class.

```csharp
public abstract class AIAgent
{
	public Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
		=> this.RunCoreAsync<T>(messages, thread, serializerOptions, options, cancellationToken);

    protected virtual Task<AgentResponse<T>> RunCoreAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        throw new NotSupportedException($"The agent of type '{this.GetType().FullName}' does not support typed responses.");
    }
}
```

Agents with native SO support override the `RunCoreAsync<T>` method to provide their implementation. If not overridden, the method throws a `NotSupportedException`.

For agents without native SO support (e.g., A2A agents), a `StructuredOutputAgent` decorator enables SO capability.
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
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Run the inner agent first, to get back the text response we want to convert.
        var response = await this.InnerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

        // Invoke the chat client to transform the text output into structured data.
        ChatResponse<T> chatResponse = await this._chatClient.GetResponseAsync<T>(
            messages:
            [
                new ChatMessage(ChatRole.System, "You are a json expert and when provided with any text, will convert it to the requested json format."),
                new ChatMessage(ChatRole.User, response.Text)
            ],
            serializerOptions: serializerOptions ?? AgentJsonUtilities.DefaultOptions,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        return new StructuredOutputAgentResponse<T>(chatResponse, response);
    }
}
```

Usage for agents with native SO support:
```csharp
AIAgent agent = new (...);

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");
```

Usage for agents without native SO support:
```csharp
AIAgent agent = new A2AAgent(...);

IChatClient chatClient = new OpenAIClient(s_apiKey)
    .GetResponsesClient(_model)
    .AsIChatClient();

agent = new StructuredOutputAgent(agent, chatClient); // Will be wrapped into IHostedAgentBuilder.WithStructuredOutput extension method

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
    AgentThread? thread = null,
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

    var response = await agent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

    if (structuredOutputFeature.Response is not null)
    {
        return new StructuredOutputResponse<T>(structuredOutputFeature.Response, response, serializerOptions);
    }

    throw new InvalidOperationException("No structured output response was generated by the agent.");
}
```

For agents without native SO support (e.g., A2A agents), a `StructuredOutputAgent` decorator enables SO capability.
```csharp
public class StructuredOutputAgent : DelegatingAIAgent
{
    private readonly IChatClient _chatClient;

    public StructuredOutputAgent(AIAgent innerAgent, IChatClient chatClient)
        : base(innerAgent)
    {
        this._chatClient = Throw.IfNull(chatClient);
    }

    protected override async Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Run the inner agent first, to get back the text response we want to convert.
        var response = await this.InnerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

        StructuredOutputFeature? soFeature =
            options?.AdditionalProperties?.TryGetValue(typeof(StructuredOutputFeature).FullName!, out var value) is true && value is StructuredOutputFeature feature
            ? feature
            : null;

        // If the structural output feature is not present or the result is provided, return the response as is.
        if (soFeature is null)
        {
            return response;
        }

        // Invoke the chat client to transform the text output into structured data.
        // The feature is updated with the result.
        // The code can be simplified by adding a non-generic structured output GetResponseAsync
        // overload that takes Type as input.
        ChatResponse chatResponse = await this._chatClient.GetResponseAsync(
            messages:
            [
                new ChatMessage(ChatRole.System, "You are a json expert and when provided with any text, will convert it to the requested json format."),
                new ChatMessage(ChatRole.User, response.Text)
            ],
            options: new() { ResponseFormat = ChatResponseFormat.ForJsonSchema(soFeature.OutputType, soFeature.SerializerOptions) },
            cancellationToken: cancellationToken).ConfigureAwait(false);

        soFeature.Response = new AgentResponse(chatResponse);

        return response;
    }
}
```

Usage for agents with native SO support:
```csharp
AIAgent agent = new (...);

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");
```

Usage for agents without native SO support:
```csharp
AIAgent agent = new A2AAgent(...);

IChatClient chatClient = new OpenAIClient(s_apiKey)
    .GetResponsesClient(_model)
    .AsIChatClient();

agent = new StructuredOutputAgent(agent, chatClient); // Will be wrapped into IHostedAgentBuilder.WithStructuredOutput extension method

AgentResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>("Please provide information about John Smith, who is a 35-year-old software engineer.");
```

Decision drivers satisfied:
1. Support arrays and primitives as SO types
2. Support complex types as SO types
3. Work with `AIAgent` decorators (e.g., `OpenTelemetryAgent`)
4. Enable SO for all AI agents, regardless of whether they natively support it

This option satisfies all decision drivers, with one caveat: to fully support primitives and collections, the Agent Framework must handle wrapping them into a JSON object schema internally. This is necessary because the solution cannot provide compile-time access to type `T` for the SO decorator and `ChatClientAgent`, making it impossible to use the native `IChatClient.GetResponseAsync<T>` API (except via reflection).

Pros:
- The `RunAsync<T>` extension method is easily discoverable.
- The `AIAgent` public API surface remains unchanged.
- No changes required to `AIAgent` decorators.

Cons:
- Agents without native SO support will still expose `RunAsync<T>`, which may be misleading.
- `ChatClientAgent` exposing `RunAsync<T>` may be misleading when the underlying chat client does not support SO.
- Must handle wrapping and unwrapping of primitives and collections to/from JSON object schema internally, rather than relying on the native `IChatClient.GetResponseAsync<T>` API.

### 3. `RunAsync<T>` as a method of the new `ITypedAIAgent` interface

This option defines a new `ITypedAIAgent` interface that agents with SO support implement. Agents without SO support do not implement it, allowing users to check for SO capability via interface detection.

The interface:
```csharp
public interface ITypedAIAgent
{
    Task<AgentResponse<T>> RunAsync<T>(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
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
        AgentThread? thread = null,
        JsonSerializerOptions? serializerOptions = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        ...
    }
}
```

However, `ChatClientAgent` presents a challenge: it can work with chat clients that either support or do not support SO. Implementing the interface does not guarantee the underlying chat client supports SO, which undermines the core idea of using interface detection to determine SO capability.

Additionally, to allow users to access interface methods on decorated agents, all decorators must implement `ITypedAIAgent`. This makes it difficult for users to determine whether the underlying agent actually supports SO, further weakening the purpose of this approach.

Additionally, users will have to probe the agent type to check if it implements the `ITypedAIAgent` interface and cast it to the interface to access the `RunAsync<T>` methods. That adds friction to the user experience. A `RunAsync<T>` extension method for `AIAgent` could be provided to alleviate that.

Similar to the other options, a `StructuredOutputAgent` decorator would be provided to add SO support to agents that do not natively support SO.

Given these drawbacks, this option is more complex to implement than the other two without providing clear benefits.

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

### Decision Table

|  | Option 1: Instance Method | Option 2: Extension Method | Option 3: ITypedAIAgent Interface |
|---|---|---|---|
| Discoverability | ✅ `RunAsync<T>` easily discoverable | ✅ `RunAsync<T>` easily discoverable | ❌ Requires type check and cast |
| Decorator changes | ❌ All decorators must override `RunCoreAsync<T>` | ✅ No changes required | ❌ All decorators must implement `ITypedAIAgent` |
| Primitives/collections handling | ✅ Native support via `IChatClient.GetResponseAsync<T>` | ❌ Must wrap/unwrap internally | ✅ Native support via `IChatClient.GetResponseAsync<T>` |
| Misleading API exposure | ❌ Agents without SO still expose `RunAsync<T>` | ❌ Agents without SO still expose `RunAsync<T>` | ❌ Interface on `ChatClientAgent` may be misleading |
| Implementation burden | ❌ Decorators must override method | ❌ Must handle schema wrapping | ❌ Agents must implement all interface members |

## Additional Considerations

1. **The `useJsonSchemaResponseFormat` parameter**: The `ChatClientAgent.RunAsync<T>` method has this parameter to enable structured output on LLMs that do not natively support it. It works by adding a user message like "Respond with a JSON value conforming to the following schema:" along with the JSON schema. However, this approach has not been reliable historically. The recommendation is to not carry this parameter forward, regardless of which option is chosen.

2. **SO response vs agent response**: When using the `StructuredOutputAgent` decorator, two responses are produced: the original agent response (text) and the structured output response. The structured output response is proposed to be returned as the primary one since the user requested structured output. To access the original text response, a cast to `StructuredOutputAgentResponse<T>` will be required to use its `AgentResponse` property.
```csharp
public class StructuredOutputAgentResponse<T> : AgentResponse<T>
{
    private readonly ChatResponse<T> _soResponse;

    public StructuredOutputAgentResponse(ChatResponse<T> soResponse, AgentResponse response) : base(soResponse)
    {
        this._soResponse = soResponse;
        this.AgentResponse = response;
    }

    public AgentResponse AgentResponse { get; }
    
    public override T Result
    {
        get
        {
            return this._soResponse.Result;
        }
    }
}
```

## Decision Outcome

Chosen option: "{title of option 1}", because
{justification. e.g., only option, which meets k.o. criterion decision driver | which resolves force {force} | ... | comes out best (see below)}.
