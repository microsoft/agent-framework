// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Represents a durable workflow run that supports streaming workflow events as they occur.
/// </summary>
/// <remarks>
/// This class provides a similar API to <see cref="StreamingRun"/> but for workflows executed as durable orchestrations.
/// Events are detected by monitoring the orchestration status for <see cref="RequestPort"/> executors that are waiting
/// for external input (human-in-the-loop scenarios).
/// </remarks>
public sealed class DurableStreamingRun : IAsyncDisposable
{
    private readonly DurableTaskClient _client;
    private readonly Workflow _workflow;
    private readonly List<RequestPort> _requestPorts;

    internal DurableStreamingRun(DurableTaskClient client, string instanceId, Workflow workflow)
    {
        this._client = client;
        this.InstanceId = instanceId;
        this._workflow = workflow;

        // Extract RequestPorts from the workflow for event detection
        this._requestPorts = ExtractRequestPorts(workflow);
    }

    /// <summary>
    /// Gets the unique instance ID for this orchestration run.
    /// </summary>
    public string InstanceId { get; }

    /// <summary>
    /// Gets the name of the workflow being executed.
    /// </summary>
    public string WorkflowName => this._workflow.Name ?? string.Empty;

    /// <summary>
    /// Gets the request ports defined in the workflow.
    /// </summary>
    public IReadOnlyList<RequestPort> RequestPorts => this._requestPorts;

