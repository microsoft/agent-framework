---
status: accepted
contact: westey-m
date: 2025-01-21
deciders: sergeymenshykh, markwallace, rbarreto, westey-m, stephentoub
consulted: reubenbond
informed:
---

# Feature Collections

## Context and Problem Statement

When using agents, we often have cases where we want to pass some arbitrary services or data to an agent or some component in the agent execution stack.
These services or data are not necessarily known at compile time and can vary by the agent stack that the user has built.
E.g., there may be an agent decorator or chat client decorator that was added to the stack by the user, and an arbitrary payload needs to be passed to that decorator.

Since these payloads are related to components that are not integral parts of the agent framework, they cannot be added as strongly typed settings to the agent run options.
However, the payloads could be added to the agent run options as loosely typed 'features', that can be retrieved as needed.

In some cases certain classes of agents may support the same capability, but not all agents do.
Having the configuration for such a capability on the main abstraction would advertise the functionality to all users, even if their chosen agent does not support it.
The user may type test for certain agent types, and call overloads on the appropriate agent types, with the strongly typed configuration.
Having a feature collection though, would be an alternative way of passing such configuration, without needing to type check the agent type.
All agents that support the functionality would be able to check for the configuration and use it, simplifying the user code.
If the agent does not support the capability, that configuration would be ignored.

### Sample Scenario 1 - Per Run ChatMessageStore Override for hosting Libraries

We are building an agent hosting library, that can host any agent built using the agent framework.
Where an agent is not built on a service that uses in-service chat history storage, the hosting library wants to force the agent to use
the hosting library's chat history storage implementation.
This chat history storage implementation may be specifically tailored to the type of protocol that the hosting library uses, e.g. conversation id based storage or response id based storage.
The hosting library does not know what type of agent it is hosting, so it cannot provide a strongly typed parameter on the agent.
Instead, it adds the chat history storage implementation to a feature collection, and if the agent supports custom chat history storage, it retrieves the implementation from the feature collection and uses it.

```csharp
// Pseudo-code for an agent hosting library that supports conversation id based hosting.
public async Task<string> HandleConversationsBasedRequestAsync(AIAgent agent, string conversationId, string userInput)
{
    var thread = await this._threadStore.GetOrCreateThread(conversationId);

    // The hosting library can set a per-run chat message store via Features that only applies for that run.
    // This message store will load and save messages under the conversation id provided.
    ConversationsChatMessageStore messageStore = new(this._dbClient, conversationId);
    var response = await agent.RunAsync(
        userInput,
        thread,
        options: new AgentRunOptions()
        {
            Features = new AgentFeatureCollection().WithFeature<ChatMessageStore>(messageStore)
        });

    await this._threadStore.SaveThreadAsync(conversationId, thread);
    return response.Text;
}

// Pseudo-code for an agent hosting library that supports response id based hosting.
public async Task<(string responseMessage, string responseId)> HandleResponseIdBasedRequestAsync(AIAgent agent, string previousResponseId, string userInput)
{
    var thread = await this._threadStore.GetOrCreateThreadAsync(previousResponseId);

    // The hosting library can set a per-run chat message store via Features that only applies for that run.
    // This message store will buffer newly added messages until explicitly saved after the run.
    ResponsesChatMessageStore messageStore = new(this._dbClient, previousResponseId);

    var response = await agent.RunAsync(
        userInput,
        thread,
        options: new AgentRunOptions()
        {
            Features = new AgentFeatureCollection().WithFeature<ChatMessageStore>(messageStore)
        });

    // Since the message store may not actually have been used at all (if the agent's underlying chat client requires service-based chat history storage),
    // we may not have anything to save back to the database.
    // We still want to generate a new response id though, so that we can save the updated thread state under that id.
    // We should also use the same id to save any buffered messages in the message store if there are any.
    var newResponseId = this.GenerateResponseId();
    if (messageStore.HasBufferedMessages)
    {
        await messageStore.SaveBufferedMessagesAsync(newResponseId);
    }
    
    // Save the updated thread state under the new response id that was generated by the store.
    await this._threadStore.SaveThreadAsync(newResponseId, thread);
    return (response.Text, newResponseId);
}
```

### Sample Scenario 2 - Structured output

Currently our base abstraction does not support structured output, since the capability is not supported by all agents.
For those agents that don't support structured output, we could add an agent decorator that takes the response from the underlying agent, and applies structured output parsing on top of it via an additional LLM call.

If we add structured output configuration as a feature, then any agent that supports structured output could retrieve the configuration from the feature collection and apply it, and where it is not supported, the configuration would simply be ignored.

We could add a simple StructuredOutputAgentFeature that can be added to the list of features and also be used to return the generated structured output.

