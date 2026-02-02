// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;

/// <summary>
/// Routes messages from a source executor to multiple target executors (fan-out pattern).
/// </summary>
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
