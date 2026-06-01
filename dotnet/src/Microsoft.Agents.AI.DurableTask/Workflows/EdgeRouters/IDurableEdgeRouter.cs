// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;

/// <summary>
/// Defines the contract for routing messages through workflow edges in durable orchestrations.
/// </summary>
/// <remarks>
/// Implementations include <see cref="DurableDirectEdgeRouter"/> for single-target routing
/// and <see cref="DurableFanOutEdgeRouter"/> for multi-target fan-out patterns.
/// </remarks>
internal interface IDurableEdgeRouter
{
    /// <summary>
    /// Routes a message from the source executor to its target(s).
    /// </summary>
    /// <param name="envelope">The message envelope containing the message and metadata.</param>
    /// <param name="messageQueues">The message queues to enqueue messages into.</param>
    /// <param name="logger">The logger for tracing.</param>
    void RouteMessage(
        DurableMessageEnvelope envelope,
        Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues,
        ILogger logger);
}
