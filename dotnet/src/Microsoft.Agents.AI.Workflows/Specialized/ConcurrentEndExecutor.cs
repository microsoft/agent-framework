// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Specialized;

/// <summary>
/// Provides an executor that accepts the output messages from each of the concurrent agents
/// and produces a result list containing the last message from each.
/// </summary>
internal sealed class ConcurrentEndExecutor : Executor, IResettableExecutor
{
    public const string ExecutorId = "ConcurrentEnd";

    private readonly int _expectedInputs;
    private readonly Func<IList<List<ChatMessage>>, List<ChatMessage>> _aggregator;
    private List<List<ChatMessage>> _allResults;
    private int _remaining;

    public ConcurrentEndExecutor(int expectedInputs, Func<IList<List<ChatMessage>>, List<ChatMessage>> aggregator) : base(ExecutorId)
    {
        this._expectedInputs = expectedInputs;
        this._aggregator = Throw.IfNull(aggregator);

        this._allResults = new List<List<ChatMessage>>(expectedInputs);
        this._remaining = expectedInputs;
    }

    private void Reset()
    {
        this._allResults = new List<List<ChatMessage>>(this._expectedInputs);
        this._remaining = this._expectedInputs;
    }

    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder) =>
        routeBuilder.AddHandler<List<ChatMessage>>(async (messages, context, cancellationToken) =>
        {
            // TODO: https://github.com/microsoft/agent-framework/issues/784
            // This locking should not be necessary.
            bool done;
            lock (this._allResults)
            {
                this._allResults.Add(messages);
                done = --this._remaining == 0;
            }

            if (done)
            {
                this._remaining = this._expectedInputs;

                var results = this._allResults;
                this._allResults = new List<List<ChatMessage>>(this._expectedInputs);
                await context.YieldOutputAsync(this._aggregator(results), cancellationToken).ConfigureAwait(false);
            }
        });

    public ValueTask ResetAsync()
    {
        this.Reset();
        return default;
    }
}
