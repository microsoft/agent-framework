// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a durable workflow run that supports streaming workflow events as they occur.
/// </summary>
/// <remarks>
/// Events are detected by monitoring the orchestration's custom status at regular intervals.
/// When executors emit events via <see cref="IWorkflowContext.AddEventAsync"/> or
/// <see cref="IWorkflowContext.YieldOutputAsync"/>, they are written to the orchestration's
/// custom status and picked up by this streaming run.
/// </remarks>
[DebuggerDisplay("{WorkflowName} ({RunId})")]
internal sealed class DurableStreamingWorkflowRun : IStreamingWorkflowRun
{
    private readonly DurableTaskClient _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="DurableStreamingWorkflowRun"/> class.
    /// </summary>
    /// <param name="client">The durable task client for orchestration operations.</param>
    /// <param name="instanceId">The unique instance ID for this orchestration run.</param>
    /// <param name="workflow">The workflow being executed.</param>
    internal DurableStreamingWorkflowRun(DurableTaskClient client, string instanceId, Workflow workflow)
    {
        this._client = client;
        this.RunId = instanceId;
        this.WorkflowName = workflow.Name ?? string.Empty;
    }

    /// <inheritdoc/>
    public string RunId { get; }

    /// <summary>
    /// Gets the name of the workflow being executed.
    /// </summary>
    public string WorkflowName { get; }

    /// <summary>
    /// Gets the current execution status of the workflow run.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The current status of the durable run.</returns>
    public async ValueTask<DurableRunStatus> GetStatusAsync(CancellationToken cancellationToken = default)
    {
        OrchestrationMetadata? metadata = await this._client.GetInstanceAsync(
            this.RunId,
            getInputsAndOutputs: false,
            cancellation: cancellationToken).ConfigureAwait(false);

        if (metadata is null)
        {
            return DurableRunStatus.NotFound;
        }

        return metadata.RuntimeStatus switch
        {
            OrchestrationRuntimeStatus.Pending => DurableRunStatus.Pending,
            OrchestrationRuntimeStatus.Running => DurableRunStatus.Running,
            OrchestrationRuntimeStatus.Completed => DurableRunStatus.Completed,
            OrchestrationRuntimeStatus.Failed => DurableRunStatus.Failed,
            OrchestrationRuntimeStatus.Terminated => DurableRunStatus.Terminated,
            OrchestrationRuntimeStatus.Suspended => DurableRunStatus.Suspended,
            _ => DurableRunStatus.Unknown
        };
    }

    /// <inheritdoc/>
    public IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(CancellationToken cancellationToken = default)
        => this.WatchStreamAsync(pollingInterval: null, cancellationToken);

