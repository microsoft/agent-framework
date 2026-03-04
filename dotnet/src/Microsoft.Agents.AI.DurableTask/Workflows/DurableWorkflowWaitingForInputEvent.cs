// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Event raised when the durable workflow is waiting for external input at a <see cref="RequestPort"/>.
/// </summary>
/// <param name="Input">The serialized input data that was passed to the RequestPort.</param>
/// <param name="RequestPort">The request port definition.</param>
[DebuggerDisplay("RequestPort = {RequestPort.Id}")]
public sealed class DurableWorkflowWaitingForInputEvent(
    string Input,
    RequestPort RequestPort) : WorkflowEvent
{
    /// <summary>
    /// Gets the serialized input data that was passed to the RequestPort.
    /// </summary>
    public string Input { get; } = Input;

    /// <summary>
    /// Gets the request port definition.
    /// </summary>
    public RequestPort RequestPort { get; } = RequestPort;

    /// <summary>
    /// Attempts to deserialize the input data to the specified type.
    /// </summary>
    /// <typeparam name="T">The type to deserialize to.</typeparam>
    /// <returns>The deserialized input.</returns>
    /// <exception cref="JsonException">Thrown when the input cannot be deserialized to the specified type.</exception>
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Deserializing workflow types provided by the caller.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Deserializing workflow types provided by the caller.")]
    public T? GetInputAs<T>()
    {
        return JsonSerializer.Deserialize<T>(this.Input, DurableSerialization.Options);
    }
}
