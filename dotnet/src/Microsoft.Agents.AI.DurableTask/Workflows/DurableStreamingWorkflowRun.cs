// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Represents a durable workflow run that supports streaming workflow events as they occur.
/// </summary>
/// <remarks>
/// <para>
/// Events are detected by monitoring the orchestration's custom status at regular intervals.
/// When executors emit events via <see cref="IWorkflowContext.AddEventAsync"/> or
/// <see cref="IWorkflowContext.YieldOutputAsync"/>, they are written to the orchestration's
/// custom status and picked up by this streaming run.
/// </para>
/// <para>
/// When the workflow reaches a <see cref="RequestPort"/> executor, a <see cref="DurableWorkflowWaitingForInputEvent"/>
/// is yielded containing the request data. The caller should then call
/// <see cref="SendResponseAsync{TResponse}(DurableWorkflowWaitingForInputEvent, TResponse, CancellationToken)"/>
/// to provide the response and resume the workflow.
/// </para>
/// </remarks>
[DebuggerDisplay("{WorkflowName} ({RunId})")]
internal sealed class DurableStreamingWorkflowRun : IStreamingWorkflowRun
{
    private readonly DurableTaskClient _client;
    private readonly Dictionary<string, RequestPort> _requestPorts;

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
        this._requestPorts = ExtractRequestPorts(workflow);
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

        // Track how many events we've already read from the durable workflow status
        int lastReadEventIndex = 0;

        // Track which pending events we've already yielded to avoid duplicates
        HashSet<string> yieldedPendingEvents = [];

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

            // Always drain any unread events from the durable workflow status before checking terminal states.
            // The orchestration may complete before the next poll, so events would be lost if we
            // check terminal status first.
            if (metadata.SerializedCustomStatus is not null)
            {
                if (DurableWorkflowLiveStatus.TryParse(metadata.SerializedCustomStatus, out DurableWorkflowLiveStatus liveStatus))
                {
                    (List<WorkflowEvent> events, lastReadEventIndex) = DrainNewEvents(liveStatus.Events, lastReadEventIndex);
                    foreach (WorkflowEvent evt in events)
                    {
                        hasNewEvents = true;
                        yield return evt;
                    }

                    // Yield a DurableWorkflowWaitingForInputEvent for each new pending request port
                    foreach (PendingRequestPortStatus pending in liveStatus.PendingEvents)
                    {
                        if (yieldedPendingEvents.Add(pending.EventName))
                        {
                            if (!this._requestPorts.TryGetValue(pending.EventName, out RequestPort? matchingPort))
                            {
                                // RequestPort may not exist in the current workflow definition (e.g., during rolling deployments).
                                continue;
                            }

                            hasNewEvents = true;
                            yield return new DurableWorkflowWaitingForInputEvent(
                                pending.Input,
                                matchingPort);
                        }
                    }

                    // Sync tracking with current pending events so re-used RequestPort names can be yielded again
                    if (liveStatus.PendingEvents.Count == 0)
                    {
                        yieldedPendingEvents.Clear();
                    }
                    else
                    {
                        yieldedPendingEvents.IntersectWith(liveStatus.PendingEvents.Select(p => p.EventName));
                    }
                }
            }

            // Check terminal states after draining events from the durable workflow status
            if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
            {
                // The framework clears the durable workflow status on completion, so events may be in
                // SerializedOutput as a DurableWorkflowResult wrapper.
                if (TryParseWorkflowResult(metadata.SerializedOutput, out DurableWorkflowResult? outputResult))
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
                    // The runner always wraps output in DurableWorkflowResult, so a parse
                    // failure here indicates a bug. Yield a failed event so the consumer
                    // gets a visible, handleable signal without crashing.
                    yield return new DurableWorkflowFailedEvent(
                        $"Workflow '{this.WorkflowName}' (RunId: {this.RunId}) completed but its output could not be parsed as DurableWorkflowResult.");
                }

