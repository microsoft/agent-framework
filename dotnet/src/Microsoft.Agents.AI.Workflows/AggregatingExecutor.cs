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
/// <param name="declareCrossRunShareable">Declare that this executor may be used simultaneously by multiple runs safely.</param>
/// <seealso cref="StreamingAggregators"/>
public class AggregatingExecutor<TInput, TAggregate>(string id,
    Func<TAggregate?, TInput, TAggregate?> aggregator,
    ExecutorOptions? options = null,
    bool declareCrossRunShareable = false) : Executor<TInput, TAggregate?>(id, options, declareCrossRunShareable)
{
    private const string AggregateStateKey = "Aggregate";

    /// <inheritdoc/>
    public override async ValueTask<TAggregate?> HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken)
    {
        TAggregate? runningAggregate = default;
        await context.InvokeWithStateAsync<PortableValue?>(InvokeAggregatorAsync, AggregateStateKey, cancellationToken: cancellationToken)
                     .ConfigureAwait(false);

        return runningAggregate;

        ValueTask<PortableValue?> InvokeAggregatorAsync(PortableValue? maybeState, IWorkflowContext context, CancellationToken cancellationToken)
        {
            if (maybeState == null || !maybeState.Is(out runningAggregate))
            {
                runningAggregate = default;
            }

            runningAggregate = aggregator(runningAggregate, message);

            if (runningAggregate == null)
            {
                return new((PortableValue?)null);
            }

            return new(new PortableValue(runningAggregate));
        }
    }
}
