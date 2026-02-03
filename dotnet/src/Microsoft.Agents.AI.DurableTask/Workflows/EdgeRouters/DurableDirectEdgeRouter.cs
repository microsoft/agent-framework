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
                    logger.LogEdgeConditionFalse(this._sourceId, this._sinkId);
                    return;
                }
            }
            catch (Exception ex)
            {
                logger.LogEdgeConditionEvaluationFailed(ex, this._sourceId, this._sinkId);
                return;
            }
        }

        logger.LogEdgeRoutingMessage(this._sourceId, this._sinkId);
        EnqueueMessage(messageQueues, this._sinkId, envelope);
    }

    /// <summary>
    /// Deserializes a JSON message to an object for condition evaluation.
    /// </summary>
    /// <remarks>
    /// Messages travel through the durable workflow as serialized JSON strings, but condition
    /// delegates need typed objects to evaluate (e.g., order => order.Status == "Approved").
    /// This method converts the JSON back to an object the condition delegate can evaluate.
    /// </remarks>
    /// <param name="json">The JSON string representation of the message.</param>
    /// <param name="targetType">
    /// The expected type of the message. When provided, enables strongly-typed deserialization
    /// so the condition function receives the correct type to evaluate against.
    /// </param>
    /// <returns>
    /// The deserialized object, or null if the JSON is empty.
    /// </returns>
    /// <exception cref="JsonException">Thrown when the JSON is invalid or cannot be deserialized to the target type.</exception>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types registered at startup.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types registered at startup.")]
    private static object? DeserializeForCondition(string json, Type? targetType)
    {
        if (string.IsNullOrEmpty(json))
        {
            return null;
        }

        // If we know the source executor's output type, deserialize to that specific type
        // so the condition function can access strongly-typed properties.
        // Otherwise, deserialize as a generic object for basic inspection.
        return targetType is null
            ? JsonSerializer.Deserialize<object>(json)
            : JsonSerializer.Deserialize(json, targetType);
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
