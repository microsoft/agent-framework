// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="AIAgent"/> implementation that communicates with an AG-UI compliant server.
/// </summary>
public sealed class AGUIAgent : AIAgent
{
    private readonly AGUIHttpService _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgent"/> class.
    /// </summary>
    /// <param name="id">The agent ID.</param>
    /// <param name="description">Optional description of the agent.</param>
    /// <param name="messages">Initial conversation messages.</param>
    /// <param name="httpClient">The HTTP client to use for communication with the AG-UI server.</param>
    /// <param name="endpoint">The URL for the AG-UI server.</param>
    public AGUIAgent(string id, string description, IEnumerable<ChatMessage> messages, HttpClient httpClient, string endpoint)
    {
        this.Id = Throw.IfNullOrWhitespace(id);
        this.Description = description;
        this._client = new AGUIHttpService(
            httpClient ?? Throw.IfNull(httpClient),
            endpoint ?? Throw.IfNullOrEmpty(endpoint));
    }

    /// <inheritdoc/>
    public override string Id { get; }

    /// <inheritdoc/>
    public override string? Description { get; }

    /// <inheritdoc/>
    public override AgentThread GetNewThread()
    {
        return new AGUIAgentThread();
    }

    /// <inheritdoc/>
    public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return new AGUIAgentThread(serializedThread, jsonSerializerOptions);
    }

    /// <inheritdoc/>
    public override async Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        List<ChatMessage> chatMessages = [];
        await foreach (AgentRunResponseUpdate update in this.RunStreamingAsync(messages, thread, options, cancellationToken).ConfigureAwait(false))
        {
            if (update.Role.HasValue && update.Contents.Count > 0)
            {
                chatMessages.Add(new ChatMessage(update.Role.Value, update.Contents));
            }
        }

        return new AgentRunResponse(chatMessages);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(messages);

        thread ??= this.GetNewThread();
        if (thread is not AGUIAgentThread typedThread)
        {
            throw new InvalidOperationException("The provided thread is not compatible with the agent. Only threads created by the agent can be used.");
        }

        string runId = Guid.NewGuid().ToString();

        RunAgentInput input = new()
        {
            ThreadId = typedThread.ThreadId,
            RunId = runId,
            Messages = messages.AsAGUIMessages(),
            Context = new Dictionary<string, string>(StringComparer.Ordinal)
        };

        var updates = new List<ChatResponseUpdate>();
        await foreach (var update in this._client.PostRunAsync(input, cancellationToken).AsChatResponseUpdatesAsync(cancellationToken).ConfigureAwait(false))
        {
            var chatUpdate = update.AsChatResponseUpdate();
            updates.Add(chatUpdate);
            yield return update;
        }

        var response = updates.ToChatResponse();

        await NotifyThreadOfNewMessagesAsync(thread, response.Messages, cancellationToken).ConfigureAwait(false);
    }
}
