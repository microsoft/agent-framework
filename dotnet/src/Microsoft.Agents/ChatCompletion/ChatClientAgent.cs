// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.ChatCompletion;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents;

/// <summary>
/// Placeholder class.
/// </summary>
public sealed class ChatClientAgent : Agent
{
    private readonly ChatClientAgentMetadata? _metadata;
    private readonly ILoggerFactory _loggerFactory;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    public ChatClientAgent(IChatClient chatClient, ChatClientAgentMetadata? metadata, ILoggerFactory? loggerFactory = null)
    {
        this.ChatClient = chatClient;
        this._metadata = metadata;
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
    public override string Id => this._metadata?.Id ?? base.Id;

    /// <inheritdoc/>
    public override string? Name => this._metadata?.Name;

    /// <inheritdoc/>
    public override string? Description => this._metadata?.Description;

    /// <inheritdoc/>
    public override string? Instructions => this._metadata?.Instructions;

    /// <inheritdoc/>
    public override Task<AgentThread> CreateThreadAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult<AgentThread>(new ChatClientAgentThread());
    }

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

        var chatClientThread = await this.EnsureThreadExistsWithMessagesAsync(
            messages,
            thread,
            () => new ChatClientAgentThread(),
            cancellationToken).ConfigureAwait(false);

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

        int messageCount = chatMessages.Count;
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
        for (int messageIndex = messageCount; messageIndex < chatResponse.Messages.Count; messageIndex++)
        {
            ChatMessage message = chatResponse.Messages[messageIndex];

            message.AuthorName = this.Name;

            chatMessages.Add(message);

            await this.NotifyThreadOfNewMessage(chatClientThread, message, cancellationToken).ConfigureAwait(false);
            if (options?.OnIntermediateMessage is not null)
            {
                await options.OnIntermediateMessage(message).ConfigureAwait(false);
            }
        }

        foreach (ChatMessage message in chatMessages)
        {
            message.AuthorName = this.Name;
        }

        chatResponse.Messages = chatMessages;
        return chatResponse;
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

    /// <inheritdoc/>
    public override IAsyncEnumerable<ChatResponseUpdate> RunStreamingAsync(IReadOnlyCollection<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        throw new System.NotImplementedException();
    }
}
