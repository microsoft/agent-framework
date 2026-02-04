// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;

/// <summary>
/// Manages message routing through workflow edges for durable orchestrations.
/// </summary>
/// <remarks>
/// This is the durable equivalent of <c>EdgeMap</c> in the in-process runner.
/// It creates and manages edge routers for each source executor, enabling
/// message-driven workflow execution.
/// </remarks>
internal sealed class DurableEdgeMap
{
    private readonly Dictionary<string, List<IDurableEdgeRouter>> _routersBySource = [];
    private readonly Dictionary<string, int> _predecessorCounts = [];
    private readonly string _startExecutorId;

    /// <summary>
    /// Initializes a new instance of <see cref="DurableEdgeMap"/> from workflow graph info.
    /// </summary>
    /// <param name="graphInfo">The workflow graph information containing routing structure.</param>
    internal DurableEdgeMap(WorkflowGraphInfo graphInfo)
    {
        ArgumentNullException.ThrowIfNull(graphInfo);

        this._startExecutorId = graphInfo.StartExecutorId;

        // Build edge routers for each source executor
        foreach (KeyValuePair<string, List<string>> entry in graphInfo.Successors)
        {
            string sourceId = entry.Key;
            List<string> successorIds = entry.Value;

            if (successorIds.Count == 0)
            {
                continue;
            }

            graphInfo.ExecutorOutputTypes.TryGetValue(sourceId, out Type? sourceOutputType);

            List<IDurableEdgeRouter> routers = [];
            foreach (string sinkId in successorIds)
            {
                graphInfo.EdgeConditions.TryGetValue((sourceId, sinkId), out Func<object?, bool>? condition);

                routers.Add(new DurableDirectEdgeRouter(sourceId, sinkId, condition, sourceOutputType));
            }

            // If multiple successors, wrap in a fan-out router
            if (routers.Count > 1)
            {
                this._routersBySource[sourceId] = [new DurableFanOutEdgeRouter(sourceId, routers)];
            }
            else
            {
                this._routersBySource[sourceId] = routers;
            }
        }

        // Store predecessor counts for fan-in detection
        foreach (KeyValuePair<string, List<string>> entry in graphInfo.Predecessors)
        {
            this._predecessorCounts[entry.Key] = entry.Value.Count;
        }
    }

    /// <summary>
    /// Routes a message from a source executor to its successors.
    /// </summary>
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="message">The serialized message to route.</param>
    /// <param name="inputTypeName">The type name of the message.</param>
    /// <param name="messageQueues">The message queues to enqueue messages into.</param>
    /// <param name="logger">The logger for tracing.</param>
    internal void RouteMessage(
        string sourceId,
        string message,
        string? inputTypeName,
        Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues,
        ILogger logger)
    {
        if (!this._routersBySource.TryGetValue(sourceId, out List<IDurableEdgeRouter>? routers))
        {
            return;
        }

        DurableMessageEnvelope envelope = DurableMessageEnvelope.Create(message, inputTypeName, sourceId);

        foreach (IDurableEdgeRouter router in routers)
        {
            router.RouteMessage(envelope, messageQueues, logger);
        }
    }

    /// <summary>
    /// Enqueues the initial workflow input to the start executor.
    /// </summary>
    /// <param name="message">The serialized initial input message.</param>
    /// <param name="messageQueues">The message queues to enqueue into.</param>
    /// <remarks>
    /// This method is used only at workflow startup to provide input to the first executor.
    /// No input type hint is required because the start executor determines its expected input type from its own <c>InputTypes</c> configuration.
    /// </remarks>
    internal void EnqueueInitialInput(
        string message,
        Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues)
    {
        DurableMessageEnvelope envelope = DurableMessageEnvelope.Create(message, inputTypeName: null);
        EnqueueMessage(messageQueues, this._startExecutorId, envelope);
    }

    /// <summary>
    /// Determines if an executor is a fan-in point (has multiple predecessors).
    /// </summary>
    /// <param name="executorId">The executor ID to check.</param>
    /// <returns><c>true</c> if the executor has multiple predecessors; otherwise, <c>false</c>.</returns>
    internal bool IsFanInExecutor(string executorId)
    {
        return this._predecessorCounts.TryGetValue(executorId, out int count) && count > 1;
    }

    private static void EnqueueMessage(
        Dictionary<string, Queue<DurableMessageEnvelope>> queues,
        string executorId,
        DurableMessageEnvelope envelope)
    {
        if (!queues.TryGetValue(executorId, out Queue<DurableMessageEnvelope>? queue))
        {
            queue = new Queue<DurableMessageEnvelope>();
            queues[executorId] = queue;
        }

        queue.Enqueue(envelope);
    }
}
