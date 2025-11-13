// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// A delegating agent that connects to Microsoft Purview.
/// </summary>
internal sealed class PurviewWrapper : IDisposable
{
    private readonly ILogger _logger;
    private readonly IScopedContentProcessor _scopedProcessor;
    private readonly PurviewSettings _purviewSettings;
    private readonly IChannelHandler _channelHandler;

    /// <summary>
    /// Creates a new <see cref="PurviewWrapper"/> instance.
    /// </summary>
    /// <param name="scopedProcessor">The scoped processor used to orchestrate the calls to Purview.</param>
    /// <param name="purviewSettings">The settings for Purview integration.</param>
    /// <param name="logger">The logger used for logging.</param>
    /// <param name="channelHandler">The channel handler used to queue background jobs and add job runners.</param>
    public PurviewWrapper(IScopedContentProcessor scopedProcessor, PurviewSettings purviewSettings, ILogger logger, IChannelHandler channelHandler)
    {
        this._scopedProcessor = scopedProcessor;
        this._purviewSettings = purviewSettings;
        this._logger = logger;
        this._channelHandler = channelHandler;
    }

    private static string GetThreadIdFromAgentThread(AgentThread? thread, IEnumerable<ChatMessage> messages)
    {
        if (thread is ChatClientAgentThread chatClientAgentThread &&
            chatClientAgentThread.ConversationId != null)
        {
            return chatClientAgentThread.ConversationId;
        }

        foreach (ChatMessage message in messages)
        {
            if (message.AdditionalProperties != null &&
                message.AdditionalProperties.TryGetValue(Constants.ConversationId, out object? conversationId) &&
                conversationId != null)
            {
                return conversationId.ToString() ?? Guid.NewGuid().ToString();
            }
        }

        return Guid.NewGuid().ToString();
    }

    /// <summary>
    /// Processes a prompt and response exchange at a chat client level.
    /// </summary>
    /// <param name="messages">The messages sent to the chat client.</param>
    /// <param name="options">The chat options used with the chat client.</param>
    /// <param name="innerChatClient">The wrapped chat client.</param>
    /// <param name="cancellationToken">The cancellation token used to interrupt async operations.</param>
    /// <returns>The chat client's response. This could be the response from the chat client or a message indicating that Purview has blocked the prompt or response.</returns>
    public async Task<ChatResponse> ProcessChatContentAsync(IEnumerable<ChatMessage> messages, ChatOptions? options, IChatClient innerChatClient, CancellationToken cancellationToken)
    {
        string? resolvedUserId = null;

        try
        {
            (bool shouldBlockPrompt, resolvedUserId) = await this._scopedProcessor.ProcessMessagesAsync(messages, options?.ConversationId, Activity.UploadText, this._purviewSettings, null, cancellationToken).ConfigureAwait(false);
            if (shouldBlockPrompt)
            {
                this._logger.LogInformation("Prompt blocked by policy. Sending message: {Message}", this._purviewSettings.BlockedPromptMessage);
                return new ChatResponse(new ChatMessage(ChatRole.System, this._purviewSettings.BlockedPromptMessage));
            }
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing prompt: {ExceptionMessage}", ex.Message);

            if (!this._purviewSettings.IgnoreExceptions)
            {
                throw;
            }
        }

        ChatResponse response = await innerChatClient.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);

        try
        {
            (bool shouldBlockResponse, _) = await this._scopedProcessor.ProcessMessagesAsync(response.Messages, options?.ConversationId, Activity.UploadText, this._purviewSettings, resolvedUserId, cancellationToken).ConfigureAwait(false);
            if (shouldBlockResponse)
            {
                this._logger.LogInformation("Response blocked by policy. Sending message: {Message}", this._purviewSettings.BlockedResponseMessage);
                return new ChatResponse(new ChatMessage(ChatRole.System, this._purviewSettings.BlockedResponseMessage));
            }
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing response: {ExceptionMessage}", ex.Message);

            if (!this._purviewSettings.IgnoreExceptions)
            {
                throw;
            }
        }

        return response;
    }

    /// <summary>
    /// Processes a prompt and response exchange at an agent level.
    /// </summary>
    /// <param name="messages">The messages sent to the agent.</param>
    /// <param name="thread">The thread used for this agent conversation.</param>
    /// <param name="options">The options used with this agent.</param>
    /// <param name="innerAgent">The wrapped agent.</param>
    /// <param name="cancellationToken">The cancellation token used to interrupt async operations.</param>
    /// <returns>The agent's response. This could be the response from the agent or a message indicating that Purview has blocked the prompt or response.</returns>
    public async Task<AgentRunResponse> ProcessAgentContentAsync(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
    {
        string threadId = GetThreadIdFromAgentThread(thread, messages);

        string? resolvedUserId = null;

        try
        {
            (bool shouldBlockPrompt, resolvedUserId) = await this._scopedProcessor.ProcessMessagesAsync(messages, threadId, Activity.UploadText, this._purviewSettings, null, cancellationToken).ConfigureAwait(false);

            if (shouldBlockPrompt)
            {
                this._logger.LogInformation("Prompt blocked by policy. Sending message: {Message}", this._purviewSettings.BlockedPromptMessage);
                return new AgentRunResponse(new ChatMessage(ChatRole.System, this._purviewSettings.BlockedPromptMessage));
            }
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing prompt: {ExceptionMessage}", ex.Message);

            if (!this._purviewSettings.IgnoreExceptions)
            {
                throw;
            }
        }

        AgentRunResponse response = await innerAgent.RunAsync(messages, thread, options, cancellationToken).ConfigureAwait(false);

        try
        {
            (bool shouldBlockResponse, _) = await this._scopedProcessor.ProcessMessagesAsync(response.Messages, threadId, Activity.UploadText, this._purviewSettings, resolvedUserId, cancellationToken).ConfigureAwait(false);

            if (shouldBlockResponse)
            {
                this._logger.LogInformation("Response blocked by policy. Sending message: {Message}", this._purviewSettings.BlockedResponseMessage);
                return new AgentRunResponse(new ChatMessage(ChatRole.System, this._purviewSettings.BlockedResponseMessage));
            }
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error processing response: {ExceptionMessage}", ex.Message);

            if (!this._purviewSettings.IgnoreExceptions)
            {
                throw;
            }
        }

        return response;
    }

    /// <inheritdoc/>
    public void Dispose()
    {
#pragma warning disable VSTHRD002 // Need to wait for pending jobs to complete.
        this._channelHandler.StopAndWaitForCompletionAsync().GetAwaiter().GetResult();
#pragma warning restore VSTHRD002 // Need to wait for pending jobs to complete.
    }
}