                yield break;
            }

            if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
            {
                string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Workflow execution failed.";
                yield return new DurableWorkflowFailedEvent(errorMessage, metadata.FailureDetails);
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
    /// Sends a response to a <see cref="DurableWorkflowWaitingForInputEvent"/> to resume the workflow.
    /// </summary>
    /// <typeparam name="TResponse">The type of the response data.</typeparam>
    /// <param name="requestEvent">The request event to respond to.</param>
    /// <param name="response">The response data to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>A <see cref="ValueTask"/> representing the asynchronous operation.</returns>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow types provided by the caller.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow types provided by the caller.")]
    public async ValueTask SendResponseAsync<TResponse>(DurableWorkflowWaitingForInputEvent requestEvent, TResponse response, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(requestEvent);

        string serializedResponse = JsonSerializer.Serialize(response, DurableSerialization.Options);
        await this._client.RaiseEventAsync(
            this.RunId,
            requestEvent.RequestPort.Id,
            serializedResponse,
            cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Waits for the workflow to complete and returns the result.
    /// </summary>
    /// <typeparam name="TResult">The expected result type.</typeparam>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The result of the workflow execution.</returns>
    /// <exception cref="TaskFailedException">Thrown when the workflow failed.</exception>
    /// <exception cref="InvalidOperationException">Thrown when the workflow was terminated or ended with an unexpected status.</exception>
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
            if (metadata.FailureDetails is not null)
            {
                throw new TaskFailedException(
                    taskName: this.WorkflowName,
                    taskId: -1,
                    failureDetails: metadata.FailureDetails);
            }

            throw new InvalidOperationException(
                $"Workflow '{this.WorkflowName}' (RunId: {this.RunId}) failed without failure details.");
        }

        throw new InvalidOperationException(
            $"Workflow '{this.WorkflowName}' (RunId: {this.RunId}) ended with unexpected status: {metadata.RuntimeStatus}");
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

    /// <summary>
    /// Attempts to parse the orchestration output as a <see cref="DurableWorkflowResult"/> wrapper.
    /// </summary>
    /// <remarks>
    /// The orchestration returns a <see cref="DurableWorkflowResult"/> object directly.
    /// The Durable Task framework's <c>DataConverter</c> serializes it as a JSON object
    /// in <c>SerializedOutput</c>, so we deserialize it directly.
    /// </remarks>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow result wrapper.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow result wrapper.")]
    private static bool TryParseWorkflowResult(string? serializedOutput, [NotNullWhen(true)] out DurableWorkflowResult? result)
    {
        if (serializedOutput is null)
        {
            result = default!;
            return false;
        }

        try
        {
            result = JsonSerializer.Deserialize(serializedOutput, DurableWorkflowJsonContext.Default.DurableWorkflowResult)!;
            return result is not null;
        }
        catch (JsonException)
        {
            result = default!;
            return false;
        }
    }

    /// <summary>
    /// Extracts a typed result from the orchestration output by unwrapping the
    /// <see cref="DurableWorkflowResult"/> wrapper.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow result.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow result.")]
    internal static TResult? ExtractResult<TResult>(string? serializedOutput)
    {
        if (serializedOutput is null)
        {
            return default;
        }

        if (!TryParseWorkflowResult(serializedOutput, out DurableWorkflowResult? workflowResult))
        {
            throw new InvalidOperationException(
                "Failed to parse orchestration output as DurableWorkflowResult. " +
                "The orchestration runner should always wrap output in this format.");
        }

        string? resultJson = workflowResult.Result;

        if (resultJson is null)
        {
            return default;
        }

        if (typeof(TResult) == typeof(string))
        {
            return (TResult)(object)resultJson;
        }

        return JsonSerializer.Deserialize<TResult>(resultJson, DurableSerialization.Options);
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

    private static Dictionary<string, RequestPort> ExtractRequestPorts(Workflow workflow)
    {
        return WorkflowAnalyzer.GetExecutorsFromWorkflowInOrder(workflow)
            .Where(e => e.RequestPort is not null)
            .ToDictionary(e => e.RequestPort!.Id, e => e.RequestPort!);
    }
}