```csharp
internal class StructuredOutputAgentFeature
{
    public Type? OutputType { get; set; }

    public JsonSerializerOptions? SerializerOptions { get; set; }

    public bool? UseJsonSchemaResponseFormat { get; set; }

    // Contains the result of the structured output parsing request.
    public ChatResponse? ChatResponse { get; set; }
}
```

We can add a simple decorator class that does the chat client invocation.

```csharp
public class StructuredOutputAgent : DelegatingAIAgent
{
    private readonly IChatClient _chatClient;
    public StructuredOutputAgent(AIAgent innerAgent, IChatClient chatClient)
        : base(innerAgent)
    {
        this._chatClient = Throw.IfNull(chatClient);
    }

    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        // Run the inner agent first, to get back the text response we want to convert.
        var response = await base.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

        if (options?.Features?.TryGet<StructuredOutputAgentFeature>(out var responseFormatFeature) is true
            && responseFormatFeature.OutputType is not null)
        {
            // Create the chat options to request structured output.
            ChatOptions chatOptions = new()
            {
                ResponseFormat = ChatResponseFormat.ForJsonSchema(responseFormatFeature.OutputType, responseFormatFeature.SerializerOptions)
            };

            // Invoke the chat client to transform the text output into structured data.
            // The feature is updated with the result.
            // The code can be simplified by adding a non-generic structured output GetResponseAsync
            // overload that takes Type as input.
            responseFormatFeature.ChatResponse = await this._chatClient.GetResponseAsync(
                messages: new[]
                {
                    new ChatMessage(ChatRole.System, "You are a json expert and when provided with any text, will convert it to the requested json format."),
                    new ChatMessage(ChatRole.User, response.Text)
                },
                options: chatOptions,
                cancellationToken: cancellationToken).ConfigureAwait(false);
        }

        return response;
    }
}
```

Finally, we can add an extension method on `AIAgent` that can add the feature to the run options and check the feature for the structured output result and add the deserialized result to the response.

```csharp
public static async Task<AgentRunResponse<T>> RunAsync<T>(
    this AIAgent agent,
    IEnumerable<ChatMessage> messages,
    AgentThread? thread = null,
    JsonSerializerOptions? serializerOptions = null,
    AgentRunOptions? options = null,
    bool? useJsonSchemaResponseFormat = null,
    CancellationToken cancellationToken = default)
{
    // Create the structured output feature.
    var structuredOutputFeature = new StructuredOutputAgentFeature();
    structuredOutputFeature.OutputType = typeof(T);
    structuredOutputFeature.UseJsonSchemaResponseFormat = useJsonSchemaResponseFormat;

    // Run the agent.
    options ??= new AgentRunOptions();
    options.Features ??= new AgentFeatureCollection();
    options.Features.Set(structuredOutputFeature);

    var response = await agent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

    // Deserialize the JSON output.
    if (structuredOutputFeature.ChatResponse is not null)
    {
        var typed = new ChatResponse<T>(structuredOutputFeature.ChatResponse, serializerOptions ?? AgentJsonUtilities.DefaultOptions);
        return new AgentRunResponse<T>(response, typed.Result);
    }

    throw new InvalidOperationException("No structured output response was generated by the agent.");
}
```

We can then use the extension method with any agent that supports structured output or that has
been decorated with the `StructuredOutputAgent` decorator.

```csharp
agent = new StructuredOutputAgent(agent, chatClient);

AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>([new ChatMessage(
    ChatRole.User,
    "Please provide information about John Smith, who is a 35-year-old software engineer.")]);
```

## Implementation Options

Three options were considered for implementing feature collections:

- **Option 1**: FeatureCollections similar to ASP.NET Core
- **Option 2**: AdditionalProperties Dictionary
- **Option 3**: IServiceProvider

Here are some comparisons about their suitability for our use case:

| Criteria         | Feature Collection | Additional Properties | IServiceProvider |
|------------------|--------------------|-----------------------|------------------|
|Ease of use       |✅ Good             |❌ Bad                |✅ Good           |
|User familiarity  |❌ Bad              |✅ Good               |✅ Good           |
|Type safety       |✅ Good             |❌ Bad                |✅ Good           |
|Ability to modify registered options when progressing down the stack|✅ Supported|✅ Supported|❌ Not-Supported (IServiceProvider is read-only)|
|Already available in MEAI stack|❌ No|✅ Yes|❌ No|
|Ambiguity with existing AdditionalProperties|❌ Yes|✅ No|❌ Yes|

## IServiceProvider

Service Collections and Service Providers provide a very popular way to register and retrieve services by type and could be used as a way to pass features to agents and chat clients.

