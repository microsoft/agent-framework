// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Agents.AI.Purview.Models.Common;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Caching.Distributed;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Purview;

/// <summary>
/// A delegating agent that connects to Microsoft Purview.
/// </summary>
internal sealed class PurviewWrapper
{
    private readonly ILogger _logger;
    private readonly IScopedContentProcessor _scopedProcessor;
    private readonly PurviewSettings _purviewSettings;

    /// <summary>
    /// Creates a new <see cref="PurviewWrapper"/> instance.
    /// </summary>
    /// <param name="tokenCredential"></param>
    /// <param name="purviewSettings"></param>
    /// <param name="logger"></param>
    public PurviewWrapper(TokenCredential tokenCredential, PurviewSettings purviewSettings, ILogger? logger = null)
    {
        ServiceCollection services = new();
        services.AddSingleton(tokenCredential);
        services.AddSingleton(purviewSettings);
        services.AddSingleton<IPurviewClient, PurviewClient>();
        services.AddSingleton<IScopedContentProcessor, ScopedContentProcessor>();

        MemoryDistributedCacheOptions options = new()
        {
            SizeLimit = purviewSettings.CacheSizeLimit,
        };

        IDistributedCache cache = purviewSettings.Cache ?? new MemoryDistributedCache(Options.Create(options));

        services.AddSingleton(cache);
        services.AddSingleton<ICacheProvider, CacheProvider>();
        services.AddSingleton<HttpClient>();
        services.AddSingleton(logger ?? NullLogger.Instance);
        ServiceProvider serviceProvider = services.BuildServiceProvider();

        this._logger = serviceProvider.GetRequiredService<ILogger>();
        this._scopedProcessor = serviceProvider.GetRequiredService<IScopedContentProcessor>();
        this._purviewSettings = serviceProvider.GetRequiredService<PurviewSettings>();
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
}
