// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="AIAgent"/> implementation that communicates with an AG-UI compliant server.
/// </summary>
public sealed class AGUIAgent : AIAgent, IDisposable
{
    private readonly IChatClient _chatClient;
    private readonly IList<AITool> _tools;

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgent"/> class.
    /// </summary>
    /// <param name="id">The agent ID.</param>
    /// <param name="description">Optional description of the agent.</param>
    /// <param name="httpClient">The HTTP client to use for communication with the AG-UI server.</param>
    /// <param name="endpoint">The URL for the AG-UI server.</param>
    /// <param name="jsonSerializerOptions">JSON serializer options for tool call argument serialization. If null, AGUIJsonSerializerContext.Default.Options will be used.</param>
    /// <param name="tools">Tools to make available to the agent.</param>
    public AGUIAgent(
        string id,
        string description,
        HttpClient httpClient,
        string endpoint,
        JsonSerializerOptions? jsonSerializerOptions,
        IList<AITool> tools)
    {
        this.Id = Throw.IfNullOrWhitespace(id);
        this.Description = description;

        var innerClient = new AGUIChatClient(
            httpClient ?? Throw.IfNull(httpClient),
            endpoint ?? Throw.IfNullOrEmpty(endpoint),
            modelId: id,
            jsonSerializerOptions: jsonSerializerOptions);

        // Wrap with FunctionInvokingChatClient to handle automatic tool invocation
        this._chatClient = new FunctionInvokingChatClient(innerClient);
        this._tools = tools ?? throw new ArgumentNullException(nameof(tools));
    }

    /// <inheritdoc/>
    public override string Id { get; }

    /// <inheritdoc/>
    public override string? Description { get; }

    /// <inheritdoc/>
    public override AgentThread GetNewThread() => new AGUIAgentThread();

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null) =>
        new AGUIAgentThread(serializedThread, jsonSerializerOptions);

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return await this.RunStreamingAsync(messages, thread, null, cancellationToken)
            .ToAgentRunResponseAsync(cancellationToken)
            .ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        if ((thread ?? this.GetNewThread()) is not AGUIAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        // Create chat options with thread ID and tools
        var chatOptions = new ChatOptions
        {
            ConversationId = typedThread.ThreadId,
        };

        if (this._tools is { Count: > 0 })
        {
            chatOptions.Tools = this._tools;
        }

        var llmMessages = typedThread.MessageStore.Concat(messages);
        List<ChatResponseUpdate> allUpdates = [];

        // FunctionInvokingChatClient handles automatic tool invocation
        await foreach (var update in this._chatClient.GetStreamingResponseAsync(llmMessages, chatOptions, cancellationToken).ConfigureAwait(false))
        {
            allUpdates.Add(update);
            yield return new AgentRunResponseUpdate(update);
        }

        var finalResponse = allUpdates.ToChatResponse();
        await NotifyThreadOfNewMessagesAsync(typedThread, messages.Concat(finalResponse.Messages), cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Disposes the agent and releases associated resources.
    /// </summary>
    public void Dispose()
    {
        this._chatClient?.Dispose();
    }
}
