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

    /// <summary>
    /// Initializes a new instance of <see cref="DurableFanOutEdgeRouter"/>.
    /// </summary>
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="targetRouters">The routers for each target executor.</param>
    internal DurableFanOutEdgeRouter(string sourceId, List<IDurableEdgeRouter> targetRouters)
    {
        this._sourceId = sourceId;
        this._targetRouters = targetRouters;
    }

    /// <inheritdoc />
    public void RouteMessage(
        DurableMessageEnvelope envelope,
        Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues,
        ILogger logger)
    {
        if (logger.IsEnabled(LogLevel.Debug))
        {
            logger.LogDebug("Fan-Out from {Source}: routing to {Count} targets", this._sourceId, this._targetRouters.Count);
        }

        foreach (IDurableEdgeRouter targetRouter in this._targetRouters)
        {
            targetRouter.RouteMessage(envelope, messageQueues, logger);
        }
    }
}