    /// <summary>
    /// Gets the current execution status of the workflow run.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The current status of the durable run.</returns>
    public async ValueTask<DurableRunStatus> GetStatusAsync(CancellationToken cancellationToken = default)
    {
        OrchestrationMetadata? metadata = await this._client.GetInstanceAsync(
            this.InstanceId,
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

    /// <summary>
    /// Asynchronously streams workflow events as they occur during workflow execution.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This method monitors the durable orchestration and yields <see cref="WorkflowEvent"/> instances
    /// when the workflow reaches points that require external input (human-in-the-loop scenarios).
    /// </para>
    /// <para>
    /// When the orchestration reaches a <see cref="RequestPort"/> executor, a <see cref="DurableRequestInfoEvent"/>
    /// is yielded containing the request data. The caller should then call <see cref="SendResponseAsync{TResponse}(DurableRequestInfoEvent, TResponse, CancellationToken)"/>
    /// to provide the response and continue the workflow.
    /// </para>
    /// </remarks>
    /// <param name="pollingInterval">The interval between status checks. Defaults to 500ms.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>An asynchronous stream of <see cref="WorkflowEvent"/> objects.</returns>
    public async IAsyncEnumerable<WorkflowEvent> WatchStreamAsync(
        TimeSpan? pollingInterval = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        TimeSpan interval = pollingInterval ?? TimeSpan.FromMilliseconds(500);

        // Track which request ports we've already yielded events for and are waiting for response
        // Key: EventName (RequestPort ID), Value: Input data (to detect if we're at a different invocation)
        Dictionary<string, string> pendingRequests = [];

        // Track how many events we've already read from custom status
        int lastReadEventIndex = 0;

        while (!cancellationToken.IsCancellationRequested)
        {
            OrchestrationMetadata? metadata = await this._client.GetInstanceAsync(
                this.InstanceId,
                getInputsAndOutputs: true,
                cancellation: cancellationToken).ConfigureAwait(false);

            if (metadata is null)
            {
                yield break;
            }

            // Check if the orchestration has completed
            if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
            {
                yield return new DurableWorkflowCompletedEvent(metadata.SerializedOutput);
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

            // Check custom status for events and pending external events
            if (metadata.SerializedCustomStatus is not null)
            {
                DurableWorkflowCustomStatus? customStatus = TryParseCustomStatus(metadata.SerializedCustomStatus);
                if (customStatus is not null)
                {
                    // Yield any new events from executors
                    while (lastReadEventIndex < customStatus.Events.Count)
                    {
                        string serializedEvent = customStatus.Events[lastReadEventIndex];
                        lastReadEventIndex++;

                        WorkflowEvent? workflowEvent = TryDeserializeEvent(serializedEvent);
                        if (workflowEvent is not null)
                        {
                            yield return workflowEvent;
                        }
                    }

                    // Check for pending external event (HITL)
                    if (customStatus.PendingEvent is not null)
                    {
                        PendingExternalEventStatus pendingStatus = customStatus.PendingEvent;
                        string eventName = pendingStatus.EventName;
                        string inputData = pendingStatus.Input;

                        // Only yield a new event if:
                        // 1. We haven't seen this event name before, OR
                        // 2. The input data is different (meaning this is a new invocation of the same RequestPort)
                        bool shouldYield = !pendingRequests.TryGetValue(eventName, out string? previousInput)
                                           || previousInput != inputData;

                        if (shouldYield)
                        {
                            pendingRequests[eventName] = inputData;

                            // Find the matching RequestPort
                            RequestPort? requestPort = this._requestPorts.Find(p => p.Id == eventName);

                            yield return new DurableRequestInfoEvent(
                                RequestPortId: eventName,
                                Input: inputData,
                                RequestType: pendingStatus.RequestType,
                                ResponseType: pendingStatus.ResponseType,
                                RequestPort: requestPort);
                        }
                    }
                }
                else
                {
                    // Try parsing as legacy PendingExternalEventStatus for backward compatibility
                    PendingExternalEventStatus? pendingStatus = TryParsePendingStatus(metadata.SerializedCustomStatus);
                    if (pendingStatus is not null)
                    {
                        string eventName = pendingStatus.EventName;
                        string inputData = pendingStatus.Input;

                        bool shouldYield = !pendingRequests.TryGetValue(eventName, out string? previousInput)
                                           || previousInput != inputData;

                        if (shouldYield)
                        {
                            pendingRequests[eventName] = inputData;
                            RequestPort? requestPort = this._requestPorts.Find(p => p.Id == eventName);

                            yield return new DurableRequestInfoEvent(
                                RequestPortId: eventName,
                                Input: inputData,
                                RequestType: pendingStatus.RequestType,
                                ResponseType: pendingStatus.ResponseType,
                                RequestPort: requestPort);
                        }
                    }
                }
            }
            else
            {
                // Custom status is null - the orchestration is not waiting for external input
                // Clear any pending requests that were waiting (they've been processed)
                pendingRequests.Clear();
            }

            await Task.Delay(interval, cancellationToken).ConfigureAwait(false);
        }
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow custom status.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow custom status.")]
    private static DurableWorkflowCustomStatus? TryParseCustomStatus(string serializedStatus)
    {
        try
        {
            return JsonSerializer.Deserialize<DurableWorkflowCustomStatus>(serializedStatus);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2057", Justification = "Event types are registered at startup and available at runtime.")]
    private static WorkflowEvent? TryDeserializeEvent(string serializedEvent)
    {
        try
        {
            // First try to deserialize as SerializedWorkflowEvent (new format with type info)
            DurableWorkflowRunner.SerializedWorkflowEvent? wrapper =
                JsonSerializer.Deserialize<DurableWorkflowRunner.SerializedWorkflowEvent>(serializedEvent);

            if (wrapper?.TypeName is not null && wrapper.Data is not null)
            {
                Type? eventType = Type.GetType(wrapper.TypeName);
                if (eventType is not null)
                {
                    // Use custom deserialization for event types with constructor parameter mismatches
                    return DeserializeEventByType(eventType, wrapper.Data);
                }
            }

            // Fall back to deserializing as base WorkflowEvent (legacy format)
            return JsonSerializer.Deserialize<WorkflowEvent>(serializedEvent);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>
    /// Deserializes an event by type, handling constructor parameter name mismatches.
    /// </summary>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow event types.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow event types.")]
    private static WorkflowEvent? DeserializeEventByType(Type eventType, string json)
    {
        using JsonDocument doc = JsonDocument.Parse(json);
        JsonElement root = doc.RootElement;

        // Handle ExecutorInvokedEvent: constructor expects (executorId, message) but JSON has (ExecutorId, Data)
        if (eventType == typeof(ExecutorInvokedEvent))
        {
            string executorId = root.GetProperty("ExecutorId").GetString() ?? string.Empty;
            JsonElement? data = GetDataProperty(root);
            return new ExecutorInvokedEvent(executorId, data!);
        }

        // Handle ExecutorCompletedEvent: constructor expects (executorId, result) but JSON has (ExecutorId, Data)
        if (eventType == typeof(ExecutorCompletedEvent))
        {
            string executorId = root.GetProperty("ExecutorId").GetString() ?? string.Empty;
            JsonElement? data = GetDataProperty(root);
            return new ExecutorCompletedEvent(executorId, data);
        }

        // For other event types, try standard deserialization with case-insensitive options
        return JsonSerializer.Deserialize(json, eventType, s_caseInsensitiveOptions) as WorkflowEvent;
    }

    // Cached JsonSerializerOptions for case-insensitive deserialization
    private static readonly JsonSerializerOptions s_caseInsensitiveOptions = new() { PropertyNameCaseInsensitive = true };

    /// <summary>
    /// Gets the Data property from a JSON element.
    /// </summary>
    private static JsonElement? GetDataProperty(JsonElement root)
    {
        if (!root.TryGetProperty("Data", out JsonElement dataElement))
        {
            return null;
        }

        if (dataElement.ValueKind == JsonValueKind.Null)
        {
            return null;
        }

        return dataElement.Clone();
    }

    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing known type PendingExternalEventStatus.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing known type PendingExternalEventStatus.")]
    private static PendingExternalEventStatus? TryParsePendingStatus(string serializedStatus)
    {
        try
        {
            return JsonSerializer.Deserialize<PendingExternalEventStatus>(serializedStatus);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>
    /// Sends an external event to the workflow orchestration.
    /// </summary>
    /// <param name="eventName">The name of the event to raise (typically the <see cref="RequestPort.Id"/>).</param>
    /// <param name="eventData">The data to send with the event.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
#pragma warning disable CA1030 // Use events where appropriate
    public async ValueTask SendExternalEventAsync(string eventName, object? eventData = null, CancellationToken cancellationToken = default)
#pragma warning restore CA1030
    {
        await this._client.RaiseEventAsync(
            this.InstanceId,
            eventName,
            eventData,
            cancellation: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Sends a response to a pending request in the workflow.
    /// </summary>
    /// <remarks>
    /// The response is serialized to JSON before being sent to match what the orchestration expects.
    /// </remarks>
    /// <typeparam name="TResponse">The type of the response data.</typeparam>
    /// <param name="requestPortId">The ID of the request port to respond to.</param>
    /// <param name="response">The response data to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow types provided by the caller.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow types provided by the caller.")]
    public ValueTask SendResponseAsync<TResponse>(string requestPortId, TResponse response, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrEmpty(requestPortId);

        // Serialize the response to JSON string - the orchestration expects a string via WaitForExternalEvent<string>
        string serializedResponse = JsonSerializer.Serialize(response);
        return this.SendExternalEventAsync(requestPortId, serializedResponse, cancellationToken);
    }

    /// <summary>
    /// Sends a response to a <see cref="DurableRequestInfoEvent"/>.
    /// </summary>
    /// <remarks>
    /// The response is serialized to JSON before being sent to match what the orchestration expects.
    /// </remarks>
    /// <typeparam name="TResponse">The type of the response data.</typeparam>
    /// <param name="requestEvent">The request event to respond to.</param>
    /// <param name="response">The response data to send.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Serializing workflow types provided by the caller.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Serializing workflow types provided by the caller.")]
    public ValueTask SendResponseAsync<TResponse>(DurableRequestInfoEvent requestEvent, TResponse response, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(requestEvent);

        // Serialize the response to JSON string - the orchestration expects a string via WaitForExternalEvent<string>
        string serializedResponse = JsonSerializer.Serialize(response);
        return this.SendExternalEventAsync(requestEvent.RequestPortId, serializedResponse, cancellationToken);
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
            this.InstanceId,
            getInputsAndOutputs: true,
            cancellation: cancellationToken).ConfigureAwait(false);

        if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Completed)
        {
            return metadata.ReadOutputAs<TResult>();
        }

        if (metadata.RuntimeStatus == OrchestrationRuntimeStatus.Failed)
        {
            string errorMessage = metadata.FailureDetails?.ErrorMessage ?? "Workflow execution failed.";
            throw new InvalidOperationException(errorMessage);
        }

        throw new InvalidOperationException($"Workflow ended with unexpected status: {metadata.RuntimeStatus}");
    }

    /// <summary>
    /// Waits for the workflow to complete and returns the string result.
    /// </summary>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    /// <returns>The string result of the workflow execution.</returns>
    public ValueTask<string?> WaitForCompletionAsync(CancellationToken cancellationToken = default)
        => this.WaitForCompletionAsync<string>(cancellationToken);

    /// <summary>
    /// Terminates the workflow orchestration.
    /// </summary>
    /// <param name="reason">An optional reason for the termination.</param>
    /// <param name="cancellationToken">A cancellation token to observe.</param>
    public async ValueTask TerminateAsync(string? reason = null, CancellationToken cancellationToken = default)
    {
        await this._client.TerminateInstanceAsync(
            this.InstanceId,
            reason,
            cancellation: cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public ValueTask DisposeAsync()
    {
        // Nothing to dispose for durable runs - the orchestration continues independently
        return default;
    }

    private static List<RequestPort> ExtractRequestPorts(Workflow workflow)
    {
        List<RequestPort> requestPorts = [];

        foreach (WorkflowExecutorInfo executorInfo in WorkflowHelper.GetExecutorsFromWorkflowInOrder(workflow))
        {
            if (executorInfo.RequestPort is not null)
            {
                requestPorts.Add(executorInfo.RequestPort);
            }
        }

        return requestPorts;
    }
}

/// <summary>
/// Event raised when the durable workflow is waiting for external input at a <see cref="RequestPort"/>.
/// </summary>
/// <param name="RequestPortId">The ID of the request port waiting for input.</param>
/// <param name="Input">The serialized input data that was passed to the RequestPort.</param>
/// <param name="RequestType">The full type name of the request type.</param>
/// <param name="ResponseType">The full type name of the expected response type.</param>
/// <param name="RequestPort">The request port definition, if available.</param>
public sealed class DurableRequestInfoEvent(
    string RequestPortId,
    string Input,
    string RequestType,
    string ResponseType,
    RequestPort? RequestPort) : WorkflowEvent(Input)
{
    /// <summary>
    /// Gets the ID of the request port waiting for input.
    /// </summary>
    public string RequestPortId { get; } = RequestPortId;

    /// <summary>
    /// Gets the serialized input data that was passed to the RequestPort.
    /// </summary>
    public string Input { get; } = Input;

    /// <summary>
    /// Gets the full type name of the request type.
    /// </summary>
    public string RequestType { get; } = RequestType;

    /// <summary>
    /// Gets the full type name of the expected response type.
    /// </summary>
    public string ResponseType { get; } = ResponseType;

    /// <summary>
    /// Gets the request port definition, if available.
    /// </summary>
    public RequestPort? RequestPort { get; } = RequestPort;

    /// <summary>
    /// Attempts to deserialize the input data to the specified type.
    /// </summary>
    /// <typeparam name="T">The type to deserialize to.</typeparam>
    /// <returns>The deserialized input, or default if deserialization fails.</returns>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types provided by the caller.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types provided by the caller.")]
    public T? GetInputAs<T>()
    {
        try
        {
            return JsonSerializer.Deserialize<T>(this.Input);
        }
        catch (JsonException)
        {
            return default;
        }
    }
}

/// <summary>
/// Event raised when a durable workflow completes successfully.
/// </summary>
public sealed class DurableWorkflowCompletedEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowCompletedEvent"/> class.
    /// </summary>
    /// <param name="result">The serialized result of the workflow.</param>
    public DurableWorkflowCompletedEvent(string? result) : base(result)
    {
        this.Result = result;
    }

    /// <summary>
    /// Gets the serialized result of the workflow.
    /// </summary>
    public string? Result { get; }
}

/// <summary>
/// Event raised when a durable workflow fails.
/// </summary>
public sealed class DurableWorkflowFailedEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableWorkflowFailedEvent"/> class.
    /// </summary>
    /// <param name="errorMessage">The error message describing the failure.</param>
    public DurableWorkflowFailedEvent(string errorMessage) : base(errorMessage)
    {
        this.ErrorMessage = errorMessage;
    }

    /// <summary>
    /// Gets the error message describing the failure.
    /// </summary>
    public string ErrorMessage { get; }
}

/// <summary>
/// Event raised when an executor yields intermediate output via <see cref="IWorkflowContext.YieldOutputAsync"/>.
/// </summary>
/// <remarks>
/// This is the durable equivalent of <see cref="WorkflowOutputEvent"/> since that class has an internal
/// constructor not accessible from outside the Workflows assembly.
/// </remarks>
public sealed class DurableYieldedOutputEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableYieldedOutputEvent"/> class.
    /// </summary>
    /// <param name="executorId">The ID of the executor that yielded the output.</param>
    /// <param name="output">The yielded output value.</param>
    public DurableYieldedOutputEvent(string executorId, object output) : base(output)
    {
        this.ExecutorId = executorId;
        this.Output = output;
    }

    /// <summary>
    /// Gets the ID of the executor that yielded the output.
    /// </summary>
    public string ExecutorId { get; }

    /// <summary>
    /// Gets the yielded output value.
    /// </summary>
    public object Output { get; }
}

/// <summary>
/// Event raised when an executor requests the workflow to halt via <see cref="IWorkflowContext.RequestHaltAsync"/>.
/// </summary>
/// <remarks>
/// This is the durable equivalent of the internal RequestHaltEvent since that class is not accessible
/// from outside the Workflows assembly.
/// </remarks>
public sealed class DurableHaltRequestedEvent : WorkflowEvent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DurableHaltRequestedEvent"/> class.
    /// </summary>
    /// <param name="executorId">The ID of the executor that requested the halt.</param>
    public DurableHaltRequestedEvent(string executorId) : base($"Halt requested by {executorId}")
    {
        this.ExecutorId = executorId;
    }

    /// <summary>
    /// Gets the ID of the executor that requested the halt.
    /// </summary>
    public string ExecutorId { get; }
}
