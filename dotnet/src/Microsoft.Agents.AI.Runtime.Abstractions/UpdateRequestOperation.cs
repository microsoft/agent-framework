// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Runtime;

/// <summary>
/// Represents an operation to update the status of an incoming request, possibly with a result.
/// The MessageId must correspond to a non-terminated request in the actor's inbox (Status is Pending).
/// </summary>
/// <param name="MessageId">The identifier of the message to update.</param>
/// <param name="Status">The new status for the request.</param>
/// <param name="Data">The data associated with the status update (e.g., result for completed requests).</param>
public sealed class UpdateRequestOperation(string MessageId, RequestStatus Status, JsonElement Data) : ActorMessageWriteOperation
{
    /// <summary>
    /// Gets the identifier of the message to update.
    /// </summary>
    [JsonPropertyName("messageId")]
    public string MessageId { get; } = MessageId;

    /// <summary>
    /// Gets the new status for the request.
    /// </summary>
    [JsonPropertyName("status")]
    public RequestStatus Status { get; } = Status;

    /// <summary>
    /// Gets the data associated with the status update.
    /// </summary>
    [JsonPropertyName("data")]
    public JsonElement Data { get; } = Data;

    /// <summary>
    /// Gets the type of the write operation.
    /// </summary>
    public override ActorWriteOperationType Type => ActorWriteOperationType.UpdateRequest;
}
