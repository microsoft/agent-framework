// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Wraps an <see cref="AIContextProvider"/> of the guarded agent so its run-end durable
/// writes defer behind the run's <c>output</c> verdict, mirroring the history gating.
/// </summary>
internal sealed class AgentHooksGatingAIContextProvider : AIContextProvider
{
    private readonly AIContextProvider _inner;

    /// <summary>The installation this wrapper belongs to (ownership check for re-wrapping foreign wrappers).</summary>
    internal AgentHooksConfiguration Configuration { get; }
    private readonly bool _endOfRunDeferral;

    internal AgentHooksGatingAIContextProvider(
        AIContextProvider inner, AgentHooksConfiguration configuration, bool perServiceCallPersistence)
    {
        this._inner = inner;
        this.Configuration = configuration;
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
            // See the history wrapper: failure notifications pass through for cleanup,
            // redacted (empty request messages) once a run-level deny or halt stands.
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
