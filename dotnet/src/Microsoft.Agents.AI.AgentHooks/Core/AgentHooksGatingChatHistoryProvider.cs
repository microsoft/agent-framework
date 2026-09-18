// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Wraps the guarded agent's <see cref="ChatHistoryProvider"/> so that durable history
/// writes obey verdict-before-durability: end-of-run writes defer behind the run's
/// <c>output</c> verdict (flushed post-transform, dropped on deny), while writes already
/// covered by their own <c>post_model_call</c> verdict (per-service-call persistence)
/// run inline.
/// </summary>
internal sealed class AgentHooksGatingChatHistoryProvider : ChatHistoryProvider
{
    private readonly ChatHistoryProvider _inner;

    /// <summary>The installation this wrapper belongs to (ownership check for re-wrapping foreign wrappers).</summary>
    internal AgentHooksConfiguration Configuration { get; }
    private readonly bool _endOfRunDeferral;

    internal AgentHooksGatingChatHistoryProvider(
        ChatHistoryProvider inner, AgentHooksConfiguration configuration, bool perServiceCallPersistence)
    {
        this._inner = inner;
        this.Configuration = configuration;
        this._endOfRunDeferral = !perServiceCallPersistence;
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._inner.StateKeys;

    /// <inheritdoc />
    protected override ValueTask<IEnumerable<ChatMessage>> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        this._inner.InvokingAsync(context, cancellationToken);

    /// <inheritdoc />
    protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            // Failure notifications are cleanup control flow (the default provider
            // stores nothing for them) and pass through — but once a run-level deny or
            // halt is standing they are REDACTED: the notification would carry the
            // denied turn's request messages, which must not reach provider code, while
            // providers that release per-run resources on the failure signal must still
            // be notified.
            var state = AgentHooksRunState.Current;
            if (state is not null && ReferenceEquals(state.Configuration, this.Configuration) &&
                (state.Denied || state.Halted is not null))
            {
                context = new InvokedContext(context.Agent, context.Session, [], context.InvokeException);
            }

            return this._inner.InvokedAsync(context, cancellationToken);
        }

        return PersistenceGating.GateAsync(
            this.Configuration,
            this._endOfRunDeferral,
            (state, ct) =>
            {
                // A deferred (end-of-run) persist substitutes the verdicted response
                // messages: for streamed runs the captured context holds the inner
                // agent's own pre-verdict message list, and the output transform must
                // be what becomes durable.
                var effective = state?.VerdictedResponseMessages is { } verdicted && context.ResponseMessages is not null
                    ? new InvokedContext(context.Agent, context.Session, context.RequestMessages, verdicted)
                    : context;
                return this._inner.InvokedAsync(effective, ct);
            },
            cancellationToken);
    }

    /// <inheritdoc />
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey) ?? this._inner.GetService(serviceType, serviceKey);
}