However, since IServiceProvider is read-only, it is not possible to modify the registered services when progressing down the execution stack.
E.g. an agent decorator cannot add additional services to the IServiceProvider passed to it when calling into the inner agent.

IServiceProvider also does not expose a way to list all services contained in it, making it difficult to copy services from one provider to another.

This lack of mutability makes IServiceProvider unsuitable for our use case, since we will not be able to use it to build sample scenario 2.

## AdditionalProperties dictionary

The AdditionalProperties dictionary is already available on various options classes in the agent framework as well as in the MEAI stack and
allows storing arbitrary key/value pairs, where the key is a string and the value is an object.

While FeatureCollection uses Type as a key, AdditionalProperties uses string keys.
This means that users need to agree on string keys to use for specific features, however it is also possible to use Type.FullName as a key by convention
to avoid key collisions, which is an easy convention to follow.

Since the value of AdditionalProperties is of type object, users need to cast the value to the expected type when retrieving it, which is also
a drawback, but when using the convention of using Type.FullName as a key, there is at least a clear expectation of what type to cast to.

```csharp
// Setting a feature
options.AdditionalProperties[typeof(MyFeature).FullName] = new MyFeature();

// Retrieving a feature
if (options.AdditionalProperties.TryGetValue(typeof(MyFeature).FullName, out var featureObj)
    && featureObj is MyFeature myFeature)
{
    // Use myFeature
}
```

It would also be possible to add extension methods to simplify setting and getting features from AdditionalProperties.
Having a base class for features should help make this more feature rich.

```csharp
// Setting a feature, this can use Type.FullName as the key.
options.AdditionalProperties
    .WithFeature(new MyFeature());

// Retrieving a feature, this can use Type.FullName as the key.
if (options.AdditionalProperties.TryGetFeature<MyFeature>(out var myFeature))
{
    // Use myFeature
}
```

It would also be possible to add extension methods for a feature to simplify setting and getting features from AdditionalProperties.

```csharp
// Setting a feature
options.AdditionalProperties
    .WithMyFeature(new MyFeature());
// Retrieving a feature
if (options.AdditionalProperties.TryGetMyFeature(out var myFeature))
{
    // Use myFeature
}
```

## Feature Collection

If we choose the feature collection option, we need to decide on the design of the feature collection itself.

### Feature Collections extension points

We need to decide the set of actions that feature collections would be supported for. Here is the suggested list of actions:

**MAAI.AIAgent:**

1. GetNewThread
    1. E.g. this would allow passing an already existing storage id for the thread to use, or an initialized custom chat message store to use.
1. DeserializeThread
    1. E.g. this would allow passing an already existing storage id for the thread to use, or an initialized custom chat message store to use.
1. Run / RunStreaming
    1. E.g. this would allow passing an override chat message store just for that run, or a desired schema for a structured output middleware component.

**MEAI.ChatClient:**

1. GetResponse / GetStreamingResponse

### Reconciling with existing AdditionalProperties

If we decide to add feature collections, separately from the existing AdditionalProperties dictionaries, we need to consider how to explain to users when to use each one.
One possible approach though is to have the one use the other under the hood.
AdditionalProperties could be stored as a feature in the feature collection.

Users would be able to retrieve additional properties from the feature collection, in addition to retrieving it via a dedicated AdditionalProperties property.
E.g. `features.Get<AdditionalPropertiesDictionary>()`

One challenge with this approach is that when setting a value in the AdditionalProperties dictionary, the feature collection would need to be created first if it does not already exist.

```csharp
public class AgentRunOptions
{
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
    public IAgentFeatureCollection? Features { get; set; }
}

var options = new AgentRunOptions();
// This would need to create the feature collection first, if it does not already exist.
options.AdditionalProperties ??= new AdditionalPropertiesDictionary();
```

Since IAgentFeatureCollection is an interface, AgentRunOptions would need to have a concrete implementation of the interface to create, meaning that the user cannot decide.
It also means that if the user doesn't realise that AdditionalProperties is implemented using feature collections, they may set a value on AdditionalProperties, and then later overwrite the entire feature collection, losing the AdditionalProperties feature.

Options to avoid these issues:

1. Make `Features` readonly.
    1. This would prevent the user from overwriting the feature collection after setting AdditionalProperties.
    1. Since the user cannot set their own implementation of IAgentFeatureCollection, having an interface for it may not be necessary.

### Feature Collection Implementation

We have two options for implementing feature collections:

