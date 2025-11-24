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
                  Name = name,
                  Description = description,
                  Instructions = instructions,
                  ChatOptions = tools is null ? null : new ChatOptions
                  {
                      Tools = tools,
                  }
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
    /// message store factories, context provider factories, and other advanced configurations.
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
    public override string Id => this._agentOptions?.Id ?? base.Id;

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
    public string? Instructions => this._agentOptions?.Instructions;

    /// <summary>
    /// Gets of the default <see cref="ChatOptions"/> used by the agent.
    /// </summary>
    internal ChatOptions? ChatOptions => this._agentOptions?.ChatOptions;

    /// <inheritdoc/>
    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        static Task<ChatResponse> GetResponseAsync(IChatClient chatClient, List<ChatMessage> threadMessages, ChatOptions? chatOptions, CancellationToken ct)
        {
            return chatClient.GetResponseAsync(threadMessages, chatOptions, ct);
        }

        static AgentRunResponse CreateResponse(ChatResponse chatResponse)
        {
            return new AgentRunResponse(chatResponse);
        }

        return this.RunCoreAsync(GetResponseAsync, CreateResponse, messages, thread, options, cancellationToken);
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
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        (ChatClientAgentThread safeThread, ChatOptions? chatOptions, List<ChatMessage> inputMessagesForChatClient, IList<ChatMessage>? aiContextProviderMessages) =
            await this.PrepareThreadAndMessagesAsync(thread, inputMessages, options, cancellationToken).ConfigureAwait(false);

        var chatClient = this.ChatClient;

        chatClient = ApplyRunOptionsTransformations(options, chatClient);

        var loggingAgentName = this.GetLoggingAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunStreamingAsync), this.Id, loggingAgentName, this._chatClientType);

        List<ChatResponseUpdate> responseUpdates = [];

        IAsyncEnumerator<ChatResponseUpdate> responseUpdatesEnumerator;

        try
        {
            // Using the enumerator to ensure we consider the case where no updates are returned for notification.
            responseUpdatesEnumerator = chatClient.GetStreamingResponseAsync(inputMessagesForChatClient, chatOptions, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, aiContextProviderMessages, cancellationToken).ConfigureAwait(false);
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
            await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, aiContextProviderMessages, cancellationToken).ConfigureAwait(false);
            throw;
        }

        while (hasUpdates)
        {
            var update = responseUpdatesEnumerator.Current;
            if (update is not null)
            {
                update.AuthorName ??= this.Name;

                responseUpdates.Add(update);
                yield return new(update) { AgentId = this.Id };
            }

            try
            {
                hasUpdates = await responseUpdatesEnumerator.MoveNextAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, aiContextProviderMessages, cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        var chatResponse = responseUpdates.ToChatResponse();

        // We can derive the type of supported thread from whether we have a conversation id,
        // so let's update it and set the conversation id for the service thread case.
        this.UpdateThreadWithTypeAndConversationId(safeThread, chatResponse.ConversationId);

        // To avoid inconsistent state we only notify the thread of the input messages if no error occurs after the initial request.
        await NotifyThreadOfNewMessagesAsync(safeThread, inputMessages.Concat(aiContextProviderMessages ?? []).Concat(chatResponse.Messages), cancellationToken).ConfigureAwait(false);

        // Notify the AIContextProvider of all new messages.
        await NotifyAIContextProviderOfSuccessAsync(safeThread, inputMessages, aiContextProviderMessages, chatResponse.Messages, cancellationToken).ConfigureAwait(false);
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
    public override AgentThread GetNewThread()
        => new ChatClientAgentThread
        {
            AIContextProvider = this._agentOptions?.AIContextProviderFactory?.Invoke(new() { SerializedState = default, JsonSerializerOptions = null })
        };

    /// <summary>
    /// Creates a new agent thread instance using an existing conversation identifier to continue that conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of an existing conversation to continue.</param>
    /// <returns>
    /// A new <see cref="AgentThread"/> instance configured to work with the specified conversation.
    /// </returns>
    /// <remarks>
    /// <para>
    /// This method creates threads that rely on server-side conversation storage, where the chat history
    /// is maintained by the underlying AI service rather than in local message stores.
    /// </para>
    /// <para>
    /// Agent threads created with this method will only work with <see cref="ChatClientAgent"/>
    /// instances that support server-side conversation storage through their underlying <see cref="IChatClient"/>.
    /// </para>
    /// </remarks>
    public AgentThread GetNewThread(string conversationId)
        => new ChatClientAgentThread()
        {
            ConversationId = conversationId,
            AIContextProvider = this._agentOptions?.AIContextProviderFactory?.Invoke(new() { SerializedState = default, JsonSerializerOptions = null })
        };

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        Func<JsonElement, JsonSerializerOptions?, ChatMessageStore>? chatMessageStoreFactory = this._agentOptions?.ChatMessageStoreFactory is null ?
            null :
            (jse, jso) => this._agentOptions.ChatMessageStoreFactory.Invoke(new() { SerializedState = jse, JsonSerializerOptions = jso });

        Func<JsonElement, JsonSerializerOptions?, AIContextProvider>? aiContextProviderFactory = this._agentOptions?.AIContextProviderFactory is null ?
            null :
            (jse, jso) => this._agentOptions.AIContextProviderFactory.Invoke(new() { SerializedState = jse, JsonSerializerOptions = jso });

        return new ChatClientAgentThread(
            serializedThread,
            jsonSerializerOptions,
            chatMessageStoreFactory,
            aiContextProviderFactory);
    }

    #region Private

    private async Task<TAgentRunResponse> RunCoreAsync<TAgentRunResponse, TChatClientResponse>(
        Func<IChatClient, List<ChatMessage>, ChatOptions?, CancellationToken, Task<TChatClientResponse>> chatClientRunFunc,
        Func<TChatClientResponse, TAgentRunResponse> agentResponseFactoryFunc,
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
        where TAgentRunResponse : AgentRunResponse
        where TChatClientResponse : ChatResponse
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        (ChatClientAgentThread safeThread, ChatOptions? chatOptions, List<ChatMessage> inputMessagesForChatClient, IList<ChatMessage>? aiContextProviderMessages) =
            await this.PrepareThreadAndMessagesAsync(thread, inputMessages, options, cancellationToken).ConfigureAwait(false);

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
            await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, aiContextProviderMessages, cancellationToken).ConfigureAwait(false);
            throw;
        }

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, loggingAgentName, this._chatClientType, inputMessages.Count);

        // We can derive the type of supported thread from whether we have a conversation id,
        // so let's update it and set the conversation id for the service thread case.
        this.UpdateThreadWithTypeAndConversationId(safeThread, chatResponse.ConversationId);

        // Ensure that the author name is set for each message in the response.
        foreach (ChatMessage chatResponseMessage in chatResponse.Messages)
        {
            chatResponseMessage.AuthorName ??= this.Name;
        }

        // Only notify the thread of new messages if the chatResponse was successful to avoid inconsistent message state in the thread.
        await NotifyThreadOfNewMessagesAsync(safeThread, inputMessages.Concat(aiContextProviderMessages ?? []).Concat(chatResponse.Messages), cancellationToken).ConfigureAwait(false);

        // Notify the AIContextProvider of all new messages.
        await NotifyAIContextProviderOfSuccessAsync(safeThread, inputMessages, aiContextProviderMessages, chatResponse.Messages, cancellationToken).ConfigureAwait(false);

        var agentResponse = agentResponseFactoryFunc(chatResponse);

        agentResponse.AgentId = this.Id;

        return agentResponse;
    }

    /// <summary>
    /// Notify the <see cref="AIContextProvider"/> when an agent run succeeded, if there is an <see cref="AIContextProvider"/>.
    /// </summary>
    private static async Task NotifyAIContextProviderOfSuccessAsync(
        ChatClientAgentThread thread,
        IEnumerable<ChatMessage> inputMessages,
        IList<ChatMessage>? aiContextProviderMessages,
        IEnumerable<ChatMessage> responseMessages,
        CancellationToken cancellationToken)
    {
        if (thread.AIContextProvider is not null)
        {
            await thread.AIContextProvider.InvokedAsync(new(inputMessages, aiContextProviderMessages) { ResponseMessages = responseMessages },
                cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Notify the <see cref="AIContextProvider"/> of any failure during an agent run, if there is an <see cref="AIContextProvider"/>.
    /// </summary>
    private static async Task NotifyAIContextProviderOfFailureAsync(
        ChatClientAgentThread thread,
        Exception ex,
        IEnumerable<ChatMessage> inputMessages,
        IList<ChatMessage>? aiContextProviderMessages,
        CancellationToken cancellationToken)
    {
        if (thread.AIContextProvider is not null)
        {
            await thread.AIContextProvider.InvokedAsync(new(inputMessages, aiContextProviderMessages) { InvokeException = ex },
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
    private ChatOptions? CreateConfiguredChatOptions(AgentRunOptions? runOptions)
    {
        ChatOptions? requestChatOptions = (runOptions as ChatClientAgentRunOptions)?.ChatOptions?.Clone();

        // If no agent chat options were provided, return the request chat options as is.
        if (this._agentOptions?.ChatOptions is null)
        {
            return ApplyBackgroundResponsesProperties(requestChatOptions, runOptions);
        }

        // If no request chat options were provided, use the agent's chat options clone.
        if (requestChatOptions is null)
        {
            return ApplyBackgroundResponsesProperties(this._agentOptions?.ChatOptions.Clone(), runOptions);
        }

        // If both are present, we need to merge them.
        // The merge strategy will prioritize the request options over the agent options,
        // and will fill the blanks with agent options where the request options were not set.
        requestChatOptions.AllowMultipleToolCalls ??= this._agentOptions.ChatOptions.AllowMultipleToolCalls;
        requestChatOptions.ConversationId ??= this._agentOptions.ChatOptions.ConversationId;
        requestChatOptions.FrequencyPenalty ??= this._agentOptions.ChatOptions.FrequencyPenalty;
        requestChatOptions.Instructions ??= this._agentOptions.ChatOptions.Instructions;
        requestChatOptions.MaxOutputTokens ??= this._agentOptions.ChatOptions.MaxOutputTokens;
        requestChatOptions.ModelId ??= this._agentOptions.ChatOptions.ModelId;
        requestChatOptions.PresencePenalty ??= this._agentOptions.ChatOptions.PresencePenalty;
        requestChatOptions.ResponseFormat ??= this._agentOptions.ChatOptions.ResponseFormat;
        requestChatOptions.Seed ??= this._agentOptions.ChatOptions.Seed;
        requestChatOptions.Temperature ??= this._agentOptions.ChatOptions.Temperature;
        requestChatOptions.TopP ??= this._agentOptions.ChatOptions.TopP;
        requestChatOptions.TopK ??= this._agentOptions.ChatOptions.TopK;
        requestChatOptions.ToolMode ??= this._agentOptions.ChatOptions.ToolMode;

        // Merge only the additional properties from the agent if they are not already set in the request options.
        if (requestChatOptions.AdditionalProperties is not null && this._agentOptions.ChatOptions.AdditionalProperties is not null)
        {
            foreach (var propertyKey in this._agentOptions.ChatOptions.AdditionalProperties.Keys)
            {
                _ = requestChatOptions.AdditionalProperties.TryAdd(propertyKey, this._agentOptions.ChatOptions.AdditionalProperties[propertyKey]);
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

        return ApplyBackgroundResponsesProperties(requestChatOptions, runOptions);

        static ChatOptions? ApplyBackgroundResponsesProperties(ChatOptions? chatOptions, AgentRunOptions? agentRunOptions)
        {
            // If any of the background response properties are set in the run options, we should apply both to the chat options.
            if (agentRunOptions?.AllowBackgroundResponses is not null || agentRunOptions?.ContinuationToken is not null)
            {
                chatOptions ??= new ChatOptions();
                chatOptions.AllowBackgroundResponses = agentRunOptions.AllowBackgroundResponses;
                chatOptions.ContinuationToken = agentRunOptions.ContinuationToken;
            }

            return chatOptions;
        }
    }

    /// <summary>
    /// Prepares the thread, chat options, and messages for agent execution.
    /// </summary>
    /// <param name="thread">The conversation thread to use or create.</param>
    /// <param name="inputMessages">The input messages to use.</param>
    /// <param name="runOptions">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A tuple containing the thread, chat options, and thread messages.</returns>
    private async Task<(ChatClientAgentThread AgentThread, ChatOptions? ChatOptions, List<ChatMessage> InputMessagesForChatClient, IList<ChatMessage>? AIContextProviderMessages)> PrepareThreadAndMessagesAsync(
        AgentThread? thread,
        IEnumerable<ChatMessage> inputMessages,
        AgentRunOptions? runOptions,
        CancellationToken cancellationToken)
    {
        ChatOptions? chatOptions = this.CreateConfiguredChatOptions(runOptions);

        // Supplying a thread for background responses is required to prevent inconsistent experience
        // for callers if they forget to provide the thread for initial or follow-up runs.
        if (chatOptions?.AllowBackgroundResponses is true && thread is null)
        {
            throw new InvalidOperationException("A thread must be provided when continuing a background response with a continuation token.");
        }

        thread ??= this.GetNewThread();
        if (thread is not ChatClientAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        // Supplying messages when continuing a background response is not allowed.
        if (chatOptions?.ContinuationToken is not null && inputMessages.Any())
        {
            throw new InvalidOperationException("Input messages are not allowed when continuing a background response using a continuation token.");
        }
        List<ChatMessage> inputMessagesForChatClient = [];
        IList<ChatMessage>? aiContextProviderMessages = null;

        // Populate the thread messages only if we are not continuing an existing response as it's not allowed
        if (chatOptions?.ContinuationToken is null)
        {
            // Add any existing messages from the thread to the messages to be sent to the chat client.
            if (typedThread.MessageStore is not null)
            {
                inputMessagesForChatClient.AddRange(await typedThread.MessageStore.GetMessagesAsync(cancellationToken).ConfigureAwait(false));
            }

            // If we have an AIContextProvider, we should get context from it, and update our
            // messages and options with the additional context.
            if (typedThread.AIContextProvider is not null)
            {
                var invokingContext = new AIContextProvider.InvokingContext(inputMessages);
                var aiContext = await typedThread.AIContextProvider.InvokingAsync(invokingContext, cancellationToken).ConfigureAwait(false);
                if (aiContext.Messages is { Count: > 0 })
                {
                    inputMessagesForChatClient.AddRange(aiContext.Messages);
                    aiContextProviderMessages = aiContext.Messages;
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

            // Add the input messages to the end of thread messages.
            inputMessagesForChatClient.AddRange(inputMessages);
        }

        // If a user provided two different thread ids, via the thread object and options, we should throw
        // since we don't know which one to use.
        if (!string.IsNullOrWhiteSpace(typedThread.ConversationId) && !string.IsNullOrWhiteSpace(chatOptions?.ConversationId) && typedThread.ConversationId != chatOptions!.ConversationId)
        {
            throw new InvalidOperationException(
                $"""
                The {nameof(chatOptions.ConversationId)} provided via {nameof(this.ChatOptions)} is different to the id of the provided {nameof(AgentThread)}.
                Only one id can be used for a run.
                """);
        }

        if (!string.IsNullOrWhiteSpace(this.Instructions))
        {
            chatOptions ??= new();
            chatOptions.Instructions = string.IsNullOrWhiteSpace(chatOptions.Instructions) ? this.Instructions : $"{this.Instructions}\n{chatOptions.Instructions}";
        }

        // Only create or update ChatOptions if we have an id on the thread and we don't have the same one already in ChatOptions.
        if (!string.IsNullOrWhiteSpace(typedThread.ConversationId) && typedThread.ConversationId != chatOptions?.ConversationId)
        {
            chatOptions ??= new();
            chatOptions.ConversationId = typedThread.ConversationId;
        }

        return (typedThread, chatOptions, inputMessagesForChatClient, aiContextProviderMessages);
    }

    private void UpdateThreadWithTypeAndConversationId(ChatClientAgentThread thread, string? responseConversationId)
    {
        if (string.IsNullOrWhiteSpace(responseConversationId) && !string.IsNullOrWhiteSpace(thread.ConversationId))
        {
            // We were passed a thread that is service managed, but we got no conversation id back from the chat client,
            // meaning the service doesn't support service managed threads, so the thread cannot be used with this service.
            throw new InvalidOperationException("Service did not return a valid conversation id when using a service managed thread.");
        }

        if (!string.IsNullOrWhiteSpace(responseConversationId))
        {
            // If we got a conversation id back from the chat client, it means that the service supports server side thread storage
            // so we should update the thread with the new id.
            thread.ConversationId = responseConversationId;
        }
        else
        {
            // If the service doesn't use service side thread storage (i.e. we got no id back from invocation), and
            // the thread has no MessageStore yet, and we have a custom messages store, we should update the thread
            // with the custom MessageStore so that it has somewhere to store the chat history.
            thread.MessageStore ??= this._agentOptions?.ChatMessageStoreFactory?.Invoke(new() { SerializedState = default, JsonSerializerOptions = null });
        }
    }

    private string GetLoggingAgentName() => this.Name ?? "UnnamedAgent";
    #endregion
}
