// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents;

/// <summary>
/// Represents a <see cref="Agent"/> specialization based on <see cref="IChatClient"/>.
/// </summary>
public sealed class ChatClientAgent : Agent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgent"/> class.
    /// </summary>
    public ChatClientAgent(IChatClient chatClient)
    {
        Verify.NotNull(chatClient);

        this.ChatClient = chatClient;
    }

    /// <summary>
    /// Gets the <see cref="IChatClient"/> used to invoke the agent.
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
    public ChatRole InstructionsRole { get; init; } = ChatRole.System;

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentResponseItem<ChatMessage>> InvokeAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Verify.NotNull(messages);

        var chatMessageAgentThread = await this.EnsureThreadExistsWithMessagesAsync(
            messages,
            thread,
            () => new ChatMessageAgentThread(),
            cancellationToken).ConfigureAwait(false);

        // Invoke Chat Completion with the updated chat chatMessages.
        var chatHistory = new List<ChatMessage>();
        await foreach (var existingMessage in chatMessageAgentThread.GetMessagesAsync(cancellationToken).ConfigureAwait(false))
        {
            chatHistory.Add(existingMessage);
        }
        var invokeResults = this.InternalInvokeAsync(
            this.GetDisplayName(),
            chatHistory,
            async (m) =>
            {
                await this.NotifyThreadOfNewMessage(chatMessageAgentThread, m, cancellationToken).ConfigureAwait(false);
                if (options?.OnIntermediateMessage is not null)
                {
                    await options.OnIntermediateMessage(m).ConfigureAwait(false);
                }
            },
            new(),
            cancellationToken);

        // Notify the thread of new chatMessages and return them to the caller.
        await foreach (var result in invokeResults.ConfigureAwait(false))
        {
            yield return new(result, chatMessageAgentThread);
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentResponseItem<ChatResponseUpdate>> InvokeStreamingAsync(
        ICollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentInvokeOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Verify.NotNull(messages);

        var chatHistoryAgentThread = await this.EnsureThreadExistsWithMessagesAsync(
            messages,
            thread,
            () => new ChatMessageAgentThread(),
            cancellationToken).ConfigureAwait(false);

        // Invoke Chat Completion with the updated chat chatMessages.
        var chatMessages = new List<ChatMessage>();
        await foreach (var existingMessage in chatHistoryAgentThread.GetMessagesAsync(cancellationToken).ConfigureAwait(false))
        {
            chatMessages.Add(existingMessage);
        }
        string agentName = this.GetDisplayName();
        var invokeResults = this.InternalInvokeStreamingAsync(
            agentName,
            chatMessages,
            async (m) =>
            {
                await this.NotifyThreadOfNewMessage(chatHistoryAgentThread, m, cancellationToken).ConfigureAwait(false);
                if (options?.OnIntermediateMessage is not null)
                {
                    await options.OnIntermediateMessage(m).ConfigureAwait(false);
                }
            },
            new ChatOptions(),
            cancellationToken);

        await foreach (var result in invokeResults.ConfigureAwait(false))
        {
            yield return new(result, chatHistoryAgentThread);
        }
    }

    #region private

    private async IAsyncEnumerable<ChatMessage> InternalInvokeAsync(
        string agentName,
        List<ChatMessage> chatMessages,
        Func<ChatMessage, Task> onNewToolMessage,
        ChatOptions? chatOptions = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Verify.NotNull(chatMessages);
        Verify.NotNull(this.ChatClient);

        int messageCount = chatMessages.Count;

        var chatResponse = await this.ChatClient!.GetResponseAsync(
            chatMessages,
            chatOptions,
            cancellationToken).ConfigureAwait(false);

        foreach (var chatMessage in chatResponse.Messages)
        {
            yield return chatMessage;
        }
    }

    private async IAsyncEnumerable<ChatResponseUpdate> InternalInvokeStreamingAsync(
        string agentName,
        List<ChatMessage> chatMessages,
        Func<ChatMessage, Task> onNewMessage,
        ChatOptions? chatOptions = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Verify.NotNull(chatMessages);
        Verify.NotNull(this.ChatClient);

        int messageCount = chatMessages.Count;

        var chatResponseUpdates = this.ChatClient!.GetStreamingResponseAsync(
            chatMessages,
            chatOptions,
            cancellationToken);

        //ChatRole? role = null;
        //StringBuilder builder = new();
        await foreach (var chatResponseUpdate in chatResponseUpdates.ConfigureAwait(false))
        {
            /*
            role = message.Role;
            message.Role ??= AuthorRole.Assistant;
            message.AuthorName = this.Name;
            builder.Append(message.ToString());
            */

            yield return chatResponseUpdate;
        }
        /*
        // Capture mutated chatMessages related function calling / tools
        for (int messageIndex = messageCount; messageIndex < chat.Count; messageIndex++)
        {
            ChatMessage message = chat[messageIndex];

            message.AuthorName = this.Name;

            await onNewMessage(message).ConfigureAwait(false);
            messages.Add(message);
        }

        // Do not duplicate terminated function result to chatMessages
        if (role != AuthorRole.Tool)
        {
            await onNewMessage(new(role ?? AuthorRole.Assistant, builder.ToString()) { AuthorName = this.Name }).ConfigureAwait(false);
            messages.Add(new(role ?? AuthorRole.Assistant, builder.ToString()) { AuthorName = this.Name });
        }
        */
    }

    #endregion
}