1. Create our own [IAgentFeatureCollection interface](https://github.com/microsoft/agent-framework/pull/2354/files#diff-9c42f3e60d70a791af9841d9214e038c6de3eebfc10e3997cb4cdffeb2f1246d) and [implementation](https://github.com/microsoft/agent-framework/pull/2354/files#diff-a435cc738baec500b8799f7f58c1538e3bb06c772a208afc2615ff90ada3f4ca).
2. Reuse the asp.net [IFeatureCollection interface](https://github.com/dotnet/aspnetcore/blob/main/src/Extensions/Features/src/IFeatureCollection.cs) and [implementation](https://github.com/dotnet/aspnetcore/blob/main/src/Extensions/Features/src/FeatureCollection.cs).

#### Roll our own

Advantages:

Creating our own IAgentFeatureCollection interface and implementation has the advantage of being more clearly associated with the agent framework and allows us to
improve on some of the design decisions made in asp.net core's IFeatureCollection.

Drawbacks:

It would mean a different implementation to maintain and test.

#### Reuse asp.net IFeatureCollection

Advantages:

Reusing the asp.net IFeatureCollection has the advantage of being able to reuse the well-established and tested implementation from asp.net
core. Users who are using agents in an asp.net core application may be able to pass feature collections from asp.net core to the agent framework directly.

Drawbacks:

While the package name is `Microsoft.Extensions.Features`, the namespaces of the types are `Microsoft.AspNetCore.Http.Features`, which may create confusion for users of agent framework who are not building web applications or services.
Users may rightly ask: Why do I need to use a class from asp.net core when I'm not building a web application / service?

The current design has some design issues that would be good to avoid.  E.g. it does not distinguish between a feature being "not set" and "null". Get returns both as null and there is no tryget method.
Since the [default implementation](https://github.com/dotnet/aspnetcore/blob/main/src/Extensions/Features/src/FeatureCollection.cs) also supports value types, it throws for null values of value types.
A TryGet method would be more appropriate.

## Feature Layering

One possible scenario when adding support for feature collections is to allow layering of features by scope.

The following levels of scope could be supported:

1. Application - Application wide features that apply to all agents / chat clients
2. Artifact (Agent / ChatClient) - Features that apply to all runs of a specific agent or chat client instance
3. Action (GetNewThread / Run / GetResponse) - Feature that apply to a single action only

When retrieving a feature from the collection, the search would start from the most specific scope (Action) and progress to the least specific scope (Application), returning the first matching feature found.

Introducing layering adds some challenges:

- There may be multiple feature collections at the same scope level, e.g. an Agent that uses a ChatClient where both have their own feature collections.
  - Do we layer the agent feature collection over the chat client feature collection (Application -> ChatClient -> Agent -> Run), or only use the agent feature collection in the agent (Application -> Agent -> Run), and the chat client feature collection in the chat client (Application -> ChatClient -> Run)?
- The appropriate base feature collection may change when progressing down the stack, e.g. when an Agent calls a ChatClient, the action feature collection stays the same, but the artifact feature collection changes.
- Who creates the feature collection hierarchy?
  - Since the hierarchy changes as it progresses down the execution stack, and the caller can only pass in the action level feature collection, the callee needs to combine it with its own artifact level feature collection and the application level feature collection. Each action will need to build the appropriate feature collection hierarchy, at the start of its execution.
- For Artifact level features, it seems odd to pass them in as a bag of untyped features, when we are constructing a known artifact type and therefore can have typed settings.
  - E.g. today we have a strongly typed setting on ChatClientAgentOptions to configure a ChatMessageStore for the agent.
- To avoid global statics for application level features, the user would need to pass in the application level feature collection to each artifact that they create.
  - This would be very odd if the user also already has to strongly typed settings for each feature that they want to set at the artifact level.

### Layering Options

1. No layering - only a single feature collection is supported per action (the caller can still create a layered collection if desired, but the callee does not do any layering automatically).
    1. Fallback is to any features configured on the artifact via strongly typed settings.
1. Full layering - support layering at all levels (Application -> Artifact -> Action).
    1. Only apply applicable artifact level features when calling into that artifact.
    1. Apply upstream artifact features when calling into downstream artifacts, e.g. Feature hierarchy in ChatClientAgent would be `Application -> Agent -> Run` and in ChatClient would be `Application -> ChatClient -> Agent -> Run` or `Application -> Agent -> ChatClient -> Run`
    1. The user needs to provide the application level feature collection to each artifact that they create and artifact features are passed via strongly typed settings.

### Accessing application level features Options

We need to consider how application level features would be accessed if supported.

1. The user provides the application level feature collection to each artifact that the user constructs
    1. Passing the application level feature collection to each artifact is tedious for the user.
1. There is a static application level feature collection that can be accessed globally.
    1. Statics create issues with testing and isolation.

## Decisions

- Feature Collections Container: Use AdditionalProperties
- Feature Layering: No layering - only a single collection/dictionary is supported per action. Application layers can be added later if needed.
