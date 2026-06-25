// Copyright (c) Microsoft. All rights reserved.

// Fan-out routing: one source message is forwarded to multiple targets.
// Example from a workflow like below:
//
//     [A] ──► [B] ──► [C] ──► [E]          (B→D has condition: x => x.NeedsReview)
//              │               ▲
//              └──► [D] ──────┘
//
//  B has two successors (C and D), so DurableEdgeMap wraps them:
//
//     Executor B completes with resultB (type: Order)
//       │
//       ▼
//     FanOutRouter(B)
//       ├──► DirectRouter(B→C) ──► no condition       ──► enqueue to C
//       └──► DirectRouter(B→D) ──► x => x.NeedsReview ──► enqueue to D (or skip)
//
//  Each DirectRouter independently evaluates its condition,
//  so resultB always reaches C, but only reaches D if NeedsReview is true.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;

/// <summary>
/// Routes messages from a source executor to multiple target executors (fan-out pattern).
/// </summary>
/// <remarks>
/// Created by <see cref="DurableEdgeMap"/> when a source executor has more than one successor.
/// Wraps the individual <see cref="DurableDirectEdgeRouter"/> instances and delegates
/// <see cref="RouteMessage"/> to each of them, so the same message is evaluated and
/// potentially enqueued for every target independently.
/// </remarks>
internal sealed class DurableFanOutEdgeRouter : IDurableEdgeRouter
{
    private readonly string _sourceId;
    private readonly List<IDurableEdgeRouter> _targetRouters;
    private readonly Func<object?, int, IEnumerable<int>>? _edgeAssigner;
    private readonly Type? _sourceOutputType;

    /// <summary>
    /// Initializes a new instance of <see cref="DurableFanOutEdgeRouter"/>.
    /// </summary>
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="targetRouters">The routers for each target executor.</param>
    /// <param name="edgeAssigner">
    /// Optional target selector. When provided (e.g., for a switch built via <c>AddSwitch</c>), it maps the
    /// incoming message to the indices of <paramref name="targetRouters"/> that should receive it, so only the
    /// selected targets run. When <c>null</c>, the message is forwarded to all targets.
    /// </param>
    /// <param name="sourceOutputType">
    /// The output type of the source executor, used to deserialize the JSON message before evaluating the
    /// <paramref name="edgeAssigner"/>. Ignored when <paramref name="edgeAssigner"/> is <c>null</c>.
    /// </param>
    internal DurableFanOutEdgeRouter(
        string sourceId,
        List<IDurableEdgeRouter> targetRouters,
        Func<object?, int, IEnumerable<int>>? edgeAssigner = null,
        Type? sourceOutputType = null)
    {
        this._sourceId = sourceId;
        this._targetRouters = targetRouters;
        this._edgeAssigner = edgeAssigner;
        this._sourceOutputType = sourceOutputType;
    }

    /// <inheritdoc />
    public void RouteMessage(
        DurableMessageEnvelope envelope,
        Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues,
        ILogger logger)
    {
        // No assigner: plain fan-out, forward the message to every target.
        if (this._edgeAssigner is null)
        {
            if (logger.IsEnabled(LogLevel.Debug))
            {
                logger.LogDebug("Fan-Out from {Source}: routing to {Count} targets", this._sourceId, this._targetRouters.Count);
            }

            foreach (IDurableEdgeRouter targetRouter in this._targetRouters)
            {
                targetRouter.RouteMessage(envelope, messageQueues, logger);
            }

            return;
        }

        // Assigner present (e.g., a switch): select only the matching targets, mirroring the in-process
        // FanOutEdgeRunner. The assigner returns indices into the ordered target list. Indices map directly
        // to targets with no range filtering and no de-duplication, so an out-of-range index surfaces as an
        // error (logged below) instead of being silently dropped, and duplicate indices deliver more than once.
        List<IDurableEdgeRouter> selectedRouters;
        try
        {
            object? messageObj = DurableSerialization.DeserializeMessage(envelope.Message, this._sourceOutputType);
            selectedRouters = this._edgeAssigner(messageObj, this._targetRouters.Count)
                                  .Select(index => this._targetRouters[index])
                                  .ToList();
        }
        catch (Exception ex)
        {
            logger.LogFanOutSelectorEvaluationFailed(ex, this._sourceId);
            return;
        }

        logger.LogFanOutSelectorMatched(this._sourceId, selectedRouters.Count, this._targetRouters.Count);

        foreach (IDurableEdgeRouter targetRouter in selectedRouters)
        {
            targetRouter.RouteMessage(envelope, messageQueues, logger);
        }
    }
}
