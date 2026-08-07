// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Shared deferral rule for the gating provider wrappers: durable writes issued inside a
/// guarded run wait behind the run's persistence gate until the covering verdict permits
/// the content; once a run-level verdict has denied, writes are refused outright.
/// </summary>
internal static class PersistenceGating
{
    /// <summary>
    /// Defer <paramref name="persist"/> behind the active run's gate when the ambient run
    /// state belongs to <paramref name="configuration"/>; run it inline otherwise.
    /// </summary>
    /// <remarks>
    /// The wrappers are installed only on the agent the agent-hooks factory itself
    /// composed, so nested or sibling agents (which have their own providers) always
    /// persist inline at their own run boundaries — no run-identity bookkeeping is
    /// needed. Per-service-call persistence never reaches this gate un-verdicted either:
    /// the per-service-call persister sits above the agent-hooks chat seam, so its writes
    /// are already covered by their own <c>post_model_call</c> verdict and are executed
    /// inline here when the end-of-run notification is skipped; a permitted
    /// per-service-call write therefore remains durable even if the run's <c>output</c>
    /// is later denied — unless a deny is already standing, in which case everything
    /// (including the denied turn's request messages) is refused.
    /// </remarks>
    public static ValueTask GateAsync(
        AgentHooksConfiguration configuration, bool endOfRunDeferral, Func<AgentHooksRunState?, CancellationToken, ValueTask> persist, CancellationToken cancellationToken)
    {
        var state = AgentHooksRunState.Current;
        if (state is null || !ReferenceEquals(state.Configuration, configuration))
        {
            return persist(null, cancellationToken);
        }

        if (state.Denied || state.Halted is not null)
        {
            // Fail closed: denied content (and the denied turn's request messages)
            // never becomes durable.
            return default;
        }

        if (endOfRunDeferral)
        {
            // The deferred callback receives the run state at flush time so it can
            // substitute the verdicted (post-transform) response messages.
            state.Gate.Collect(ct => persist(state, ct));
            return default;
        }

        return persist(null, cancellationToken);
    }
}

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
    private readonly AgentHooksConfiguration _configuration;
    private readonly bool _endOfRunDeferral;

    internal AgentHooksGatingChatHistoryProvider(
        ChatHistoryProvider inner, AgentHooksConfiguration configuration, bool perServiceCallPersistence)
    {
        this._inner = inner;
        this._configuration = configuration;
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
            // Failure notifications are content-free control flow (the default provider
            // stores nothing for them); they pass through so providers can clean up.
            return this._inner.InvokedAsync(context, cancellationToken);
        }

        return PersistenceGating.GateAsync(
            this._configuration,
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

/// <summary>
/// Wraps an <see cref="AIContextProvider"/> of the guarded agent so its run-end durable
/// writes defer behind the run's <c>output</c> verdict, mirroring the history gating.
/// </summary>
internal sealed class AgentHooksGatingAIContextProvider : AIContextProvider
{
    private readonly AIContextProvider _inner;
    private readonly AgentHooksConfiguration _configuration;
    private readonly bool _endOfRunDeferral;

    internal AgentHooksGatingAIContextProvider(
        AIContextProvider inner, AgentHooksConfiguration configuration, bool perServiceCallPersistence)
    {
        this._inner = inner;
        this._configuration = configuration;
        this._endOfRunDeferral = !perServiceCallPersistence;
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._inner.StateKeys;

    /// <inheritdoc />
    protected override ValueTask<AIContext> InvokingCoreAsync(InvokingContext context, CancellationToken cancellationToken = default) =>
        this._inner.InvokingAsync(context, cancellationToken);

    /// <inheritdoc />
    protected override ValueTask InvokedCoreAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        if (context.InvokeException is not null)
        {
            return this._inner.InvokedAsync(context, cancellationToken);
        }

        return PersistenceGating.GateAsync(
            this._configuration,
            this._endOfRunDeferral,
            (state, ct) =>
            {
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
