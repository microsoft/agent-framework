// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI.Agents.Purview.Models.Common;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Extensions.AI.Agents.Purview;

/// <summary>
/// A delegating agent that connects to Microsoft Purview.
/// </summary>
public sealed class PurviewWrapper
{
    private readonly ILogger _logger;
    private readonly ScopedContentProcessor _scopedProcessor;
    private readonly PurviewSettings _purviewSettings;

    /// <summary>
    /// Creates a new <see cref="PurviewWrapper"/> instance.
    /// </summary>
    /// <param name="tokenCredential"></param>
    /// <param name="purviewSettings"></param>
    /// <param name="logger"></param>
    public PurviewWrapper(TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null)
    {
        this._logger = logger ?? NullLogger.Instance;
        this._scopedProcessor = new ScopedContentProcessor(new PurviewClient(tokenCredential, purviewSettings));
        this._purviewSettings = purviewSettings;
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
    /// <param name="messages"></param>
    /// <param name="options"></param>
    /// <param name="innerChatClient"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
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
        }

        return response;
    }

    /// <summary>
    /// Processes a prompt and response exchange at an agent level.
    /// </summary>
    /// <param name="messages"></param>
    /// <param name="thread"></param>
    /// <param name="options"></param>
    /// <param name="innerAgent"></param>
    /// <param name="cancellationToken"></param>
    /// <returns></returns>
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
        }

        return response;
    }
}
