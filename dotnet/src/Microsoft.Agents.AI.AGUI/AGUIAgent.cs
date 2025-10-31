// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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
    /// <param name="httpClient">The HTTP client to use for communication with the AG-UI server.</param>
    /// <param name="endpoint">The URL for the AG-UI server.</param>
    public AGUIAgent(string id, string description, HttpClient httpClient, string endpoint)
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

        var aguiOptions = (options as AGUIAgentRunOptions)
            ?? throw new InvalidOperationException($"AGUIAgent requires {nameof(AGUIAgentRunOptions)} with {nameof(AGUIAgentRunOptions.JsonSerializerOptions)} to be provided.");

        Dictionary<string, AIFunction>? toolsLookup = null;
        if (aguiOptions.Tools is { Count: > 0 })
        {
            toolsLookup = aguiOptions.Tools
                .OfType<AIFunction>()
                .ToDictionary(f => f.Name, StringComparer.Ordinal);
        }

        var ongoingMessages = messages.ToList();
        List<ChatResponseUpdate> allUpdates = [];

        do
        {
            if (TryGetExecutablePendingToolCalls(allUpdates, toolsLookup, out var pendingToolCalls))
            {
                // Append messages from existing updates
                var response = allUpdates.ToChatResponse();
                ongoingMessages.AddRange(response.Messages);

                // Invoke tools and collect results
                var toolResultMessages = await InvokeToolsAsync(pendingToolCalls, cancellationToken).ConfigureAwait(false);

                // Append tool call results
                ongoingMessages.AddRange(toolResultMessages);
                allUpdates.Clear();
            }

            await foreach (var update in this.RunStreamingCoreAsync(ongoingMessages, typedThread, aguiOptions, cancellationToken).ConfigureAwait(false))
            {
                allUpdates.Add(update.AsChatResponseUpdate());
                yield return update;
            }
        }
        while (TryGetExecutablePendingToolCalls(allUpdates, toolsLookup, out _));

        var finalResponse = allUpdates.ToChatResponse();
        await NotifyThreadOfNewMessagesAsync(typedThread, messages.Concat(finalResponse.Messages), cancellationToken).ConfigureAwait(false);
    }

    private async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingCoreAsync(
        IEnumerable<ChatMessage> messages,
        AGUIAgentThread thread,
        AGUIAgentRunOptions options,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        string runId = Guid.NewGuid().ToString();

        var llmMessages = thread.MessageStore.Concat(messages);

        RunAgentInput input = new()
        {
            ThreadId = thread.ThreadId,
            RunId = runId,
            Messages = llmMessages.AsAGUIMessages(options.JsonSerializerOptions),
        };

        if (options.Tools is { Count: > 0 })
        {
            input.Tools = options.Tools.AsAGUITools();
        }

        await foreach (var update in this._client.PostRunAsync(input, cancellationToken).AsAgentRunResponseUpdatesAsync(options.JsonSerializerOptions, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    private static bool TryGetExecutablePendingToolCalls(
        List<ChatResponseUpdate> updates,
        Dictionary<string, AIFunction>? toolsLookup,
        out List<PendingToolCallContext> pendingToolCalls)
    {
        pendingToolCalls = null!;

        if (updates.Count == 0 || toolsLookup is not { Count: > 0 })
        {
            return false;
        }

        var lastUpdate = updates[updates.Count - 1];
        var functionCalls = lastUpdate.Contents.OfType<FunctionCallContent>().ToList();

        if (functionCalls.Count == 0)
        {
            return false;
        }

        // Check if all function calls can be executed by finding matching AIFunction tools
        var executableCalls = new List<PendingToolCallContext>();
        foreach (var functionCall in functionCalls)
        {
            if (toolsLookup.TryGetValue(functionCall.Name, out var aiFunction))
            {
                executableCalls.Add(new PendingToolCallContext(functionCall, aiFunction));
            }
        }

        // If we can't execute all tool calls, we must not execute any of them and let the caller handle it.
        // This ensures we don't send partial tool results back to the server.
        if (executableCalls.Count != functionCalls.Count)
        {
            return false;
        }

        pendingToolCalls = executableCalls;
        return true;
    }

    private static async Task<List<ChatMessage>> InvokeToolsAsync(
        List<PendingToolCallContext> pendingToolCalls,
        CancellationToken cancellationToken)
    {
        var toolResultMessages = new List<ChatMessage>();

        foreach (var pending in pendingToolCalls)
        {
            object? result;
            Exception? exception = null;

            try
            {
                var arguments = pending.FunctionCall.Arguments is not null
                    ? new AIFunctionArguments(pending.FunctionCall.Arguments)
                    : null;
                result = await pending.Function.InvokeAsync(arguments, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                exception = ex;
                result = $"Error invoking tool: {ex.Message}";
            }

            var functionResult = exception is null
                ? new FunctionResultContent(pending.FunctionCall.CallId, result)
                : new FunctionResultContent(pending.FunctionCall.CallId, result) { Exception = exception };

            toolResultMessages.Add(new ChatMessage(ChatRole.Tool, [functionResult]));
        }

        return toolResultMessages;
    }

    private readonly struct PendingToolCallContext
    {
        public PendingToolCallContext(FunctionCallContent functionCall, AIFunction function)
        {
            this.FunctionCall = functionCall;
            this.Function = function;
        }

        public FunctionCallContent FunctionCall { get; }

        public AIFunction Function { get; }
    }
}
