// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an <see cref="AIAgent"/> that delegates to an <see cref="IChatClient"/> implementation.
/// </summary>
public sealed partial class ChatClientAgent : AIAgent
{
    private readonly ChatClientAgentOptions? _agentOptions;
    private readonly AIAgentMetadata _agentMetadata;
    private readonly ILogger _logger;
    private readonly Type _chatClientType;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use when running the agent.</param>
    /// <param name="instructions">
    /// Optional system instructions that guide the agent's behavior. These instructions are provided to the <see cref="IChatClient"/>
    /// with each invocation to establish the agent's role and behavior.
    /// </param>
    /// <param name="name">
    /// Optional name for the agent. This name is used for identification and logging purposes.
    /// </param>
    /// <param name="description">
    /// Optional human-readable description of the agent's purpose and capabilities.
    /// This description can be useful for documentation and agent discovery scenarios.
    /// </param>
    /// <param name="tools">
    /// Optional collection of tools that the agent can invoke during conversations.
    /// These tools augment any tools that may be provided to the agent via <see cref="ChatOptions.Tools"/> when
    /// the agent is run.
    /// </param>
    /// <param name="loggerFactory">
    /// Optional logger factory for creating loggers used by the agent and its components.
    /// </param>
    /// <param name="services">
    /// Optional service provider for resolving dependencies required by AI functions and other agent components.
    /// This is particularly important when using custom tools that require dependency injection.
    /// This is only relevant when the <see cref="IChatClient"/> doesn't already contain a <see cref="FunctionInvokingChatClient"/>
    /// and the <see cref="ChatClientAgent"/> needs to insert one.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="chatClient"/> is <see langword="null"/>.</exception>
    public ChatClientAgent(IChatClient chatClient, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null, IServiceProvider? services = null)
        : this(
              chatClient,
              new ChatClientAgentOptions
              {
                  ChatOptions = (tools is null && string.IsNullOrWhiteSpace(instructions)) ? null : new ChatOptions
                  {
                      Tools = tools,
                      Instructions = instructions
                  },
                  Name = name,
                  Description = description
              },
              loggerFactory,
              services)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use when running the agent.</param>
    /// <param name="options">
    /// Configuration options that control all aspects of the agent's behavior, including chat settings,
    /// chat history provider factories, context provider factories, and other advanced configurations.
    /// </param>
    /// <param name="loggerFactory">
    /// Optional logger factory for creating loggers used by the agent and its components.
    /// </param>
    /// <param name="services">
    /// Optional service provider for resolving dependencies required by AI functions and other agent components.
    /// This is particularly important when using custom tools that require dependency injection.
    /// This is only relevant when the <see cref="IChatClient"/> doesn't already contain a <see cref="FunctionInvokingChatClient"/>
    /// and the <see cref="ChatClientAgent"/> needs to insert one.
    /// </param>
    /// <exception cref="ArgumentNullException"><paramref name="chatClient"/> is <see langword="null"/>.</exception>
    public ChatClientAgent(IChatClient chatClient, ChatClientAgentOptions? options, ILoggerFactory? loggerFactory = null, IServiceProvider? services = null)
    {
        _ = Throw.IfNull(chatClient);

        // Options must be cloned since ChatClientAgentOptions is mutable.
        this._agentOptions = options?.Clone();

        this._agentMetadata = new AIAgentMetadata(chatClient.GetService<ChatClientMetadata>()?.ProviderName);

        // Get the type of the chat client before wrapping it as an agent invoking chat client.
        this._chatClientType = chatClient.GetType();

        // If the user has not opted out of using our default decorators, we wrap the chat client.
        this.ChatClient = options?.UseProvidedChatClientAsIs is true ? chatClient : chatClient.WithDefaultAgentMiddleware(options, services);

        this._logger = (loggerFactory ?? chatClient.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance).CreateLogger<ChatClientAgent>();
    }

    /// <summary>
    /// Gets the underlying chat client used by the agent to invoke chat completions.
    /// </summary>
    /// <value>
    /// The <see cref="IChatClient"/> instance that backs this agent.
    /// </value>
    /// <remarks>
    /// This may return the original client provided when the <see cref="ChatClientAgent"/> was constructed, or it may
    /// return a pipeline of decorating <see cref="IChatClient"/> instances applied around that inner client.
    /// </remarks>
    public IChatClient ChatClient { get; }

    /// <inheritdoc/>
    protected override string? IdCore => this._agentOptions?.Id;

    /// <inheritdoc/>
    public override string? Name => this._agentOptions?.Name;

    /// <inheritdoc/>
    public override string? Description => this._agentOptions?.Description;

