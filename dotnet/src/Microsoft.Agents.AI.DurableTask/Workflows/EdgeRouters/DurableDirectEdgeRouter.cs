// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.DurableTask.Workflows.EdgeRouters;

/// <summary>
/// Routes messages from a source executor to a single target executor with optional condition evaluation.
/// </summary>
internal sealed class DurableDirectEdgeRouter : IDurableEdgeRouter
{
    private readonly string _sourceId;
    private readonly string _sinkId;
    private readonly Func<object?, bool>? _condition;
    private readonly Type? _sourceOutputType;

    /// <summary>
    /// Initializes a new instance of <see cref="DurableDirectEdgeRouter"/>.
    /// </summary>
    /// <param name="sourceId">The source executor ID.</param>
    /// <param name="sinkId">The target executor ID.</param>
    /// <param name="condition">Optional condition function to evaluate before routing.</param>
    /// <param name="sourceOutputType">The output type of the source executor for deserialization.</param>
    internal DurableDirectEdgeRouter(
        string sourceId,
        string sinkId,
        Func<object?, bool>? condition,
        Type? sourceOutputType)
    {
        this._sourceId = sourceId;
        this._sinkId = sinkId;
        this._condition = condition;
        this._sourceOutputType = sourceOutputType;
    }

    /// <inheritdoc />
    public void RouteMessage(
        DurableMessageEnvelope envelope,
        Dictionary<string, Queue<DurableMessageEnvelope>> messageQueues,
        ILogger logger)
    {
        if (this._condition is not null)
        {
            try
            {
                object? messageObj = DeserializeForCondition(envelope.Message, this._sourceOutputType);
                if (!this._condition(messageObj))
                {
                    if (logger.IsEnabled(LogLevel.Debug))
                    {
                        logger.LogDebug(
                            "Edge {Source} -> {Sink}: condition returned false, skipping",
                            this._sourceId,
                            this._sinkId);
                    }

                    return;
                }
            }
            catch (Exception ex)
            {
                logger.LogWarning(
                    ex,
                    "Failed to evaluate condition for edge {Source} -> {Sink}, skipping",
                    this._sourceId,
                    this._sinkId);
                return;
            }
        }

        if (logger.IsEnabled(LogLevel.Debug))
        {
            logger.LogDebug("Edge {Source} -> {Sink}: routing message", this._sourceId, this._sinkId);
        }

        EnqueueMessage(messageQueues, this._sinkId, envelope);
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static object? DeserializeForCondition(string json, Type? targetType)
    {
        if (string.IsNullOrEmpty(json))
        {
            return null;
        }

        try
        {
            return targetType is null
                ? JsonSerializer.Deserialize<object>(json)
                : JsonSerializer.Deserialize(json, targetType);
        }
        catch (JsonException)
        {
            return json;
        }
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
