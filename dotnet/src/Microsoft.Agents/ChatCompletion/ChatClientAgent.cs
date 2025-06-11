// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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
    private readonly ILogger _logger;

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
        this._logger = (loggerFactory ?? chatClient.GetService<ILoggerFactory>() ?? NullLoggerFactory.Instance).CreateLogger<ChatClientAgent>();
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

        ChatOptions? chatOptions = null;
        if (options is ChatClientAgentRunOptions chatClientAgentRunOptions)
        {
            chatOptions = chatClientAgentRunOptions.ChatOptions;
        }

        var chatClientThread = this.ValidateOrCreateThreadType<ChatClientAgentThread>(thread, () => new());

        List<ChatMessage> threadMessages = [];
        if (chatClientThread is IMessagesRetrievableThread messagesRetrievableThread)
        {
            await foreach (ChatMessage message in messagesRetrievableThread.GetMessagesAsync(cancellationToken).ConfigureAwait(false))
            {
                threadMessages.Add(message);
            }
        }

        threadMessages.AddRange(messages);

        List<ChatMessage> chatMessages = await this.GetMessagesWithAgentInstructionsAsync(threadMessages, options, cancellationToken).ConfigureAwait(false);

        var agentName = this.Name ?? "UnnamedAgent";
        Type serviceType = this.ChatClient.GetType();

        this._logger.LogAgentChatClientInvokingAgent(nameof(RunAsync), this.Id, agentName, serviceType);

        ChatResponse chatResponse =
            await this.ChatClient.GetResponseAsync(
                chatMessages,
                chatOptions,
                cancellationToken).ConfigureAwait(false);

        // Need to add the messages... 
        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, messages, cancellationToken).ConfigureAwait(false);

        foreach (ChatMessage chatResponseMessage in chatResponse.Messages)
        {
            chatResponseMessage.AuthorName ??= agentName;
        }
        var chatResponseMessages = chatResponse.Messages.ToArray();

        this._logger.LogAgentChatClientInvokedAgent(nameof(RunAsync), this.Id, agentName, serviceType, messages.Count);

        await this.NotifyThreadOfNewMessagesAsync(chatClientThread, chatResponseMessages, cancellationToken).ConfigureAwait(false);
        if (options?.OnIntermediateMessages is not null)
        {
            await options.OnIntermediateMessages(chatResponseMessages).ConfigureAwait(false);
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
