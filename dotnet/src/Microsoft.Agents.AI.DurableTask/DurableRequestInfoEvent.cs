// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Event raised when the durable workflow is waiting for external input at a <see cref="RequestPort"/>.
/// </summary>
/// <param name="RequestPortId">The ID of the request port waiting for input.</param>
/// <param name="Input">The serialized input data that was passed to the RequestPort.</param>
/// <param name="RequestType">The full type name of the request type.</param>
/// <param name="ResponseType">The full type name of the expected response type.</param>
/// <param name="RequestPort">The request port definition, if available.</param>
[DebuggerDisplay("RequestPort = {RequestPortId}")]
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
