// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Executes a workflow step that incrementally aggregates input messages using a user-provided aggregation function.
/// </summary>
/// <remarks>The aggregate state is persisted and restored automatically during workflow checkpointing. This
/// executor is suitable for scenarios where stateful, incremental aggregation of messages is required, such as running
/// totals or event accumulation.</remarks>
/// <typeparam name="TInput">The type of input messages to be processed and aggregated.</typeparam>
/// <typeparam name="TAggregate">The type representing the aggregate state produced by the aggregator function.</typeparam>
/// <param name="id">The unique identifier for this executor instance.</param>
/// <param name="aggregator">A function that computes the new aggregate state from the previous aggregate and the current input message. The
/// function receives the current aggregate (or null if this is the first message) and the input message, and returns
/// the updated aggregate.</param>
/// <param name="options">Optional configuration settings for the executor. If null, default options are used.</param>
/// <seealso cref="StreamingAggregators"/>
public class AggregatingExecutor<TInput, TAggregate>(string id,
    Func<TAggregate?, TInput, TAggregate?> aggregator,
    ExecutorOptions? options = null) : Executor<TInput, TAggregate?>(id, options)
{
    private const string AggregateStateKey = "Aggregate";
    private TAggregate? _runningAggregate;

    /// <inheritdoc/>
    public override ValueTask<TAggregate?> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._runningAggregate = aggregator(this._runningAggregate, message);
        return new(this._runningAggregate);
    }

    /// <inheritdoc/>
    protected internal override async ValueTask OnCheckpointingAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await context.QueueStateUpdateAsync(AggregateStateKey, this._runningAggregate, cancellationToken: cancellationToken).ConfigureAwait(false);

        await base.OnCheckpointingAsync(context, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    protected internal override async ValueTask OnCheckpointRestoredAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await base.OnCheckpointRestoredAsync(context, cancellationToken).ConfigureAwait(false);

        this._runningAggregate = await context.ReadStateAsync<TAggregate>(AggregateStateKey, cancellationToken: cancellationToken).ConfigureAwait(false);
    }
}
