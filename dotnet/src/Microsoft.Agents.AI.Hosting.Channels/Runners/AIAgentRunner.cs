// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// Default <see cref="IHostedTargetRunner"/> for <see cref="AIAgent"/> targets. Coerces
/// <see cref="ChannelRequest.Input"/> into the agent's <c>RunAsync</c> message shape, resolves an
/// <see cref="AgentSession"/> from the request's isolation key (cached per active session alias), and wraps
/// the response in <see cref="HostedRunResult{TResult}"/>.
/// </summary>
/// <remarks>
/// Session continuity is the ADR-0027 core feature: identical <see cref="ChannelSession.IsolationKey"/>
/// values resolve to the same cached <see cref="AgentSession"/>; <see cref="AgentFrameworkHost.ResetSessionAsync"/>
/// rotates the alias so the next run starts a fresh session. Cache is in-process for this slice.
/// </remarks>
public sealed class AIAgentRunner : IHostedTargetRunner
{
    private readonly AIAgent _agent;
    private readonly IHostStateStore _stateStore;
    private readonly ConcurrentDictionary<string, Task<AgentSession>> _sessions = new(StringComparer.Ordinal);

    /// <summary>Initializes a new instance.</summary>
    public AIAgentRunner(AIAgent agent, IHostStateStore stateStore)
    {
        this._agent = Throw.IfNull(agent);
        this._stateStore = Throw.IfNull(stateStore);
    }

    /// <inheritdoc />
    public async ValueTask<HostedRunResult> RunAsync(ChannelRequest request, CancellationToken cancellationToken)
    {
        Throw.IfNull(request);
        var messages = CoerceToMessages(request.Input);
        var session = await this.ResolveSessionAsync(request, cancellationToken).ConfigureAwait(false);
        var runOptions = request.Options is null ? null : new ChatClientAgentRunOptions(request.Options);
        var response = await this._agent.RunAsync(messages, session, runOptions, cancellationToken).ConfigureAwait(false);
        return new HostedRunResult<AgentResponse>(response)
        {
            Session = request.Session,
        };
    }

    /// <inheritdoc />
    public async IAsyncEnumerable<HostedStreamItem> StreamAsync(
        ChannelRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        Throw.IfNull(request);
        var messages = CoerceToMessages(request.Input);
        var session = await this.ResolveSessionAsync(request, cancellationToken).ConfigureAwait(false);
        var runOptions = request.Options is null ? null : new ChatClientAgentRunOptions(request.Options);

        AgentResponseUpdate? final = null;
        await foreach (var update in this._agent.RunStreamingAsync(messages, session, runOptions, cancellationToken).ConfigureAwait(false))
        {
            final = update;
            yield return new HostedStreamUpdate(update);
        }

        var aggregate = final is null
            ? new HostedRunResult<AgentResponseUpdate?>(null) { Session = request.Session }
            : (HostedRunResult)new HostedRunResult<AgentResponseUpdate>(final) { Session = request.Session };
        yield return new HostedStreamCompleted(aggregate);
    }

    private async ValueTask<AgentSession?> ResolveSessionAsync(ChannelRequest request, CancellationToken cancellationToken)
    {
        if (request.SessionMode == SessionMode.Disabled)
        {
            return null;
        }

        var isolationKey = request.Session?.IsolationKey;
        if (string.IsNullOrEmpty(isolationKey))
        {
            if (request.SessionMode == SessionMode.Required)
            {
                throw new InvalidOperationException(
                    "SessionMode.Required: the request must carry a ChannelSession.IsolationKey to resolve or create a session, but none was supplied.");
            }

            return null;
        }

        var alias = await this._stateStore.GetActiveSessionAliasAsync(isolationKey, cancellationToken).ConfigureAwait(false)
            ?? isolationKey;

        return await this._sessions.GetOrAdd(alias, _ => this._agent.CreateSessionAsync(CancellationToken.None).AsTask()).ConfigureAwait(false);
    }

    private static ChatMessage[] CoerceToMessages(object input)
    {
        return input switch
        {
            string s => [new ChatMessage(ChatRole.User, s)],
            ChatMessage cm => [cm],
            IEnumerable<ChatMessage> seq => seq.ToArray(),
            _ => throw new ArgumentException(
                $"AIAgentRunner cannot coerce input of type '{input?.GetType().FullName ?? "<null>"}' into ChatMessage[]. " +
                "Channels should normalize input to string, ChatMessage, or IEnumerable<ChatMessage> before calling RunAsync.",
                nameof(input)),
        };
    }
}
