// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.AgentHooks;

/// <summary>
/// Collects a guarded run's durable persistence side effects so they only execute after
/// the covering verdict permits the content.
/// </summary>
/// <remarks>
/// The .NET equivalent of the Python feature's run persistence gate, radically simplified
/// by construction ownership: the gate is consulted only by the gating provider wrappers
/// that the agent-hooks factory itself installed on its own agent, so nested or sibling
/// agents (which have their own providers) always persist inline at their own run
/// boundaries, with no run-identity bookkeeping.
/// </remarks>
internal sealed class RunPersistenceGate
{
    private readonly object _lock = new();
    private List<Func<CancellationToken, ValueTask>>? _pending;

    /// <summary>Queue one deferred persistence callback.</summary>
    public void Collect(Func<CancellationToken, ValueTask> persist)
    {
        lock (this._lock)
        {
            (this._pending ??= []).Add(persist);
        }
    }

    /// <summary>Execute the deferred persistence in order (the covering verdict permitted the content).</summary>
    public async ValueTask FlushAsync(CancellationToken cancellationToken)
    {
        List<Func<CancellationToken, ValueTask>>? pending;
        lock (this._lock)
        {
            pending = this._pending;
            this._pending = null;
        }

        if (pending is not null)
        {
            foreach (var persist in pending)
            {
                await persist(cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <summary>Discard the deferred persistence (the covering verdict denied the content).</summary>
    public void Drop()
    {
        lock (this._lock)
        {
            this._pending = null;
        }
    }
}