    /// <summary>
    /// Asynchronously streams workflow events as they occur during workflow execution.
    /// </summary>
    /// <param name="pollingInterval">The interval between status checks. Defaults to 100ms.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An asynchronous stream of <see cref="WorkflowEvent"/> objects.</returns>
    private async IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(
        TimeSpan? pollingInterval,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        TimeSpan minInterval = pollingInterval ?? TimeSpan.FromMilliseconds(100);
        TimeSpan maxInterval = TimeSpan.FromSeconds(2);
        TimeSpan currentInterval = minInterval;

        // Track how many events we've already read from custom status
        int lastReadEventIndex = 0;

        while (!cancellationToken.IsCancellationRequested)
        {
            // Poll with getInputsAndOutputs: true because SerializedCustomStatus
            // (used for event streaming) is only populated when this flag is set.
            OrchestrationMetadata? metadata = await this._client.GetInstanceAsync(
                this.RunId,
                getInputsAndOutputs: true,
                cancellation: cancellationToken).ConfigureAwait(false);

            if (metadata is null)
            {
                yield break;
            }

            bool hasNewEvents = false;

            // Always drain any unread events from custom status before checking terminal states.
            // The orchestration may complete before the next poll, so events would be lost if we
            // check terminal status first.
            if (metadata.SerializedCustomStatus is not null)
            {
                DurableWorkflowCustomStatus? customStatus = TryParseCustomStatus(metadata.SerializedCustomStatus);
                if (customStatus is not null)
                {
                    (List<WorkflowEvent> events, lastReadEventIndex) = DrainNewEvents(customStatus.Events, lastReadEventIndex);
                    foreach (WorkflowEvent evt in events)
                    {
                        hasNewEvents = true;
                        yield return evt;
                    }
                }
            }

            // Check terminal states after draining events from custom status
            if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
            {
                // The framework clears custom status on completion, so events may be in
                // SerializedOutput as a DurableWorkflowResult wrapper.
                DurableWorkflowResult? outputResult = TryParseWorkflowResult(metadata.SerializedOutput);
                if (outputResult is not null)
                {
                    (List<WorkflowEvent> events, _) = DrainNewEvents(outputResult.Events, lastReadEventIndex);
                    foreach (WorkflowEvent evt in events)
                    {
                        yield return evt;
                    }

                    yield return new DurableWorkflowCompletedEvent(outputResult.Result);
                }
                else
                {
                    yield return new DurableWorkflowCompletedEvent(metadata.SerializedOutput);
                }

                yield break;
            }

            if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
            {
                string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Workflow execution failed.";
                yield return new DurableWorkflowFailedEvent(errorMessage);
                yield break;
            }

            if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Terminated)
            {
                yield return new DurableWorkflowFailedEvent("Workflow was terminated.");
                yield break;
            }

            // Adaptive backoff: reset to minimum when events were found, increase otherwise
            currentInterval = hasNewEvents
                ? minInterval
                : TimeSpan.FromMilliseconds(Math.Min(currentInterval.TotalMilliseconds * 2, maxInterval.TotalMilliseconds));

            try
            {
                await Task.Delay(currentInterval, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                yield break;
            }
        }
    }

    /// <summary>
    /// Waits for the workflow to complete and returns the result.
    /// </summary>
    /// <typeparam name="TResult">The expected result type.</typeparam>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The result of the workflow execution.</returns>
    public async ValueTask<TResult?> WaitForCompletionAsync<TResult>(CancellationToken cancellationToken = default)
    {
        OrchestrationMetadata metadata = await this._client.WaitForInstanceCompletionAsync(
            this.RunId,
            getInputsAndOutputs: true,
            cancellation: cancellationToken).ConfigureAwait(false);

        if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
        {
            return ExtractResult<TResult>(metadata.SerializedOutput);
        }

        if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
        {
            string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Workflow execution failed.";
            throw new InvalidOperationException(errorMessage);
        }

        throw new InvalidOperationException($"Workflow ended with unexpected status: {metadata.RuntimeStatus}");
    }

