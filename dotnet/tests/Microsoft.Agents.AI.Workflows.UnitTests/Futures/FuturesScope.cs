// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.UnitTests.Futures;

/// <summary>
/// Sets <see cref="Workflows.Futures.EnableAgentResponseOutputTaggingAndFiltering"/> for
/// the lifetime of the scope, restoring the prior value on dispose. Pair every use with
/// <c>using</c> and run inside the <c>FuturesSerial</c> xUnit collection to avoid leaking
/// state across parallel tests.
/// </summary>
internal sealed class FuturesScope : IDisposable
{
    private readonly bool _previous;

    public FuturesScope(bool enabled)
    {
        this._previous = Workflows.Futures.EnableAgentResponseOutputTaggingAndFiltering;
        Workflows.Futures.EnableAgentResponseOutputTaggingAndFiltering = enabled;
    }

    public void Dispose()
    {
        Workflows.Futures.EnableAgentResponseOutputTaggingAndFiltering = this._previous;
    }
}
