// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Response executor that uses an AIAgent to execute responses locally.
/// This is the default implementation for local execution.
/// </summary>
internal sealed class AIAgentResponseExecutor : IResponseExecutor
{
    private readonly AIAgent _agent;
    private readonly Func<OpenAIResponseRequestInfo, AgentRunOptions?> _runOptionsFactory;
    private readonly IServiceProvider _serviceProvider;

    public AIAgentResponseExecutor(AIAgent agent, IServiceProvider serviceProvider, OpenAIResponsesMapOptions? mapOptions = null)
    {
        ArgumentNullException.ThrowIfNull(agent);
        ArgumentNullException.ThrowIfNull(serviceProvider);
        this._agent = agent;
        this._serviceProvider = serviceProvider;
        this._runOptionsFactory = (mapOptions ?? new OpenAIResponsesMapOptions()).RunOptionsFactory;
    }

    public ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
        => ValueTask.FromResult(this.ValidateRunOptions(request));

    public async ValueTask DeleteResponseStateAsync(
        string responseId, CreateResponse request, Task? completionTask = null, CancellationToken cancellationToken = default)
    {
        AgentSessionStore? sessionStore = this.ResolveSessionStore(this._agent);
        if (sessionStore is not null)
        {
            // Avoid a late save recreating the snapshot after it has been deleted.
            if (completionTask is not null)
            {
                await completionTask.WaitAsync(cancellationToken).ConfigureAwait(false);
            }

            await sessionStore.DeleteSessionAsync(this._agent, responseId, cancellationToken).ConfigureAwait(false);
        }
    }

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
        AgentSessionStore? sessionStore = this.ResolveSessionStore(this._agent);

        AgentSession? session = null;
        if (sessionStore is not null)
        {
            string agentSessionId = HostedAgentSessionKey.Resolve(
                request.Conversation?.Id, request.PreviousResponseId, context.ResponseId);
            session = await sessionStore.GetSessionAsync(this._agent, agentSessionId, cancellationToken).ConfigureAwait(false);
        }

        var messages = new List<ChatMessage>();

        // A restored session owns history and pending approvals. Replaying the conversation
        // transcript would duplicate messages and can resubmit approvals that were already handled.
        if (sessionStore is null && conversationHistory is not null)
        {
            messages.AddRange(conversationHistory);
        }

        foreach (var inputMessage in request.Input.GetInputMessages())
        {
            messages.Add(inputMessage.ToChatMessage());
        }

        StreamingResponseCompleted? completedEvent = null;
        await foreach (var streamingEvent in this._agent.RunStreamingAsync(messages, session, options, cancellationToken)
            .ToStreamingResponseAsync(request, context, cancellationToken)
            .ConfigureAwait(false))
        {
            if (sessionStore is not null && streamingEvent is StreamingResponseCompleted completed)
            {
                completedEvent = completed;
                continue;
            }

            yield return streamingEvent;
        }

        if (completedEvent is not null && sessionStore is not null && session is not null)
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Response IDs are immutable snapshots so independent continuations can branch.
            // A conversation ID is a mutable head that advances after each successful turn.
            if (request.Store is not false)
            {
                await sessionStore.SaveSessionAsync(this._agent, context.ResponseId, session, cancellationToken).ConfigureAwait(false);
                cancellationToken.ThrowIfCancellationRequested();
            }

            if (request.Conversation?.Id is { } conversationId)
            {
                await sessionStore.SaveSessionAsync(this._agent, conversationId, session, cancellationToken).ConfigureAwait(false);
                cancellationToken.ThrowIfCancellationRequested();
            }

            // Publish completion only after persistence, so an immediate approval can restore it.
            yield return completedEvent;
        }
    }

    private AgentSessionStore? ResolveSessionStore(AIAgent agent)
    {
        // The resolved agent, not a request-supplied name, determines which store to use.
        AgentSessionStore? store = this._serviceProvider.GetKeyedService<AgentSessionStore>(agent.Name)
            ?? this._serviceProvider.GetService<AgentSessionStore>();
        if (store is null || store.GetService<IsolationKeyScopedAgentSessionStore>() is not null)
        {
            return store;
        }

        AgentIsolationKeyProvider? isolationKeyProvider = this._serviceProvider.GetService<AgentIsolationKeyProvider>();
        return new IsolationKeyScopedAgentSessionStore(store, isolationKeyProvider, new() { Strict = isolationKeyProvider is not null });
    }
}
