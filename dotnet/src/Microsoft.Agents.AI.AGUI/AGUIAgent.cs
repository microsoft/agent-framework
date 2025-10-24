// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.ServerSentEvents;
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
    private readonly HttpClient _httpClient;
    private readonly string _agentId;
    private readonly string? _description;

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgent"/> class.
    /// </summary>
    /// <param name="httpClient">The HTTP client to use for communication with the AG-UI server.</param>
    /// <param name="id">The agent ID.</param>
    /// <param name="description">Optional description of the agent.</param>
    /// <param name="messages">Initial conversation messages.</param>
    public AGUIAgent(HttpClient httpClient, string id, string description, IEnumerable<ChatMessage> messages)
    {
        this._httpClient = Throw.IfNull(httpClient);
        this._agentId = Throw.IfNullOrWhitespace(id);
        this._description = description;
    }

    /// <inheritdoc/>
    public override string Id => this._agentId;

    /// <inheritdoc/>
    public override string? Description => this._description;

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

        AGUIAgentThread aguiThread = thread as AGUIAgentThread ?? new AGUIAgentThread();

        string threadId = Guid.NewGuid().ToString("N");
        string runId = Guid.NewGuid().ToString("N");

        RunAgentInput input = new()
        {
            ThreadId = threadId,
            RunId = runId,
            Messages = messages.Select(m => new AGUIMessage
            {
                Role = m.Role.Value,
                Content = m.Text
            }).ToArray(),
            Tools = [],
            Context = new Dictionary<string, string>(StringComparer.Ordinal)
        };

        string jsonContent = JsonSerializer.Serialize(input, AGUIJsonSerializerContext.Default.RunAgentInput);
        using StringContent content = new(jsonContent, System.Text.Encoding.UTF8, "application/json");
        using HttpResponseMessage response = await this._httpClient.PostAsync(
            this._httpClient.BaseAddress,
            content,
            cancellationToken).ConfigureAwait(false);

        response.EnsureSuccessStatusCode();

#if NET
        Stream responseStream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
#else
        Stream responseStream = await response.Content.ReadAsStreamAsync().ConfigureAwait(false);
#endif

        AGUIEventStreamProcessor processor = new();

        await foreach (SseItem<string> sseItem in SseParser.Create(responseStream).EnumerateAsync(cancellationToken).ConfigureAwait(false))
        {
            BaseEvent? evt = JsonSerializer.Deserialize(sseItem.Data, AGUIJsonSerializerContext.Default.BaseEvent);
            if (evt is null)
            {
                continue;
            }

            switch (evt)
            {
                case RunStartedEvent runStarted:
                    AgentRunResponse startResponse = processor.MapRunStarted(runStarted);
                    foreach (AgentRunResponseUpdate update in startResponse.ToAgentRunResponseUpdates())
                    {
                        yield return update;
                    }
                    break;

                case TextMessageStartEvent:
                case TextMessageContentEvent:
                case TextMessageEndEvent:
                    // Buffer text events and process them together
                    List<BaseEvent> textEvents = [evt];
                    yield return processor.MapTextEvents(textEvents);
                    break;

                case RunFinishedEvent runFinished:
                    AgentRunResponse finishResponse = processor.MapRunFinished(runFinished);
                    foreach (AgentRunResponseUpdate update in finishResponse.ToAgentRunResponseUpdates())
                    {
                        yield return update;
                    }
                    break;

                case RunErrorEvent runError:
                    AgentRunResponse errorResponse = processor.MapRunError(runError);
                    foreach (AgentRunResponseUpdate update in errorResponse.ToAgentRunResponseUpdates())
                    {
                        yield return update;
                    }
                    break;
            }
        }

        await NotifyThreadOfNewMessagesAsync(aguiThread, messages, cancellationToken).ConfigureAwait(false);
    }
}