    /// <summary>
    /// Gets the system instructions that guide the agent's behavior during conversations.
    /// </summary>
    /// <value>
    /// A string containing the system instructions that are provided to the underlying chat client
    /// to establish the agent's role, personality, and behavioral guidelines. May be <see langword="null"/>
    /// if no specific instructions were configured.
    /// </value>
    /// <remarks>
    /// These instructions are typically provided to the AI model as system messages to establish
    /// the context and expected behavior for the agent's responses.
    /// </remarks>
    public string? Instructions => this._agentOptions?.ChatOptions?.Instructions;

    /// <summary>
    /// Gets of the default <see cref="ChatOptions"/> used by the agent.
    /// </summary>
    internal ChatOptions? ChatOptions => this._agentOptions?.ChatOptions;

    /// <inheritdoc/>
    protected override Task<AgentResponse> RunCoreAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        static Task<ChatResponse> GetResponseAsync(IChatClient chatClient, List<ChatMessage> threadMessages, ChatOptions? chatOptions, CancellationToken ct)
        {
            return chatClient.GetResponseAsync(threadMessages, chatOptions, ct);
        }

        static AgentResponse CreateResponse(ChatResponse chatResponse)
        {
            return new AgentResponse(chatResponse)
            {
                ContinuationToken = WrapContinuationToken(chatResponse.ContinuationToken)
            };
        }

