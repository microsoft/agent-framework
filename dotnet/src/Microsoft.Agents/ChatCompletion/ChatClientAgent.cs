// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
/// </summary>
public sealed class ChatClientAgent : Agent
{
    private readonly ChatClientAgentOptions? _agentOptions;
    private readonly ILoggerFactory _loggerFactory;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    /// <param name="chatClient">The chat client to use for invoking the agent.</param>
    /// <param name="options">Optional agent options to configure the agent.</param>
    /// <param name="loggerFactory">Optional logger factory to use for logging.</param>
    public ChatClientAgent(IChatClient chatClient, ChatClientAgentOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        Throw.IfNull(chatClient);

        this.ChatClient = chatClient.AsAgentInvokingChatClient();
        this._agentOptions = options;
        this._loggerFactory = loggerFactory ?? chatClient.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance;
    }

    /// <summary>
    /// The chat client.
    /// </summary>
    public IChatClient ChatClient { get; }

    /// <summary>
    /// Gets the role used for agent instructions.  Defaults to "system".
    /// </summary>
    /// <remarks>
    /// Certain versions of "O*" series (deep reasoning) models require the instructions
    /// to be provided as "developer" role.  Other versions support neither role and
    /// an agent targeting such a model cannot provide instructions.  Agent functionality
    /// will be dictated entirely by the provided plugins.
    /// </remarks>
    public ChatRole InstructionsRole { get; set; } = ChatRole.System;

    /// <inheritdoc/>
    public override string Id => this._agentOptions?.Id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._agentOptions?.Name;

    /// <inheritdoc/>
    public override string? Description => this._agentOptions?.Description;

    /// <inheritdoc/>
    public override string? Instructions => this._agentOptions?.Instructions;

    /// <inheritdoc/>
    public override async Task<ChatResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(messages);

        ILogger logger = this._loggerFactory.CreateLogger<ChatClientAgent>();
        ChatOptions? chatOptions = null;
        if (options is ChatClientAgentRunOptions chatClientAgentRunOptions)
        {
            chatOptions = chatClientAgentRunOptions.ChatOptions;
        }

        var chatClientThread = await this.ValidateOrCreateThreadTypeAsync(thread, messages, () => new ChatClientAgentThread(), cancellationToken).ConfigureAwait(false);

        List<ChatMessage> threadMessages = [];
        if (chatClientThread is IMessagesRetrievableThread messagesRetrievableThread)
        {
            // Retrieve messages from the thread if it supports it
            await foreach (ChatMessage message in messagesRetrievableThread.GetMessagesAsync(cancellationToken).ConfigureAwait(false))
            {
                threadMessages.Add(message);
            }
        }

        List<ChatMessage> chatMessages = await this.GetMessagesWithAgentInstructionsAsync(threadMessages, options, cancellationToken).ConfigureAwait(false);

        var agentName = this.GetDisplayName();
        Type serviceType = this.ChatClient.GetType();

        logger.LogAgentChatClientInvokingAgent(nameof(RunAsync), this.Id, agentName, serviceType);

        ChatResponse chatResponse =
            await this.ChatClient.GetResponseAsync(
                chatMessages,
                chatOptions,
                cancellationToken).ConfigureAwait(false);

        logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, agentName, serviceType, messages.Count);

        // Capture mutated messages related function calling / tools
        foreach (ChatMessage message in chatResponse.Messages)
        {
            message.AuthorName = this.Name;
            chatMessages.Add(message);

            await this.NotifyThreadOfNewMessagesAsync(chatClientThread, [message], cancellationToken).ConfigureAwait(false);
            if (options?.OnIntermediateMessage is not null)
            {
                await options.OnIntermediateMessage(message).ConfigureAwait(false);
            }
        }

        foreach (ChatMessage message in chatMessages)
        {
            message.AuthorName = this.Name;
        }

        return chatResponse;
    }

    /// <inheritdoc/>
    public override IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        throw new System.NotImplementedException();
    }

    /// <inheritdoc/>
    public override AgentThread GetNewThread() => new ChatClientAgentThread();

    #region Private

    private async Task<TThreadType> ValidateOrCreateThreadTypeAsync<TThreadType>(AgentThread? thread, IReadOnlyCollection<ChatMessage> messages, Func<TThreadType> constructThread, CancellationToken cancellationToken)
        where TThreadType : AgentThread
    {
        var chatClientThread = this.ValidateOrCreateThreadType<TThreadType>(thread, constructThread);

        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, messages, cancellationToken).ConfigureAwait(false);

        return chatClientThread;
    }
    private Task<List<ChatMessage>> GetMessagesWithAgentInstructionsAsync(IReadOnlyCollection<ChatMessage> originalChatMessages, AgentRunOptions? options, CancellationToken cancellationToken)
    {
        List<ChatMessage> instructedChatMessages = [];

        if (!string.IsNullOrWhiteSpace(this.Instructions))
        {
            instructedChatMessages.Add(new(this.InstructionsRole, this.Instructions) { AuthorName = this.Name });
        }

        if (!string.IsNullOrWhiteSpace(options?.AdditionalInstructions))
        {
            instructedChatMessages.Add(new(this.InstructionsRole, options?.AdditionalInstructions) { AuthorName = this.Name });
        }

        instructedChatMessages.AddRange(originalChatMessages);

        return Task.FromResult(instructedChatMessages);
    }

    #endregion
}
