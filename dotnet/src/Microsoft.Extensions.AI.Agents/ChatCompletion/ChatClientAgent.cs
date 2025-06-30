// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Represents an agent that can be invoked using a chat client.
/// </summary>
public sealed class ChatClientAgent : Agent
{
    private readonly ChatClientAgentOptions? _agentOptions;
    private readonly ILogger _logger;
    private readonly Type _chatClientType;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for invoking the agent.</param>
    /// <param name="options">Optional agent options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public ChatClientAgent(IChatClient chatClient, ChatClientAgentOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(chatClient);

        // Options must be cloned since ChatClientAgentOptions is mutable.
        this._agentOptions = options?.Clone();

        // Get the type of the chat client before wrapping it as an agent invoking chat client.
        this._chatClientType = chatClient.GetType();

        this.ChatClient = chatClient.AsAgentInvokingChatClient();

        this._logger = (loggerFactory ?? chatClient.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance).CreateLogger<ChatClientAgent>();
    }

    /// <summary>
    /// The underlying chat client used by the agent to invoke chat completions.
    /// </summary>
    public IChatClient ChatClient { get; }

    /// <inheritdoc/>
    public override string Id => this._agentOptions?.Id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._agentOptions?.Name;

    /// <inheritdoc/>
    public override string? Description => this._agentOptions?.Description;

    /// <inheritdoc/>
    public override string? Instructions => this._agentOptions?.Instructions;

    /// <summary>
    /// Gets of the default <see cref="Microsoft.Extensions.AI.ChatOptions"/> used by the agent.
    /// </summary>
    internal ChatOptions? ChatOptions => this._agentOptions?.ChatOptions;

    /// <inheritdoc/>
    public override async Task<ChatResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        (ChatClientAgentThread chatClientThread, ChatOptions? chatOptions, List<ChatMessage> threadMessages) =
            await this.PrepareThreadAndMessagesAsync(thread, messages, options, cancellationToken).ConfigureAwait(false);

        var agentName = this.GetAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunAsync), this.Id, agentName, this._chatClientType);

        ChatResponse chatResponse = await this.ChatClient.GetResponseAsync(threadMessages, chatOptions, cancellationToken).ConfigureAwait(false);

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, agentName, this._chatClientType, messages.Count);

        // We can derive the type of supported thread from whether we have a conversation id,
        // so let's update it and set the conversation id for the service thread case.
        this.UpdateThreadWithTypeAndConversationId(chatClientThread, chatResponse.ConversationId);

        // Only notify the thread of new messages if the chatResponse was successful to avoid inconsistent messages state in the thread.
        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, messages, cancellationToken).ConfigureAwait(false);

        // Ensure that the author name is set for each message in the response.
        foreach (ChatMessage chatResponseMessage in chatResponse.Messages)
        {
            chatResponseMessage.AuthorName ??= agentName;
        }

        // Convert the chat response messages to a valid IReadOnlyCollection for notification signatures below.
        var chatResponseMessages = chatResponse.Messages as IReadOnlyCollection<ChatMessage> ?? chatResponse.Messages.ToArray();

        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, chatResponseMessages, cancellationToken).ConfigureAwait(false);
        if (options?.OnIntermediateMessages is not null)
        {
            await options.OnIntermediateMessages(chatResponseMessages).ConfigureAwait(false);
        }

        return chatResponse;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var inputMessages = Throw.IfNull(messages);

        (ChatClientAgentThread chatClientThread, ChatOptions? chatOptions, List<ChatMessage> threadMessages) =
            await this.PrepareThreadAndMessagesAsync(thread, inputMessages, options, cancellationToken).ConfigureAwait(false);

        int messageCount = threadMessages.Count;
        var agentName = this.GetAgentName();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunStreamingAsync), this.Id, agentName, this._chatClientType);

        // Using the enumerator to ensure we consider the case where no updates are returned for notification.
        var responseUpdatesEnumerator = this.ChatClient.GetStreamingResponseAsync(threadMessages, chatOptions, cancellationToken).GetAsyncEnumerator(cancellationToken);

        this._logger.LogAgentChatClientInvokedStreamingAgent(nameof(RunStreamingAsync), this.Id, agentName, this._chatClientType);

        List<ChatResponseUpdate> responseUpdates = [];

        // Ensure we start the streaming request
        var hasUpdates = await responseUpdatesEnumerator.MoveNextAsync().ConfigureAwait(false);

        while (hasUpdates)
        {
            var update = responseUpdatesEnumerator.Current;
            if (update is not null)
            {
                responseUpdates.Add(update);
                update.AuthorName ??= agentName;
                yield return update;
            }

            hasUpdates = await responseUpdatesEnumerator.MoveNextAsync().ConfigureAwait(false);
        }

        var chatResponse = responseUpdates.ToChatResponse();
        var chatResponseMessages = chatResponse.Messages as IReadOnlyCollection<ChatMessage> ?? chatResponse.Messages.ToArray();

        // We can derive the type of supported thread from whether we have a conversation id,
        // so let's update it and set the conversation id for the service thread case.
        this.UpdateThreadWithTypeAndConversationId(chatClientThread, chatResponse.ConversationId);

        // To avoid inconsistent state we only notify the thread of the input messages if no error occurs after the initial request.
        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, inputMessages, cancellationToken).ConfigureAwait(false);

        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, chatResponseMessages, cancellationToken).ConfigureAwait(false);
        if (options?.OnIntermediateMessages is not null)
        {
            await options.OnIntermediateMessages(chatResponseMessages).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public override AgentThread GetNewThread() => new ChatClientAgentThread();

    #region Private

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
            return this._agentOptions?.ChatOptions?.Clone();
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

        // Merge only the additional properties from the agent if they are not already set in the request options.
        if (requestChatOptions.AdditionalProperties is not null && this._agentOptions.ChatOptions.AdditionalProperties is not null)
        {
            foreach (var propertyKey in this._agentOptions.ChatOptions.AdditionalProperties.Keys)
            {
                requestChatOptions.AdditionalProperties.TryAdd(propertyKey, this._agentOptions.ChatOptions.AdditionalProperties[propertyKey]);
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
    private async Task<(ChatClientAgentThread, ChatOptions?, List<ChatMessage>)> PrepareThreadAndMessagesAsync(
        AgentThread? thread,
        IReadOnlyCollection<ChatMessage> inputMessages,
        AgentRunOptions? runOptions,
        CancellationToken cancellationToken)
    {
        ChatOptions? chatOptions = this.CreateConfiguredChatOptions(runOptions);

        var chatClientThread = this.ValidateOrCreateThreadType<ChatClientAgentThread>(thread, () => new());

        // Add any existing messages from the thread to the messages to be sent to the chat client.
        List<ChatMessage> threadMessages = [];
        if (chatClientThread is IMessagesRetrievableThread messagesRetrievableThread)
        {
            await foreach (ChatMessage message in messagesRetrievableThread.GetMessagesAsync(cancellationToken).ConfigureAwait(false))
            {
                threadMessages.Add(message);
            }
        }

        // Update the messages with agent instructions.
        this.UpdateThreadMessagesWithAgentInstructions(threadMessages, runOptions);

        // Add the input messages to the end of thread messages.
        threadMessages.AddRange(inputMessages);

        // If a user provided two different thread ids, via the thread object and options, we should throw
        // since we don't know which one to use.
        if (!string.IsNullOrWhiteSpace(chatClientThread.Id) && !string.IsNullOrWhiteSpace(chatOptions?.ConversationId) && chatClientThread.Id != chatOptions.ConversationId)
        {
            throw new InvalidOperationException(
                $"The {nameof(chatOptions.ConversationId)} provided via {nameof(Microsoft.Extensions.AI.ChatOptions)} is different to the id of the provided {nameof(AgentThread)}. Only one thread id can be used for a run.");
        }

        // Only clone and update ChatOptions if we have an id on the thread and we don't have the same one already in ChatOptions.
        if (!string.IsNullOrWhiteSpace(chatClientThread.Id) && chatClientThread.Id != chatOptions?.ConversationId)
        {
            chatOptions ??= new();
            chatOptions.ConversationId = chatClientThread.Id;
        }

        return (chatClientThread, chatOptions, threadMessages);
    }

    private void UpdateThreadWithTypeAndConversationId(ChatClientAgentThread chatClientThread, string? responseConversationId)
    {
        // Set the thread's storage location, the first time that we use it.
        if (chatClientThread.StorageLocation is null)
        {
            chatClientThread.StorageLocation = string.IsNullOrWhiteSpace(responseConversationId)
                ? ChatClientAgentThreadType.InMemoryMessages
                : ChatClientAgentThreadType.ConversationId;
        }

        // If we got a conversation id back from the chat client, it means that the service supports server side thread storage
        // so we should capture the id and update the thread with the new id.
        if (chatClientThread.StorageLocation == ChatClientAgentThreadType.ConversationId)
        {
            if (string.IsNullOrWhiteSpace(responseConversationId))
            {
                throw new InvalidOperationException("Service did not return a valid conversation id when using a service managed thread.");
            }

            chatClientThread.Id = responseConversationId;
        }
    }

    private void UpdateThreadMessagesWithAgentInstructions(List<ChatMessage> threadMessages, AgentRunOptions? options)
    {
        if (!string.IsNullOrWhiteSpace(this.Instructions))
        {
            threadMessages.Insert(0, new(ChatRole.System, this.Instructions) { AuthorName = this.Name });
        }
    }

    private string GetAgentName() => this.Name ?? "UnnamedAgent";
    #endregion
}
