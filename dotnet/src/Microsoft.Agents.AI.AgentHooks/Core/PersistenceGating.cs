// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

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
