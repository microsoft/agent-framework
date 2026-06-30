// Copyright (c) Microsoft. All rights reserved.

// How WorkflowGraphInfo maps to DurableEdgeMap at runtime.
// For a workflow like below:
//
//     [A] ──► [B] ──► [C] ──► [E]
//              │               ▲
//              └──► [D] ──────┘
//                (condition: x => x.NeedsReview)
//
//  WorkflowGraphInfo                          DurableEdgeMap
//  ┌──────────────────────────┐               ┌──────────────────────────────────────┐
//  │ Successors:              │               │ _routersBySource:                    │
//  │   A → [B]                │──constructs──►│   A → [DirectRouter(A→B)]            │
//  │   B → [C, D]             │               │   B → [FanOutRouter([C, D])]         │
//  │   C → [E]                │               │   C → [DirectRouter(C→E)]            │
//  │   D → [E]                │               │   D → [DirectRouter(D→E)]            │
//  └──────────────────────────┘               │                                      │
//  ┌──────────────────────────┐               │ _predecessorCounts:                  │
//  │ Predecessors:            │               │   A → 0                              │
//  │   E → [C, D]  (fan-in!)  │──constructs──►│   B → 1, C → 1, D → 1                │
//  └──────────────────────────┘               │   E → 2  ◄── IsFanInExecutor = true  │
//                                             └──────────────────────────────────────┘
//
// Usage during superstep execution (continuing the example):
//
//  1. EnqueueInitialInput(msg) ──► MessageQueues["A"].Enqueue(envelope)
//
//  2. After B completes, RouteMessage("B", resultB) ──► _routersBySource["B"]
//       │
//       ▼
//     FanOutRouter (B has 2 successors)
//       ├─► DirectRouter(B→C)  ──► no condition  ──► enqueue to C
//       └─► DirectRouter(B→D)  ──► evaluate x => x.NeedsReview ──► enqueue to D (or skip)
//
//  3. Before superstep 4, IsFanInExecutor("E") returns true (count=2)
//       → CollectExecutorInputs aggregates C and D results into ["resultC","resultD"]

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;

/// <summary>
/// Manages message routing through workflow edges for durable orchestrations.
/// </summary>
/// <remarks>
/// <para>
/// This is the durable equivalent of <c>EdgeMap</c> in the in-process runner.
/// It is constructed from <see cref="WorkflowGraphInfo"/> (produced by <see cref="WorkflowAnalyzer.BuildGraphInfo"/>)
/// and converts the static graph structure into an active routing layer used during superstep execution.
/// </para>
/// <para>
/// <b>What it stores:</b>
/// </para>
/// <list type="bullet">
/// <item><description><c>_routersBySource</c> — For each source executor, a list of <see cref="IDurableEdgeRouter"/> instances
/// that know how to deliver messages to successor executors. When a source has multiple successors, a single
/// <see cref="DurableFanOutEdgeRouter"/> wraps the individual <see cref="DurableDirectEdgeRouter"/> instances.</description></item>
/// <item><description><c>_predecessorCounts</c> — The number of predecessors for each executor, used to detect
/// fan-in points where multiple incoming messages should be aggregated before execution.</description></item>
/// <item><description><c>_startExecutorId</c> — The entry-point executor that receives the initial workflow input.</description></item>
/// </list>
/// <para>
/// <b>How it is used during execution:</b>
/// </para>
/// <list type="number">
/// <item><description><see cref="EnqueueInitialInput"/> seeds the start executor's queue before the first superstep.</description></item>
/// <item><description>After each superstep, <c>DurableWorkflowRunner.RouteOutputToSuccessors</c> calls
/// <see cref="RouteMessage"/> which looks up the routers for the completed executor and forwards the
/// result to successor queues. Each router may evaluate an edge condition before enqueueing.</description></item>
/// <item><description><see cref="IsFanInExecutor"/> is checked during input collection to decide whether
/// to aggregate multiple queued messages into a single JSON array before dispatching.</description></item>
/// </list>
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

            // A switch (AddSwitch) or target-selecting fan-out edge is represented as a single fan-out edge
            // with an assigner. A source can also declare such selector edges alongside ordinary direct or
            // plain fan-out edges. Because the graph flattens every edge's targets into a single successor
            // list, we build one selector-aware fan-out router per selector routing (so only the chosen
            // targets receive the message) and ordinary direct routers for the remaining sibling edges, so
            // none of them are dropped. This mirrors the in-process runner, which creates one runner per edge.
            if (graphInfo.SelectiveFanOuts.TryGetValue(sourceId, out List<SelectiveFanOut>? selectiveFanOuts)
                && selectiveFanOuts.Count > 0)
            {
                List<IDurableEdgeRouter> sourceRouters = [];

                // Count how many times each target is claimed by a selector. The flattened successor list can
                // contain the same target more than once (a selector case and a sibling edge can point at the
                // same executor), so we consume one occurrence per selector claim rather than skipping the
                // target entirely, ensuring sibling edges to a selector's target are still wired.
                Dictionary<string, int> selectorSinkCounts = [];
                foreach (SelectiveFanOut selectiveFanOut in selectiveFanOuts)
                {
                    List<IDurableEdgeRouter> orderedRouters = [];
                    foreach (string sinkId in selectiveFanOut.SinkIds)
                    {
                        orderedRouters.Add(new DurableDirectEdgeRouter(sourceId, sinkId, condition: null, sourceOutputType));
                        selectorSinkCounts[sinkId] = selectorSinkCounts.GetValueOrDefault(sinkId) + 1;
                    }

                    sourceRouters.Add(new DurableFanOutEdgeRouter(sourceId, orderedRouters, selectiveFanOut.Assigner, sourceOutputType));
                }

                // Sibling edges from the same source (direct or plain fan-out, possibly conditional) that are
                // not part of any selector still need to deliver.
                foreach (string sinkId in successorIds)
                {
                    // Consume one selector occurrence of this target; any remaining occurrence is a sibling edge.
                    if (selectorSinkCounts.TryGetValue(sinkId, out int remaining) && remaining > 0)
                    {
                        selectorSinkCounts[sinkId] = remaining - 1;
                        continue;
                    }

                    graphInfo.EdgeConditions.TryGetValue((sourceId, sinkId), out Func<object?, bool>? siblingCondition);
                    sourceRouters.Add(new DurableDirectEdgeRouter(sourceId, sinkId, siblingCondition, sourceOutputType));
                }

                this._routersBySource[sourceId] = sourceRouters;

                continue;
            }

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

        // Store predecessor counts for fan-in detection. Count distinct source executors: a single source can
        // reach the same target through more than one edge (for example a switch case plus a sibling direct
        // edge to the same executor), and those repeated deliveries must not be mistaken for a fan-in. True
        // fan-in aggregates deliveries from multiple distinct sources, mirroring the in-process FanInEdgeData
        // contract, so a target fed twice by the same source still runs once per delivery.
        foreach (KeyValuePair<string, List<string>> entry in graphInfo.Predecessors)
        {
            this._predecessorCounts[entry.Key] = entry.Value.Distinct().Count();
        }
    }

    /// <summary>
    /// Routes a message from a source executor to its successors.
    /// </summary>
    /// <remarks>
    /// Called by <c>DurableWorkflowRunner.RouteOutputToSuccessors</c> after each superstep.
    /// Wraps the message in a <see cref="DurableMessageEnvelope"/> and delegates to the
    /// appropriate <see cref="IDurableEdgeRouter"/>(s) for the source executor. Each router
    /// may evaluate an edge condition and, if satisfied, enqueue the envelope into the
    /// target executor's message queue for the next superstep.
    /// </remarks>
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