    /// <summary>
    /// Deserializes and returns any events beyond <paramref name="lastReadIndex"/> from the list.
    /// </summary>
    private static (List<WorkflowEvent> Events, int UpdatedIndex) DrainNewEvents(List<string> serializedEvents, int lastReadIndex)
    {
        List<WorkflowEvent> events = [];
        while (lastReadIndex < serializedEvents.Count)
        {
            string serializedEvent = serializedEvents[lastReadIndex];
            lastReadIndex++;

            WorkflowEvent? workflowEvent = TryDeserializeEvent(serializedEvent);
            if (workflowEvent is not null)
            {
                events.Add(workflowEvent);
            }
        }

        return (events, lastReadIndex);
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow custom status.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow custom status.")]
    private static DurableWorkflowCustomStatus? TryParseCustomStatus(string serializedStatus)
    {
        try
        {
            return JsonSerializer.Deserialize(serializedStatus, DurableWorkflowJsonContext.Default.DurableWorkflowCustomStatus);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>
    /// Attempts to parse the orchestration output as a <see cref="DurableWorkflowResult"/> wrapper.
    /// </summary>
    /// <remarks>
    /// The orchestration wraps its output in a <see cref="DurableWorkflowResult"/> to include
    /// accumulated events alongside the result. The Durable Task framework's <c>DataConverter</c>
    /// serializes the string output with an extra layer of JSON encoding, so we first unwrap that.
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow result wrapper.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow result wrapper.")]
    private static DurableWorkflowResult? TryParseWorkflowResult(string? serializedOutput)
    {
        if (serializedOutput is null)
        {
            return null;
        }

        try
        {
            // The DurableDataConverter wraps string results in JSON quotes, so
            // SerializedOutput is a JSON-encoded string like "\"{ ... }\"".
            // We need to unwrap the outer JSON string first.
            string? innerJson = JsonSerializer.Deserialize<string>(serializedOutput);
            if (innerJson is null)
            {
                return null;
            }

            return JsonSerializer.Deserialize(innerJson, DurableWorkflowJsonContext.Default.DurableWorkflowResult);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>
    /// Extracts a typed result from the orchestration output, unwrapping the
    /// <see cref="DurableWorkflowResult"/> wrapper if present.
    /// Falls back to deserializing the raw output when the wrapper is absent
    /// (e.g., runs started before the wrapper was introduced).
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow result.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow result.")]
    internal static TResult? ExtractResult<TResult>(string? serializedOutput)
    {
        if (serializedOutput is null)
        {
            return default;
        }

        DurableWorkflowResult? workflowResult = TryParseWorkflowResult(serializedOutput);
        string? resultJson = workflowResult?.Result;

        if (resultJson is not null)
        {
            if (typeof(TResult) == typeof(string))
            {
                return (TResult)(object)resultJson;
            }

            return JsonSerializer.Deserialize<TResult>(resultJson, DurableSerialization.Options);
        }

        // Fallback: the output is not wrapped in DurableWorkflowResult.
        // The DurableDataConverter wraps string results in JSON quotes, so
        // we unwrap the outer JSON string first.
        try
        {
            string? innerString = JsonSerializer.Deserialize<string>(serializedOutput);
            if (typeof(TResult) == typeof(string) && innerString is not null)
            {
                return (TResult)(object)innerString;
            }

            if (innerString is not null)
            {
                return JsonSerializer.Deserialize<TResult>(innerString, DurableSerialization.Options);
            }
        }
        catch (JsonException)
        {
            // Not a JSON-encoded string; try direct deserialization below.
        }

        if (typeof(TResult) == typeof(string))
        {
            return (TResult)(object)serializedOutput;
        }

        return JsonSerializer.Deserialize<TResult>(serializedOutput, DurableSerialization.Options);
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2057", Justification = "Event types are registered at startup.")]
    private static WorkflowEvent? TryDeserializeEvent(string serializedEvent)
    {
        try
        {
            TypedPayload? wrapper = JsonSerializer.Deserialize(
                serializedEvent,
                DurableWorkflowJsonContext.Default.TypedPayload);

            if (wrapper?.TypeName is not null && wrapper.Data is not null)
            {
                Type? eventType = Type.GetType(wrapper.TypeName);
                if (eventType is not null)
                {
                    return DeserializeEventByType(eventType, wrapper.Data);
                }
            }

            return null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow event types.")]
    private static WorkflowEvent? DeserializeEventByType(Type eventType, string json)
    {
        // Types with internal constructors need manual deserialization
        if (eventType == typeof(ExecutorInvokedEvent)
            || eventType == typeof(ExecutorCompletedEvent)
            || eventType == typeof(WorkflowOutputEvent))
        {
            using JsonDocument doc = JsonDocument.Parse(json);
            JsonElement root = doc.RootElement;

            if (eventType == typeof(ExecutorInvokedEvent))
            {
                string executorId = root.GetProperty("executorId").GetString() ?? string.Empty;
                JsonElement? data = GetDataProperty(root);
                return new ExecutorInvokedEvent(executorId, data!);
            }

            if (eventType == typeof(ExecutorCompletedEvent))
            {
                string executorId = root.GetProperty("executorId").GetString() ?? string.Empty;
                JsonElement? data = GetDataProperty(root);
                return new ExecutorCompletedEvent(executorId, data);
            }

            // WorkflowOutputEvent
            string sourceId = root.GetProperty("sourceId").GetString() ?? string.Empty;
            object? outputData = GetDataProperty(root);
            return new WorkflowOutputEvent(outputData!, sourceId);
        }

        return JsonSerializer.Deserialize(json, eventType, DurableSerialization.Options) as WorkflowEvent;
    }

    private static JsonElement? GetDataProperty(JsonElement root)
    {
        if (!root.TryGetProperty("data", out JsonElement dataElement))
        {
            return null;
        }

        return dataElement.ValueKind == JsonValueKind.Null ? null : dataElement.Clone();
    }
}