        return this.RunCoreAsync(GetResponseAsync, CreateResponse, messages, session, options, cancellationToken);
    }

    /// <summary>
    /// Configures the specified <see cref="IChatClient"/> instance based on the provided run options and chat options.
    /// </summary>
    /// <remarks>This method applies transformations and customizations to the chat client and chat options
    /// based on the provided <paramref name="options"/>. If no applicable options are provided, the original <paramref
    /// name="chatClient"/> is returned unchanged.</remarks>
    /// <param name="options">The run options to apply. If <paramref name="options"/> is of type <see cref="ChatClientAgentRunOptions"/>,
    /// additional configuration such as tool transformations and custom chat client creation may be applied.</param>
    /// <param name="chatClient">The <see cref="IChatClient"/> instance to configure. If a custom chat client factory is provided in <see
    /// cref="ChatClientAgentRunOptions.ChatClientFactory"/>, a new <see cref="IChatClient"/> instance may be created.</param>
    /// <returns>The configured <see cref="IChatClient"/> instance. If a custom chat client factory is used, the returned
    /// instance may differ from the input <paramref name="chatClient"/>.</returns>
    private static IChatClient ApplyRunOptionsTransformations(AgentRunOptions? options, IChatClient chatClient)
    {
        if (options is ChatClientAgentRunOptions agentChatOptions && agentChatOptions.ChatClientFactory is not null)
        {
            // If we have a custom chat client factory, we should use it to create a new chat client with the transformed tools.
            chatClient = agentChatOptions.ChatClientFactory(chatClient);
            _ = Throw.IfNull(chatClient);
        }

        return chatClient;
    }

    /// <inheritdoc/>
    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        (ChatClientAgentSession safeSession,
         ChatOptions? chatOptions,
         List<ChatMessage> inputMessagesForProviders,
         List<ChatMessage> inputMessagesForChatClient,
         ChatClientAgentContinuationToken? continuationToken) =
            await this.PrepareSessionAndMessagesAsync(session, inputMessages, options, cancellationToken).ConfigureAwait(false);

        var chatClient = this.ChatClient;

        chatClient = ApplyRunOptionsTransformations(options, chatClient);

        var loggingAgentName = this.GetLoggingAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunStreamingAsync), this.Id, loggingAgentName, this._chatClientType);

        List<ChatResponseUpdate> responseUpdates = GetResponseUpdates(continuationToken);

        IAsyncEnumerator<ChatResponseUpdate> responseUpdatesEnumerator;

        try
        {
            // Using the enumerator to ensure we consider the case where no updates are returned for notification.
            responseUpdatesEnumerator = chatClient.GetStreamingResponseAsync(inputMessagesForChatClient, chatOptions, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            await this.NotifyChatHistoryProviderOfFailureAsync(safeSession, ex, GetInputMessages(inputMessagesForProviders, continuationToken), chatOptions, cancellationToken).ConfigureAwait(false);
            await this.NotifyAIContextProviderOfFailureAsync(safeSession, ex, GetInputMessages(inputMessagesForProviders, continuationToken), cancellationToken).ConfigureAwait(false);
            throw;
        }

        this._logger.LogAgentChatClientInvokedStreamingAgent(nameof(RunStreamingAsync), this.Id, loggingAgentName, this._chatClientType);

        bool hasUpdates;
        try
        {
            // Ensure we start the streaming request
            hasUpdates = await responseUpdatesEnumerator.MoveNextAsync().ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await this.NotifyChatHistoryProviderOfFailureAsync(safeSession, ex, GetInputMessages(inputMessagesForProviders, continuationToken), chatOptions, cancellationToken).ConfigureAwait(false);
            await this.NotifyAIContextProviderOfFailureAsync(safeSession, ex, GetInputMessages(inputMessagesForProviders, continuationToken), cancellationToken).ConfigureAwait(false);
            throw;
        }

        while (hasUpdates)
        {
            var update = responseUpdatesEnumerator.Current;
            if (update is not null)
            {
                update.AuthorName ??= this.Name;

                responseUpdates.Add(update);

                yield return new(update)
                {
                    AgentId = this.Id,
                    ContinuationToken = WrapContinuationToken(update.ContinuationToken, GetInputMessages(inputMessages, continuationToken), responseUpdates)
                };
            }

            try
            {
                hasUpdates = await responseUpdatesEnumerator.MoveNextAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await this.NotifyChatHistoryProviderOfFailureAsync(safeSession, ex, GetInputMessages(inputMessagesForProviders, continuationToken), chatOptions, cancellationToken).ConfigureAwait(false);
                await this.NotifyAIContextProviderOfFailureAsync(safeSession, ex, GetInputMessages(inputMessagesForProviders, continuationToken), cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        var chatResponse = responseUpdates.ToChatResponse();

        // We can derive the type of supported session from whether we have a conversation id,
        // so let's update it and set the conversation id for the service session case.
        await this.UpdateSessionWithTypeAndConversationIdAsync(safeSession, chatResponse.ConversationId, cancellationToken).ConfigureAwait(false);

        // To avoid inconsistent state we only notify the session of the input messages if no error occurs after the initial request.
        await this.NotifyChatHistoryProviderOfNewMessagesAsync(safeSession, GetInputMessages(inputMessagesForProviders, continuationToken), chatResponse.Messages, chatOptions, cancellationToken).ConfigureAwait(false);

        // Notify the AIContextProvider of all new messages.
        await this.NotifyAIContextProviderOfSuccessAsync(safeSession, GetInputMessages(inputMessagesForProviders, continuationToken), chatResponse.Messages, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey) ??
        (serviceType == typeof(AIAgentMetadata) ? this._agentMetadata
        : serviceType == typeof(IChatClient) ? this.ChatClient
        : serviceType == typeof(ChatOptions) ? this._agentOptions?.ChatOptions
        : serviceType == typeof(ChatClientAgentOptions) ? this._agentOptions
        : this.ChatClient.GetService(serviceType, serviceKey));

    /// <inheritdoc/>
    protected override async ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
    {
        ChatHistoryProvider? chatHistoryProvider = this._agentOptions?.ChatHistoryProviderFactory is not null
            ? await this._agentOptions.ChatHistoryProviderFactory.Invoke(new() { SerializedState = default, JsonSerializerOptions = null }, cancellationToken).ConfigureAwait(false)
            : null;

        AIContextProvider? contextProvider = this._agentOptions?.AIContextProviderFactory is not null
            ? await this._agentOptions.AIContextProviderFactory.Invoke(new() { SerializedState = default, JsonSerializerOptions = null }, cancellationToken).ConfigureAwait(false)
            : null;

        return new ChatClientAgentSession
        {
            ChatHistoryProvider = chatHistoryProvider,
            AIContextProvider = contextProvider
        };
    }

    /// <summary>
    /// Creates a new agent session instance using an existing conversation identifier to continue that conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of an existing conversation to continue.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A value task representing the asynchronous operation. The task result contains a new <see cref="AgentSession"/> instance configured to work with the specified conversation.
    /// </returns>
    /// <remarks>
    /// <para>
    /// This method creates an <see cref="AgentSession"/> that relies on server-side chat history storage, where the chat history
    /// is maintained by the underlying AI service rather than by a local <see cref="ChatHistoryProvider"/>.
    /// </para>
    /// <para>
    /// Agent threads created with this method will only work with <see cref="ChatClientAgent"/>
    /// instances that support server-side conversation storage through their underlying <see cref="IChatClient"/>.
    /// </para>
    /// </remarks>
    public async ValueTask<AgentSession> CreateSessionAsync(string conversationId, CancellationToken cancellationToken = default)
    {
        AIContextProvider? contextProvider = this._agentOptions?.AIContextProviderFactory is not null
            ? await this._agentOptions.AIContextProviderFactory.Invoke(new() { SerializedState = default, JsonSerializerOptions = null }, cancellationToken).ConfigureAwait(false)
            : null;

        return new ChatClientAgentSession()
        {
            ConversationId = conversationId,
            AIContextProvider = contextProvider
        };
    }

    /// <summary>
    /// Creates a new agent session instance using an existing <see cref="ChatHistoryProvider"/> to continue a conversation.
    /// </summary>
    /// <param name="chatHistoryProvider">The <see cref="ChatHistoryProvider"/> instance to use for managing the conversation's message history.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>
    /// A value task representing the asynchronous operation. The task result contains a new <see cref="AgentSession"/> instance configured to work with the provided <paramref name="chatHistoryProvider"/>.
    /// </returns>
    /// <remarks>
    /// <para>
    /// This method creates threads that do not support server-side conversation storage.
    /// Some AI services require server-side conversation storage to function properly, and creating a session
    /// with a <see cref="ChatHistoryProvider"/> may not be compatible with these services.
    /// </para>
    /// <para>
    /// Where a service requires server-side conversation storage, use <see cref="CreateSessionAsync(string, CancellationToken)"/>.
    /// </para>
    /// <para>
    /// If the agent detects, during the first run, that the underlying AI service requires server-side conversation storage,
    /// the session will throw an exception to indicate that it cannot continue using the provided <see cref="ChatHistoryProvider"/>.
    /// </para>
    /// </remarks>
    public async ValueTask<AgentSession> CreateSessionAsync(ChatHistoryProvider chatHistoryProvider, CancellationToken cancellationToken = default)
    {
        AIContextProvider? contextProvider = this._agentOptions?.AIContextProviderFactory is not null
            ? await this._agentOptions.AIContextProviderFactory.Invoke(new() { SerializedState = default, JsonSerializerOptions = null }, cancellationToken).ConfigureAwait(false)
            : null;

        return new ChatClientAgentSession()
        {
            ChatHistoryProvider = Throw.IfNull(chatHistoryProvider),
            AIContextProvider = contextProvider
        };
    }

    /// <inheritdoc/>
    protected override JsonElement SerializeSessionCore(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        _ = Throw.IfNull(session);

        if (session is not ChatClientAgentSession typedSession)
        {
            throw new InvalidOperationException("The provided session is not compatible with the agent. Only sessions created by the agent can be serialized.");
        }

        return typedSession.Serialize(jsonSerializerOptions);
    }

    /// <inheritdoc/>
    protected override async ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        Func<JsonElement, JsonSerializerOptions?, CancellationToken, ValueTask<ChatHistoryProvider>>? chatHistoryProviderFactory = this._agentOptions?.ChatHistoryProviderFactory is null ?
            null :
            (jse, jso, ct) => this._agentOptions.ChatHistoryProviderFactory.Invoke(new() { SerializedState = jse, JsonSerializerOptions = jso }, ct);

        Func<JsonElement, JsonSerializerOptions?, CancellationToken, ValueTask<AIContextProvider>>? aiContextProviderFactory = this._agentOptions?.AIContextProviderFactory is null ?
            null :
            (jse, jso, ct) => this._agentOptions.AIContextProviderFactory.Invoke(new() { SerializedState = jse, JsonSerializerOptions = jso }, ct);

        return await ChatClientAgentSession.DeserializeAsync(
            serializedState,
            jsonSerializerOptions,
            chatHistoryProviderFactory,
            aiContextProviderFactory,
            cancellationToken).ConfigureAwait(false);
    }

    #region Private

    private async Task<TAgentResponse> RunCoreAsync<TAgentResponse, TChatClientResponse>(
        Func<IChatClient, List<ChatMessage>, ChatOptions?, CancellationToken, Task<TChatClientResponse>> chatClientRunFunc,
        Func<TChatClientResponse, TAgentResponse> agentResponseFactoryFunc,
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        where TAgentResponse : AgentResponse
        where TChatClientResponse : ChatResponse
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        (ChatClientAgentSession safeSession,
         ChatOptions? chatOptions,
         List<ChatMessage> inputMessagesForProviders,
         List<ChatMessage> inputMessagesForChatClient,
         ChatClientAgentContinuationToken? _) =
            await this.PrepareSessionAndMessagesAsync(session, inputMessages, options, cancellationToken).ConfigureAwait(false);

        var chatClient = this.ChatClient;

        chatClient = ApplyRunOptionsTransformations(options, chatClient);

        var loggingAgentName = this.GetLoggingAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunAsync), this.Id, loggingAgentName, this._chatClientType);

        // Call the IChatClient and notify the AIContextProvider of any failures.
        TChatClientResponse chatResponse;
        try
        {
            chatResponse = await chatClientRunFunc.Invoke(chatClient, inputMessagesForChatClient, chatOptions, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await this.NotifyChatHistoryProviderOfFailureAsync(safeSession, ex, inputMessagesForProviders, chatOptions, cancellationToken).ConfigureAwait(false);
            await this.NotifyAIContextProviderOfFailureAsync(safeSession, ex, inputMessagesForProviders, cancellationToken).ConfigureAwait(false);
            throw;
        }

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, loggingAgentName, this._chatClientType, inputMessages.Count);

        // We can derive the type of supported session from whether we have a conversation id,
        // so let's update it and set the conversation id for the service session case.
        await this.UpdateSessionWithTypeAndConversationIdAsync(safeSession, chatResponse.ConversationId, cancellationToken).ConfigureAwait(false);

        // Ensure that the author name is set for each message in the response.
        foreach (ChatMessage chatResponseMessage in chatResponse.Messages)
        {
            chatResponseMessage.AuthorName ??= this.Name;
        }

        // Only notify the session of new messages if the chatResponse was successful to avoid inconsistent message state in the session.
        await this.NotifyChatHistoryProviderOfNewMessagesAsync(safeSession, inputMessagesForProviders, chatResponse.Messages, chatOptions, cancellationToken).ConfigureAwait(false);

        // Notify the AIContextProvider of all new messages.
        await this.NotifyAIContextProviderOfSuccessAsync(safeSession, inputMessagesForProviders, chatResponse.Messages, cancellationToken).ConfigureAwait(false);

        var agentResponse = agentResponseFactoryFunc(chatResponse);

        agentResponse.AgentId = this.Id;

        return agentResponse;
    }

    /// <summary>
    /// Notify the <see cref="AIContextProvider"/> when an agent run succeeded, if there is an <see cref="AIContextProvider"/>.
    /// </summary>
    private async Task NotifyAIContextProviderOfSuccessAsync(
        ChatClientAgentSession session,
        IEnumerable<ChatMessage> inputMessages,
        IEnumerable<ChatMessage> responseMessages,
        CancellationToken cancellationToken)
    {
        if (session.AIContextProvider is not null)
        {
            await session.AIContextProvider.InvokedAsync(new(this, session, inputMessages) { ResponseMessages = responseMessages },
                cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Notify the <see cref="AIContextProvider"/> of any failure during an agent run, if there is an <see cref="AIContextProvider"/>.
    /// </summary>
    private async Task NotifyAIContextProviderOfFailureAsync(
        ChatClientAgentSession session,
        Exception ex,
        IEnumerable<ChatMessage> inputMessages,
        CancellationToken cancellationToken)
    {
        if (session.AIContextProvider is not null)
        {
            await session.AIContextProvider.InvokedAsync(new(this, session, inputMessages) { InvokeException = ex },
                cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Configures and returns chat options by merging the provided run options with the agent's default chat options.
    /// </summary>
    /// <remarks>This method prioritizes the chat options provided in <paramref name="runOptions"/> over the
    /// agent's default chat options. Any unset properties in the run options will be filled using the agent's chat
    /// options. If both are <see langword="null"/>, the method returns <see langword="null"/>.</remarks>
    /// <param name="runOptions">Optional run options that may include specific chat configuration settings.</param>
    /// <returns>A <see cref="ChatOptions"/> object representing the merged chat configuration, or <see langword="null"/> if
    /// neither the run options nor the agent's chat options are available.</returns>
    private (ChatOptions?, ChatClientAgentContinuationToken?) CreateConfiguredChatOptions(AgentRunOptions? runOptions)
    {
        ChatOptions? requestChatOptions = (runOptions as ChatClientAgentRunOptions)?.ChatOptions?.Clone();

        // If no agent chat options were provided, return the request chat options with just agent run options overrides.
        if (this._agentOptions?.ChatOptions is null)
        {
            return ApplyAgentRunOptionsOverrides(requestChatOptions, runOptions);
        }

        // If no request chat options were provided, use the agent's chat options clone with agent run options overrides.
        if (requestChatOptions is null)
        {
            return ApplyAgentRunOptionsOverrides(this._agentOptions?.ChatOptions.Clone(), runOptions);
        }

        // If both are present, we need to merge them.
        // The merge strategy will prioritize the request options over the agent options,
        // and will fill the blanks with agent options where the request options were not set.
        requestChatOptions.AllowMultipleToolCalls ??= this._agentOptions.ChatOptions.AllowMultipleToolCalls;
        requestChatOptions.ConversationId ??= this._agentOptions.ChatOptions.ConversationId;
        requestChatOptions.FrequencyPenalty ??= this._agentOptions.ChatOptions.FrequencyPenalty;
        requestChatOptions.MaxOutputTokens ??= this._agentOptions.ChatOptions.MaxOutputTokens;
        requestChatOptions.ModelId ??= this._agentOptions.ChatOptions.ModelId;
        requestChatOptions.PresencePenalty ??= this._agentOptions.ChatOptions.PresencePenalty;
        requestChatOptions.ResponseFormat ??= this._agentOptions.ChatOptions.ResponseFormat;
        requestChatOptions.Seed ??= this._agentOptions.ChatOptions.Seed;
        requestChatOptions.Temperature ??= this._agentOptions.ChatOptions.Temperature;
        requestChatOptions.TopP ??= this._agentOptions.ChatOptions.TopP;
        requestChatOptions.TopK ??= this._agentOptions.ChatOptions.TopK;
        requestChatOptions.ToolMode ??= this._agentOptions.ChatOptions.ToolMode;

        // Merge instructions by concatenating them if both are present.
        requestChatOptions.Instructions = !string.IsNullOrWhiteSpace(requestChatOptions.Instructions) && !string.IsNullOrWhiteSpace(this.Instructions)
            ? $"{this.Instructions}\n{requestChatOptions.Instructions}"
            : (!string.IsNullOrWhiteSpace(requestChatOptions.Instructions)
            ? requestChatOptions.Instructions
            : this.Instructions);

        // Merge only the additional properties from the agent if they are not already set in the request options.
        if (requestChatOptions.AdditionalProperties is not null && this._agentOptions.ChatOptions.AdditionalProperties is not null)
        {
            foreach (var kvp in this._agentOptions.ChatOptions.AdditionalProperties)
            {
                _ = requestChatOptions.AdditionalProperties.TryAdd(kvp.Key, kvp.Value);
            }
        }
        else
        {
            requestChatOptions.AdditionalProperties ??= this._agentOptions.ChatOptions.AdditionalProperties?.Clone();
        }

        // Chain the raw representation factory from the request options with the agent's factory if available.
        if (this._agentOptions.ChatOptions.RawRepresentationFactory is { } agentFactory)
        {
            requestChatOptions.RawRepresentationFactory = requestChatOptions.RawRepresentationFactory is { } requestFactory
                ? chatClient => requestFactory(chatClient) ?? agentFactory(chatClient)
                : agentFactory;
        }

        // We concatenate the request stop sequences with the agent's stop sequences when available.
        if (this._agentOptions.ChatOptions.StopSequences is { Count: not 0 })
        {
            if (requestChatOptions.StopSequences is null || requestChatOptions.StopSequences.Count == 0)
            {
                // If the request stop sequences are not set or empty, we use the agent's stop sequences directly.
                requestChatOptions.StopSequences = [.. this._agentOptions.ChatOptions.StopSequences];
            }
            else if (requestChatOptions.StopSequences is List<string> requestStopSequences)
            {
                // If the request stop sequences are set, we concatenate them with the agent's stop sequences.
                requestStopSequences.AddRange(this._agentOptions.ChatOptions.StopSequences);
            }
            else
            {
                // If both agent's and request's stop sequences are set, we concatenate them.
                foreach (string stopSequence in this._agentOptions.ChatOptions.StopSequences)
                {
                    requestChatOptions.StopSequences.Add(stopSequence);
                }
            }
        }

        // We concatenate the request tools with the agent's tools when available.
        if (this._agentOptions.ChatOptions.Tools is { Count: not 0 })
        {
            if (requestChatOptions.Tools is not { Count: > 0 })
            {
                // If the request tools are not set or empty, we use the agent's tools.
                requestChatOptions.Tools = [.. this._agentOptions.ChatOptions.Tools];
            }
            else
            {
                if (requestChatOptions.Tools is List<AITool> requestTools)
                {
                    // If the request tools are set, we concatenate them with the agent's tools.
                    requestTools.AddRange(this._agentOptions.ChatOptions.Tools);
                }
                else
                {
                    // If the both agent's and request's tools are set, we concatenate all tools.
                    foreach (var tool in this._agentOptions.ChatOptions.Tools)
                    {
                        requestChatOptions.Tools.Add(tool);
                    }
                }
            }
        }

        return ApplyAgentRunOptionsOverrides(requestChatOptions, runOptions);

        static (ChatOptions?, ChatClientAgentContinuationToken?) ApplyAgentRunOptionsOverrides(ChatOptions? chatOptions, AgentRunOptions? agentRunOptions)
        {
            if (agentRunOptions?.AllowBackgroundResponses is not null)
            {
                chatOptions ??= new ChatOptions();
                chatOptions.AllowBackgroundResponses = agentRunOptions.AllowBackgroundResponses;
            }

            ChatClientAgentContinuationToken? agentContinuationToken = null;

            if ((agentRunOptions?.ContinuationToken ?? chatOptions?.ContinuationToken) is { } continuationToken)
            {
                agentContinuationToken = ChatClientAgentContinuationToken.FromToken(continuationToken);
                chatOptions ??= new ChatOptions();
                chatOptions.ContinuationToken = agentContinuationToken!.InnerToken;
            }

            // Add/Replace any additional properties from the AgentRunOptions, since they should always take precedence.
            if (agentRunOptions?.AdditionalProperties is { Count: > 0 })
            {
                chatOptions ??= new ChatOptions();
                chatOptions.AdditionalProperties ??= new();
                foreach (var kvp in agentRunOptions.AdditionalProperties)
                {
                    chatOptions.AdditionalProperties[kvp.Key] = kvp.Value;
                }
            }

            return (chatOptions, agentContinuationToken);
        }
    }

    /// <summary>
    /// Prepares the session, chat options, and messages for agent execution.
    /// </summary>
    /// <param name="session">The conversation session to use or create.</param>
    /// <param name="inputMessages">The input messages to use.</param>
    /// <param name="runOptions">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A tuple containing the session, chat options, messages and continuation token.</returns>
    private async Task
        <(
            ChatClientAgentSession AgentSession,
            ChatOptions? ChatOptions,
            List<ChatMessage> inputMessagesForProviders,
            List<ChatMessage> InputMessagesForChatClient,
            ChatClientAgentContinuationToken? ContinuationToken
        )> PrepareSessionAndMessagesAsync(
        AgentSession? session,
        IEnumerable<ChatMessage> inputMessages,
        AgentRunOptions? runOptions,
        CancellationToken cancellationToken)
    {
        (ChatOptions? chatOptions, ChatClientAgentContinuationToken? continuationToken) = this.CreateConfiguredChatOptions(runOptions);

        // Supplying a session for background responses is required to prevent inconsistent experience
        // for callers if they forget to provide the session for initial or follow-up runs.
        if (chatOptions?.AllowBackgroundResponses is true && session is null)
        {
            throw new InvalidOperationException("A session must be provided when continuing a background response with a continuation token.");
        }

        session ??= await this.CreateSessionAsync(cancellationToken).ConfigureAwait(false);
        if (session is not ChatClientAgentSession typedSession)
        {
            throw new InvalidOperationException("The provided session is not compatible with the agent. Only sessions created by the agent can be used.");
        }

        // Supplying messages when continuing a background response is not allowed.
        if (chatOptions?.ContinuationToken is not null && inputMessages.Any())
        {
            throw new InvalidOperationException("Input messages are not allowed when continuing a background response using a continuation token.");
        }

        List<ChatMessage> inputMessagesForProviders = [];
        List<ChatMessage> inputMessagesForChatClient = [];

        // Populate the session messages only if we are not continuing an existing response as it's not allowed
        if (chatOptions?.ContinuationToken is null)
        {
            ChatHistoryProvider? chatHistoryProvider = ResolveChatHistoryProvider(typedSession, chatOptions);

            // Add any existing messages from the session to the messages to be sent to the chat client.
            if (chatHistoryProvider is not null)
            {
                var invokingContext = new ChatHistoryProvider.InvokingContext(this, typedSession, inputMessages);
                var providerMessages = await chatHistoryProvider.InvokingAsync(invokingContext, cancellationToken).ConfigureAwait(false);
                inputMessagesForChatClient.AddRange(providerMessages);
            }

            // Add the input messages before getting context from AIContextProvider.
            inputMessagesForProviders.AddRange(inputMessages);
            inputMessagesForChatClient.AddRange(inputMessages);

            // If we have an AIContextProvider, we should get context from it, and update our
            // messages and options with the additional context.
            if (typedSession.AIContextProvider is not null)
            {
                var invokingContext = new AIContextProvider.InvokingContext(this, typedSession, inputMessages);
                var aiContext = await typedSession.AIContextProvider.InvokingAsync(invokingContext, cancellationToken).ConfigureAwait(false);
                if (aiContext.Messages is { Count: > 0 })
                {
                    inputMessagesForProviders.AddRange(aiContext.Messages);
                    inputMessagesForChatClient.AddRange(aiContext.Messages);
                }

                if (aiContext.Tools is { Count: > 0 })
                {
                    chatOptions ??= new();
                    chatOptions.Tools ??= [];
                    foreach (AITool tool in aiContext.Tools)
                    {
                        chatOptions.Tools.Add(tool);
                    }
                }

                if (aiContext.Instructions is not null)
                {
                    chatOptions ??= new();
                    chatOptions.Instructions = string.IsNullOrWhiteSpace(chatOptions.Instructions) ? aiContext.Instructions : $"{chatOptions.Instructions}\n{aiContext.Instructions}";
                }
            }
        }

        // If a user provided two different session ids, via the session object and options, we should throw
        // since we don't know which one to use.
        if (!string.IsNullOrWhiteSpace(typedSession.ConversationId) && !string.IsNullOrWhiteSpace(chatOptions?.ConversationId) && typedSession.ConversationId != chatOptions!.ConversationId)
        {
            throw new InvalidOperationException(
                $"""
                The {nameof(chatOptions.ConversationId)} provided via {nameof(this.ChatOptions)} is different to the id of the provided {nameof(AgentSession)}.
                Only one id can be used for a run.
                """);
        }

        // Only create or update ChatOptions if we have an id on the session and we don't have the same one already in ChatOptions.
        if (!string.IsNullOrWhiteSpace(typedSession.ConversationId) && typedSession.ConversationId != chatOptions?.ConversationId)
        {
            chatOptions ??= new();
            chatOptions.ConversationId = typedSession.ConversationId;
        }

        return (typedSession, chatOptions, inputMessagesForProviders, inputMessagesForChatClient, continuationToken);
    }

    private async Task UpdateSessionWithTypeAndConversationIdAsync(ChatClientAgentSession session, string? responseConversationId, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(responseConversationId) && !string.IsNullOrWhiteSpace(session.ConversationId))
        {
            // We were passed an AgentSession that has an id for service managed chat history, but we got no conversation id back from the chat client,
            // meaning the service doesn't support service managed chat history, so the session cannot be used with this service.
            throw new InvalidOperationException("Service did not return a valid conversation id when using an AgentSession with service managed chat history.");
        }

        if (!string.IsNullOrWhiteSpace(responseConversationId))
        {
            // If we got a conversation id back from the chat client, it means that the service supports server side session storage
            // so we should update the session with the new id.
            session.ConversationId = responseConversationId;
        }
        else
        {
            // If the service doesn't use service side chat history storage (i.e. we got no id back from invocation), and
            // the session has no ChatHistoryProvider yet, we should update the session with the custom ChatHistoryProvider or
            // default InMemoryChatHistoryProvider so that it has somewhere to store the chat history.
            session.ChatHistoryProvider ??= this._agentOptions?.ChatHistoryProviderFactory is not null
                ? await this._agentOptions.ChatHistoryProviderFactory.Invoke(new() { SerializedState = default, JsonSerializerOptions = null }, cancellationToken).ConfigureAwait(false)
                : new InMemoryChatHistoryProvider();
        }
    }

    private Task NotifyChatHistoryProviderOfFailureAsync(
        ChatClientAgentSession session,
        Exception ex,
        IEnumerable<ChatMessage> requestMessages,
        ChatOptions? chatOptions,
        CancellationToken cancellationToken)
    {
        ChatHistoryProvider? provider = ResolveChatHistoryProvider(session, chatOptions);

        // Only notify the provider if we have one.
        // If we don't have one, it means that the chat history is service managed and the underlying service is responsible for storing messages.
        if (provider is not null)
        {
            var invokedContext = new ChatHistoryProvider.InvokedContext(this, session, requestMessages)
            {
                InvokeException = ex
            };

            return provider.InvokedAsync(invokedContext, cancellationToken).AsTask();
        }

        return Task.CompletedTask;
    }

    private Task NotifyChatHistoryProviderOfNewMessagesAsync(
        ChatClientAgentSession session,
        IEnumerable<ChatMessage> requestMessages,
        IEnumerable<ChatMessage> responseMessages,
        ChatOptions? chatOptions,
        CancellationToken cancellationToken)
    {
        ChatHistoryProvider? provider = ResolveChatHistoryProvider(session, chatOptions);

        // Only notify the provider if we have one.
        // If we don't have one, it means that the chat history is service managed and the underlying service is responsible for storing messages.
        if (provider is not null)
        {
            var invokedContext = new ChatHistoryProvider.InvokedContext(this, session, requestMessages)
            {
                ResponseMessages = responseMessages
            };
            return provider.InvokedAsync(invokedContext, cancellationToken).AsTask();
        }

        return Task.CompletedTask;
    }

    private static ChatHistoryProvider? ResolveChatHistoryProvider(ChatClientAgentSession session, ChatOptions? chatOptions)
    {
        ChatHistoryProvider? provider = session.ChatHistoryProvider;

        // If someone provided an override ChatHistoryProvider via AdditionalProperties, we should use that instead of the one on the session.
        if (chatOptions?.AdditionalProperties?.TryGetValue(out ChatHistoryProvider? overrideProvider) is true)
        {
            provider = overrideProvider;
        }

        return provider;
    }

    private static ChatClientAgentContinuationToken? WrapContinuationToken(ResponseContinuationToken? continuationToken, IEnumerable<ChatMessage>? inputMessages = null, List<ChatResponseUpdate>? responseUpdates = null)
    {
        if (continuationToken is null)
        {
            return null;
        }

        return new(continuationToken)
        {
            // Save input messages to the continuation token so they can be added to the session and
            // provided to the context provider in the last successful streaming resumption run.
            // That's necessary for scenarios where initial streaming run is interrupted and streaming is resumed later.
            InputMessages = inputMessages?.Any() is true ? inputMessages : null,

            // Save all updates received so far to the continuation token so they can be provided to the
            // message store and context provider in the last successful streaming resumption run.
            // That's necessary for scenarios where a streaming run is interrupted after some updates were received.
            ResponseUpdates = responseUpdates?.Count > 0 ? responseUpdates : null
        };
    }

    private static IEnumerable<ChatMessage> GetInputMessages(IReadOnlyCollection<ChatMessage> inputMessages, ChatClientAgentContinuationToken? token)
    {
        // First, use input messages if provided.
        if (inputMessages.Count > 0)
        {
            return inputMessages;
        }

        // Fallback to messages saved in the continuation token if available.
        return token?.InputMessages ?? [];
    }

    private static List<ChatResponseUpdate> GetResponseUpdates(ChatClientAgentContinuationToken? token)
    {
        // Restore any previously received updates from the continuation token.
        return token?.ResponseUpdates?.ToList() ?? [];
    }

    private string GetLoggingAgentName() => this.Name ?? "UnnamedAgent";
    #endregion
}
