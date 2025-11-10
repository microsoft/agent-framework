// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Response executor that uses an AIAgent to execute responses locally.
/// This is the default implementation for local execution.
/// </summary>
internal sealed class AIAgentResponseExecutor : IResponseExecutor
{
    private readonly AIAgent _agent;

    public AIAgentResponseExecutor(AIAgent agent)
    {
        ArgumentNullException.ThrowIfNull(agent);
        this._agent = agent;
    }

    public ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default) => ValueTask.FromResult<ResponseError?>(null);

    public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Create options with properties from the request
        var chatOptions = new ChatOptions
        {
            ConversationId = request.Conversation?.Id,
            Temperature = (float?)request.Temperature,
            TopP = (float?)request.TopP,
            MaxOutputTokens = request.MaxOutputTokens,
            Instructions = request.Instructions,
            ModelId = request.Model,
        };
        var options = new ChatClientAgentRunOptions(chatOptions);

        // Convert input to chat messages
        var messages = new List<ChatMessage>();

        foreach (var inputMessage in request.Input.GetInputMessages())
        {
            messages.Add(inputMessage.ToChatMessage());
        }

        // Use the extension method to convert streaming updates to streaming response events
        await foreach (var streamingEvent in this._agent.RunStreamingAsync(messages, options: options, cancellationToken: cancellationToken)
            .ToStreamingResponseAsync(request, context, cancellationToken)
            .ConfigureAwait(false))
        {
            yield return streamingEvent;
        }
    }
}
