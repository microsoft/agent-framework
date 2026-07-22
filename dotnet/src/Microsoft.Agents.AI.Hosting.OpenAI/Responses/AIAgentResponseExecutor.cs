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
    private readonly Func<OpenAIResponseRequestInfo, AgentRunOptions?> _runOptionsFactory;

    public AIAgentResponseExecutor(AIAgent agent, OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        this._agent = agent;
        this._runOptionsFactory = (mapOptions ?? new OpenAIResponsesMapOptions()).RunOptionsFactory;
    }

    public ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
        => ValueTask.FromResult(this.ValidateRunOptions(request));

    internal ResponseError? ValidateRunOptions(CreateResponse request)
    {
        try
        {
            // Invoke the factory during validation so that unsupported request settings are surfaced
            // as a clean request error rather than an unhandled exception during execution.
            _ = this._runOptionsFactory(request.ToRequestInfo());
            return null;
        }
        catch (NotSupportedException ex)
        {
            return new ResponseError
            {
                Code = "unsupported_parameter",
                Message = ex.Message
            };
        }
    }

    public async IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
        AgentInvocationContext context,
        CreateResponse request,
        IReadOnlyList<ChatMessage>? conversationHistory = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // The hosting developer controls, via OpenAIResponsesMapOptions.RunOptionsFactory, which (if any)
        // request settings are mapped onto the agent run. By default no request setting is mapped.
        AgentRunOptions? options = this._runOptionsFactory(request.ToRequestInfo());

        // Convert input to chat messages, prepending conversation history if available
        var messages = new List<ChatMessage>();

        if (conversationHistory is not null)
        {
            messages.AddRange(conversationHistory);
        }

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
