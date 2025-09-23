// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

#pragma warning disable S3358 // Ternary operators should not be nested

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an agent that can be invoked using a chat client.
/// </summary>
public sealed class ChatClientAgent : AIAgent
{
    private readonly ChatClientAgentOptions? _agentOptions;
    private readonly AIAgentMetadata _agentMetadata;
    private readonly ILogger _logger;
    private readonly Type _chatClientType;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for invoking the agent.</param>
    /// <param name="instructions">Optional instructions for the agent.</param>
    /// <param name="name">Optional name for the agent.</param>
    /// <param name="description">Optional description for the agent.</param>
    /// <param name="tools">Optional list of tools that the agent can use during invocation.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public ChatClientAgent(IChatClient chatClient, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
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
              loggerFactory)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for invoking the agent.</param>
    /// <param name="options">Full set of options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public ChatClientAgent(IChatClient chatClient, ChatClientAgentOptions? options, ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(chatClient);

        // Options must be cloned since ChatClientAgentOptions is mutable.
        this._agentOptions = options?.Clone();

        this._agentMetadata = new AIAgentMetadata(chatClient.GetService<ChatClientMetadata>()?.ProviderName);

        // Get the type of the chat client before wrapping it as an agent invoking chat client.
        this._chatClientType = chatClient.GetType();

        // If the user has not opted out of using our default decorators, we wrap the chat client.
        this.ChatClient = options?.UseProvidedChatClientAsIs is true ? chatClient : chatClient.AsAgentInvokedChatClient(options);

        this._logger = (loggerFactory ?? chatClient.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance).CreateLogger<ChatClientAgent>();
    }

    /// <summary>
    /// Gets the underlying chat client used by the agent to invoke chat completions.
    /// </summary>
    public IChatClient ChatClient { get; }

    /// <inheritdoc/>
    public override string Id => this._agentOptions?.Id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._agentOptions?.Name;

    /// <inheritdoc/>
    public override string? Description => this._agentOptions?.Description;

    /// <summary>
    /// Gets the instructions for the agent (optional).
    /// </summary>
    public string? Instructions => this._agentOptions?.Instructions;

    /// <summary>
    /// Gets of the default <see cref="ChatOptions"/> used by the agent.
    /// </summary>
    internal ChatOptions? ChatOptions => this._agentOptions?.ChatOptions;

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        (ChatClientAgentThread safeThread, ChatOptions? chatOptions, List<ChatMessage> threadMessages) =
            await this.PrepareThreadAndMessagesAsync(thread, inputMessages, options, cancellationToken).ConfigureAwait(false);

        var agentName = this.GetLoggingAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunAsync), this.Id, agentName, this._chatClientType);

        // Call the IChatClient and notify the AIContextProvider of any failures.
        ChatResponse chatResponse;
        try
        {
            chatResponse = await this.ChatClient.GetResponseAsync(threadMessages, chatOptions, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, cancellationToken).ConfigureAwait(false);
            throw;
        }

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, agentName, this._chatClientType, inputMessages.Count);

        // We can derive the type of supported thread from whether we have a conversation id,
        // so let's update it and set the conversation id for the service thread case.
        this.UpdateThreadWithTypeAndConversationId(safeThread, chatResponse.ConversationId);

        // Ensure that the author name is set for each message in the response.
        foreach (ChatMessage chatResponseMessage in chatResponse.Messages)
        {
            chatResponseMessage.AuthorName ??= agentName;
        }

        // Only notify the thread of new messages if the chatResponse was successful to avoid inconsistent message state in the thread.
        await NotifyThreadOfNewMessagesAsync(safeThread, inputMessages.Concat(chatResponse.Messages), cancellationToken).ConfigureAwait(false);

        // Notify the AIContextProvider of all new messages.
        await NotifyAIContextProviderOfSuccessAsync(safeThread, inputMessages, chatResponse.Messages, cancellationToken).ConfigureAwait(false);

        return new(chatResponse) { AgentId = this.Id };
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages) as IReadOnlyCollection<ChatMessage> ?? messages.ToList();

        (ChatClientAgentThread safeThread, ChatOptions? chatOptions, List<ChatMessage> threadMessages) =
            await this.PrepareThreadAndMessagesAsync(thread, inputMessages, options, cancellationToken).ConfigureAwait(false);

        int messageCount = threadMessages.Count;
        var loggingAgentName = this.GetLoggingAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunStreamingAsync), this.Id, loggingAgentName, this._chatClientType);

        List<ChatResponseUpdate> responseUpdates = [];

        IAsyncEnumerator<ChatResponseUpdate> responseUpdatesEnumerator;

        try
        {
            // Using the enumerator to ensure we consider the case where no updates are returned for notification.
            responseUpdatesEnumerator = this.ChatClient.GetStreamingResponseAsync(threadMessages, chatOptions, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, cancellationToken).ConfigureAwait(false);
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
            await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, cancellationToken).ConfigureAwait(false);
            throw;
        }

        while (hasUpdates)
        {
            var update = responseUpdatesEnumerator.Current;
            if (update is not null)
            {
                responseUpdates.Add(update);
                update.AuthorName ??= this.Name;
                yield return new(update) { AgentId = this.Id };
            }

            try
            {
                hasUpdates = await responseUpdatesEnumerator.MoveNextAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await NotifyAIContextProviderOfFailureAsync(safeThread, ex, inputMessages, cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        var chatResponse = responseUpdates.ToChatResponse();

        // We can derive the type of supported thread from whether we have a conversation id,
        // so let's update it and set the conversation id for the service thread case.
        this.UpdateThreadWithTypeAndConversationId(safeThread, chatResponse.ConversationId);

        // To avoid inconsistent state we only notify the thread of the input messages if no error occurs after the initial request.
        await NotifyThreadOfNewMessagesAsync(safeThread, inputMessages.Concat(chatResponse.Messages), cancellationToken).ConfigureAwait(false);

        // Notify the AIContextProvider of all new messages.
        await NotifyAIContextProviderOfSuccessAsync(safeThread, inputMessages, chatResponse.Messages, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey)
        ?? (serviceType == typeof(AIAgentMetadata) ? this._agentMetadata
        : serviceType == typeof(IChatClient) ? this.ChatClient
        : this.ChatClient.GetService(serviceType, serviceKey));

    /// <inheritdoc/>
    public override AgentThread GetNewThread()
        => new ChatClientAgentThread
        {
            MessageStore = this._agentOptions?.ChatMessageStoreFactory?.Invoke(new() { SerializedState = default, JsonSerializerOptions = null }),
            AIContextProvider = this._agentOptions?.AIContextProviderFactory?.Invoke(new() { SerializedState = default, JsonSerializerOptions = null })
        };

    /// <summary>
    /// Get a new <see cref="AgentThread"/> instance using an existing conversation id, to continue that conversation.
    /// </summary>
    /// <param name="conversationId">The conversation id to continue.</param>
    /// <returns>A new <see cref="AgentThread"/> instance.</returns>
    /// <remarks>
    /// Note that any <see cref="AgentThread"/> created with this method will only work with <see cref="ChatClientAgent"/> instances that support storing
    /// chat history in the underlying service provided by the <see cref="IChatClient"/>.
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
        Func<JsonElement, JsonSerializerOptions?, IChatMessageStore>? chatMessageStoreFactory = this._agentOptions?.ChatMessageStoreFactory is null ?
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

    /// <summary>
    /// Notify the <see cref="AIContextProvider"/> when an agent run succeeded, if there is an <see cref="AIContextProvider"/>.
    /// </summary>
    private static async Task NotifyAIContextProviderOfSuccessAsync(ChatClientAgentThread thread, IEnumerable<ChatMessage> inputMessages, IEnumerable<ChatMessage> responseMessages, CancellationToken cancellationToken)
    {
        if (thread.AIContextProvider is not null)
        {
            await thread.AIContextProvider.InvokedAsync(new(inputMessages) { ResponseMessages = responseMessages },
                cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Notify the <see cref="AIContextProvider"/> of any failure during an agent run, if there is an <see cref="AIContextProvider"/>.
    /// </summary>
    private static async Task NotifyAIContextProviderOfFailureAsync(ChatClientAgentThread thread, Exception ex, IEnumerable<ChatMessage> inputMessages, CancellationToken cancellationToken)
    {
        if (thread.AIContextProvider is not null)
        {
            await thread.AIContextProvider.InvokedAsync(new(inputMessages) { InvokeException = ex },
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
            return requestChatOptions;
        }

        // If no request chat options were provided, use the agent's chat options clone.
        if (requestChatOptions is null)
        {
            return this._agentOptions?.ChatOptions.Clone();
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

        return requestChatOptions;
    }

    /// <summary>
    /// Prepares the thread, chat options, and messages for agent execution.
    /// </summary>
    /// <param name="thread">The conversation thread to use or create.</param>
    /// <param name="inputMessages">The input messages to use.</param>
    /// <param name="runOptions">Optional parameters for agent invocation.</param>
    /// <param name="cancellationToken">The cancellation token.</param>
    /// <returns>A tuple containing the thread, chat options, and thread messages.</returns>
    private async Task<(ChatClientAgentThread AgentThread, ChatOptions? ChatOptions, List<ChatMessage> ThreadMessages)> PrepareThreadAndMessagesAsync(
        AgentThread? thread,
        IEnumerable<ChatMessage> inputMessages,
        AgentRunOptions? runOptions,
        CancellationToken cancellationToken)
    {
        ChatOptions? chatOptions = this.CreateConfiguredChatOptions(runOptions);

        thread ??= this.GetNewThread();
        if (thread is not ChatClientAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        // Add any existing messages from the thread to the messages to be sent to the chat client.
        List<ChatMessage> threadMessages = [];
        if (typedThread.MessageStore is not null)
        {
            threadMessages.AddRange(await typedThread.MessageStore.GetMessagesAsync(cancellationToken).ConfigureAwait(false));
        }

        // If we have an AIContextProvider, we should get context from it, and update our
        // messages and options with the additional context.
        if (typedThread.AIContextProvider is not null)
        {
            var invokingContext = new AIContextProvider.InvokingContext(inputMessages);
            var aiContext = await typedThread.AIContextProvider.InvokingAsync(invokingContext, cancellationToken).ConfigureAwait(false);
            if (aiContext.Messages is { Count: > 0 })
            {
                threadMessages.AddRange(aiContext.Messages);
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
        threadMessages.AddRange(inputMessages);

        // If a user provided two different thread ids, via the thread object and options, we should throw
        // since we don't know which one to use.
        if (!string.IsNullOrWhiteSpace(typedThread.ConversationId) && !string.IsNullOrWhiteSpace(chatOptions?.ConversationId) && typedThread.ConversationId != chatOptions!.ConversationId)
        {
            throw new InvalidOperationException(
                $"""
                The {nameof(chatOptions.ConversationId)} provided via {nameof(AI.ChatOptions)} is different to the id of the provided {nameof(AgentThread)}.
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

        return (typedThread, chatOptions, threadMessages);
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
